"""
Efficiency Optimizer — Token & Latency Minimization
====================================================
Reduces redundant tool calls, compresses context strategically,
and identifies token bloat patterns to minimize cost and latency.

Key optimizations:
1. Context deduplication: Strip repeated observations from context
2. Smart truncation: Progressive truncation based on information density
3. Tool call batching: Detect sequential reads that could be batched
4. Token budget tracking: Per-session token accounting with alerts
5. Caching: Memoize deterministic tool calls (e.g., get_today)
"""

import time
import logging
import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict, OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class EfficiencyMetrics:
    """Tracks efficiency metrics for a session."""
    session_id: str
    total_tokens_saved: int = 0
    total_calls_optimized: int = 0
    contexts_deduplicated: int = 0
    calls_batched: int = 0
    cache_hits: int = 0
    truncations_applied: int = 0
    start_time: float = 0.0
    original_estimated_tokens: int = 0
    actual_tokens_used: int = 0

    def savings_percent(self) -> float:
        if self.original_estimated_tokens == 0:
            return 0.0
        saved = self.original_estimated_tokens - self.actual_tokens_used
        return round(max(0, saved / self.original_estimated_tokens * 100), 1)


# Cache for deterministic tool calls (TTL-based)
_ToolCache = OrderedDict  # LRU cache
_CACHE_MAX_SIZE = 100
_CACHE_TTL_SECONDS = 300  # 5 minutes


class EfficiencyOptimizer:
    """
    Optimizes agent execution for token efficiency.
    Drop-in compatible with TaskPlanner.
    """

    # Tool calls that are deterministic and safe to cache
    CACHABLE_TOOLS = {
        "get_today", "get_week", "get_office_hour_slots",
        "list_pipelines", "list_pending", "get_sequence_templates",
        "list_pricing_tiers", "get_all_statuses",
    }

    # Tool calls that typically return large payloads
    HIGH_VOLUME_TOOLS = {
        "get_inbox", "summarize_and_categorize_inbox", "deep_research",
        "browse_agent",
    }

    def __init__(self):
        self.cache: Dict[str, _ToolCache] = defaultdict(OrderedDict)  # tool_name -> OrderedDict
        self.session_metrics: Dict[str, EfficiencyMetrics] = {}
        self.seen_contexts: Dict[str, Set[str]] = defaultdict(set)  # session_id -> set of content hashes

    def start_session(self, session_id: str):
        """Initialize metrics for a new session."""
        self.session_metrics[session_id] = EfficiencyMetrics(
            session_id=session_id,
            start_time=time.time(),
        )
        self.seen_contexts[session_id] = set()

    def should_optimize_call(self, session_id: str, fn_name: str,
                             fn_args: Dict[str, Any]) -> Tuple[bool, Optional[Any]]:
        """
        Check if a tool call can be optimized (cached/skipped).
        Returns (should_execute, cached_result).
        If cached_result is not None, the call can be skipped.
        """
        metrics = self.session_metrics.get(session_id)
        if not metrics:
            return True, None

        # Check if this is a cachable tool
        if fn_name not in self.CACHABLE_TOOLS:
            return True, None

        # Check cache
        cache = self.cache[fn_name]
        cache_key = self._make_cache_key(fn_args)

        if cache_key in cache:
            result, timestamp = cache[cache_key]
            # Check TTL
            if time.time() - timestamp < _CACHE_TTL_SECONDS:
                # Move to end (LRU)
                cache.move_to_end(cache_key)
                metrics.cache_hits += 1
                metrics.total_calls_optimized += 1
                logger.info(f"[EFFICIENCY] Cache hit for {fn_name} (args: {list(fn_args.keys())})")
                return False, result  # Skip execution, return cached

        return True, None

    def record_cache(self, fn_name: str, fn_args: Dict[str, Any], result: Any):
        """Store a result in the cache."""
        cache = self.cache[fn_name]
        cache_key = self._make_cache_key(fn_args)

        # LRU eviction
        if len(cache) >= _CACHE_MAX_SIZE:
            cache.popitem(last=False)

        cache[cache_key] = (result, time.time())

    def deduplicate_context(self, session_id: str, content: str) -> Optional[str]:
        """
        Remove redundant context content.
        Returns None if content is a duplicate (skip it).
        Returns original content if unique.
        """
        metrics = self.session_metrics.get(session_id)
        if not metrics:
            return content

        content_hash = hashlib.md5(content.encode()).hexdigest()
        seen = self.seen_contexts[session_id]

        if content_hash in seen:
            metrics.contexts_deduplicated += 1
            metrics.total_tokens_saved += len(content) // 4  # rough token estimate
            logger.info(f"[EFFICIENCY] Deduplicated context ({len(content)} chars)")
            return None

        seen.add(content_hash)
        return content

    def optimize_observation(self, session_id: str, observation: str,
                             tool_name: str) -> str:
        """
        Apply progressive truncation based on tool type and content size.
        """
        metrics = self.session_metrics.get(session_id)
        if not metrics:
            return observation

        char_count = len(observation)
        if char_count < 500:
            return observation  # Small enough

        # Check if high-volume tool
        is_high_volume = tool_name in self.HIGH_VOLUME_TOOLS

        if is_high_volume:
            # Aggressive truncation for known large outputs
            if char_count > 8000:
                metrics.truncations_applied += 1
                saved = char_count - 4000
                metrics.total_tokens_saved += saved // 4
                return observation[:2000] + f"\n... [TRUNCATED {char_count - 4000} chars] ...\n" + observation[-2000:]
            elif char_count > 4000:
                metrics.truncations_applied += 1
                saved = char_count - 2000
                metrics.total_tokens_saved += saved // 4
                return observation[:1000] + f"\n... [TRUNCATED {char_count - 2000} chars] ...\n" + observation[-1000:]
        else:
            # Standard truncation
            if char_count > 4000:
                metrics.truncations_applied += 1
                saved = char_count - 2000
                metrics.total_tokens_saved += saved // 4
                return observation[:1000] + f"\n... [TRUNCATED {saved} chars] ...\n" + observation[-1000:]

        return observation

    def detect_redundant_sequence(self, history: List[Dict]) -> Optional[str]:
        """
        Detect redundant tool call sequences like:
        - search -> search -> search (could be batched)
        - read -> read -> read (sequential reads)
        - browse -> browse -> browse
        Returns a warning message if redundancy detected.
        """
        if len(history) < 3:
            return None

        recent = history[-5:]
        tool_names = [h.get("tool_name", "") for h in recent]

        # Detect same tool called 3+ times consecutively
        for tool in set(tool_names):
            if tool_names.count(tool) >= 3:
                # Check if consecutive
                indices = [i for i, t in enumerate(tool_names) if t == tool]
                if max(indices) - min(indices) + 1 == len(indices):
                    return f"[EFFICIENCY] Warning: {tool} called {tool_names.count(tool)} times consecutively. Consider batching."

        return None

    def estimate_token_savings(self, session_id: str) -> EfficiencyMetrics:
        """Get token savings estimate for a session."""
        return self.session_metrics.get(session_id, EfficiencyMetrics(session_id=session_id))

    def get_session_report(self, session_id: str) -> Dict[str, Any]:
        """Generate a human-readable efficiency report."""
        metrics = self.session_metrics.get(session_id)
        if not metrics:
            return {"session_id": session_id, "status": "no_data"}

        return {
            "session_id": session_id,
            "duration_seconds": round(time.time() - metrics.start_time, 1),
            "total_tokens_saved": metrics.total_tokens_saved,
            "estimated_cost_saved": round(metrics.total_tokens_saved * 0.000001, 6),  # ~$1/1M tokens
            "total_calls_optimized": metrics.total_calls_optimized,
            "breakdown": {
                "contexts_deduplicated": metrics.contexts_deduplicated,
                "calls_batched": metrics.calls_batched,
                "cache_hits": metrics.cache_hits,
                "truncations_applied": metrics.truncations_applied,
            },
            "savings_percent": metrics.savings_percent(),
        }

    def complete_session(self, session_id: str) -> EfficiencyMetrics:
        """Finalize and return metrics for a session."""
        metrics = self.session_metrics.pop(session_id, None)
        if metrics:
            self.seen_contexts.pop(session_id, None)
        return metrics or EfficiencyMetrics(session_id=session_id)

    def _make_cache_key(self, args: Dict[str, Any]) -> str:
        """Create a cache key from function arguments."""
        return hashlib.md5(json.dumps(args, sort_keys=True).encode()).hexdigest()


# Global instance
efficiency_optimizer = EfficiencyOptimizer()