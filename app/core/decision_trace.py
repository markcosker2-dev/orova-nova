"""
Decision Trace — Structured observability for agentic decision-making.
=====================================================================
Captures the agent's intent, tool selection, expected vs. actual outcome,
and firewall decisions for every step. Enables full failure reconstruction.
"""

import json
import time
import logging
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DecisionStep:
    """A single decision step in the agent's execution trace."""
    step_number: int
    goal: str
    tool_name: str
    parameters: Dict[str, Any]
    intent: str  # Agent's stated intent for this tool call
    expected_outcome: str  # What the agent expected to happen
    actual_outcome: str  # What actually happened (truncated)
    status: str  # "success", "error", "blocked", "timeout", "loop_detected"
    latency_ms: float
    token_usage: Optional[Dict[str, int]] = None  # prompt_tokens, completion_tokens
    firewall_decision: str = "allow"
    firewall_reason: str = ""
    error_message: str = ""
    compressed: bool = False  # True if this step was compressed from history


@dataclass
class DecisionTrace:
    """Complete decision trace for a single task execution."""
    session_id: str
    agent_id: str
    client_id: int
    goal: str
    start_time: float
    end_time: Optional[float] = None
    total_steps: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    final_status: str = "unknown"  # "completed", "failed", "max_steps", "degraded", "blocked"
    final_response: str = ""
    steps: List[DecisionStep] = field(default_factory=list)
    error: Optional[str] = None

    def add_step(self, step: DecisionStep):
        self.steps.append(step)
        self.total_steps = len(self.steps)
        self.total_latency_ms += step.latency_ms
        if step.token_usage:
            self.total_tokens += step.token_usage.get("total_tokens", 0)

    def complete(self, status: str, response: str = "", error: Optional[str] = None):
        self.end_time = time.time()
        self.final_status = status
        self.final_response = response[:500] if response else ""
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "client_id": self.client_id,
            "goal": self.goal[:200],
            "duration_seconds": round((self.end_time or time.time()) - self.start_time, 2),
            "total_steps": self.total_steps,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_tokens": self.total_tokens,
            "final_status": self.final_status,
            "final_response": self.final_response[:200],
            "error": self.error[:500] if self.error else None,
            "steps": [asdict(s) for s in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_markdown(self, max_step_detail: int = 3) -> str:
        """Human-readable markdown summary."""
        lines = [
            f"## Decision Trace: `{self.session_id}`",
            f"",
            f"**Goal:** {self.goal[:200]}",
            f"**Agent:** {self.agent_id} | **Client:** {self.client_id}",
            f"**Duration:** {self.to_dict()['duration_seconds']}s | **Steps:** {self.total_steps} | **Tokens:** {self.total_tokens}",
            f"**Status:** {self.final_status}",
            f"",
            f"### Step-by-Step Breakdown",
            f"",
        ]
        for i, s in enumerate(self.steps[:max_step_detail]):
            lines.extend([
                f"**Step {s.step_number}:** `{s.tool_name}` → **{s.status}** ({s.latency_ms:.0f}ms)",
                f"- Intent: {s.intent[:150]}",
                f"- Expected: {s.expected_outcome[:150]}",
                f"- Actual: {s.actual_outcome[:150]}",
                f"- Firewall: {s.firewall_decision}" + (f" ({s.firewall_reason[:100]})" if s.firewall_reason else ""),
                f"",
            ])
        if len(self.steps) > max_step_detail:
            lines.append(f"... and {len(self.steps) - max_step_detail} more steps")
        if self.error:
            lines.extend(["", "### Error", "", f"```\n{self.error[:500]}\n```"])
        return "\n".join(lines)


class DecisionTraceManager:
    """
    Manages decision traces with bounded memory storage.
    Traces are kept in memory for the current session and
    optionally persisted to disk for post-mortem analysis.
    """

    MAX_TRACES = 500
    TRACE_DIR = "data/traces"

    def __init__(self, persist: bool = False):
        self.active_traces: Dict[str, DecisionTrace] = {}
        self.completed_traces: deque = deque(maxlen=self.MAX_TRACES)
        self.persist = persist
        if persist:
            Path(self.TRACE_DIR).mkdir(parents=True, exist_ok=True)

    def start_trace(self, session_id: str, agent_id: str, client_id: int, goal: str) -> DecisionTrace:
        trace = DecisionTrace(
            session_id=session_id,
            agent_id=agent_id,
            client_id=client_id,
            goal=goal,
            start_time=time.time(),
        )
        self.active_traces[session_id] = trace
        logger.info(f"[TRACE] Started {session_id}: {goal[:80]}...")
        return trace

    def get_trace(self, session_id: str) -> Optional[DecisionTrace]:
        return self.active_traces.get(session_id)

    def add_step(self, session_id: str, step: DecisionStep) -> bool:
        trace = self.active_traces.get(session_id)
        if not trace:
            logger.warning(f"[TRACE] No active trace for {session_id}")
            return False
        trace.add_step(step)
        return True

    def complete_trace(self, session_id: str, status: str, response: str = "", error: Optional[str] = None) -> Optional[Dict[str, Any]]:
        trace = self.active_traces.pop(session_id, None)
        if not trace:
            logger.warning(f"[TRACE] Cannot complete unknown trace {session_id}")
            return None
        trace.complete(status, response, error)
        self.completed_traces.append(trace)
        logger.info(f"[TRACE] Completed {session_id}: {status} ({trace.total_steps} steps, {trace.total_tokens} tokens)")

        if self.persist:
            self._persist_trace(trace)
        return trace.to_dict()

    def _persist_trace(self, trace: DecisionTrace):
        """Save trace to disk for post-mortem analysis."""
        try:
            timestamp = datetime.fromtimestamp(trace.start_time).strftime("%Y%m%d_%H%M%S")
            safe_goal = "".join(c if c.isalnum() or c in " _-" else "_" for c in trace.goal[:50])
            filename = f"{timestamp}_{trace.session_id}_{safe_goal}.json"
            filepath = Path(self.TRACE_DIR) / filename
            with open(filepath, "w") as f:
                json.dump(trace.to_dict(), f, indent=2, default=str)
            logger.info(f"[TRACE] Persisted to {filepath}")
        except Exception as e:
            logger.error(f"[TRACE] Failed to persist: {e}")

    def get_recent_traces(self, n: int = 10) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in list(self.completed_traces)[-n:]]

    def get_traces_by_status(self, status: str) -> List[Dict[str, Any]]:
        return [
            t.to_dict() for t in self.completed_traces
            if t.final_status == status
        ]

    def get_failure_summary(self) -> Dict[str, Any]:
        """Aggregate failure patterns for observability."""
        failures = [t for t in self.completed_traces if t.final_status in ("failed", "error")]
        if not failures:
            return {"total_failures": 0, "patterns": []}

        patterns = {}
        for t in failures:
            for s in t.steps:
                if s.status == "error":
                    key = f"{s.tool_name}:{s.error_message[:80]}"
                    patterns[key] = patterns.get(key, 0) + 1

        return {
            "total_failures": len(failures),
            "failure_rate": round(len(failures) / max(len(self.completed_traces), 1) * 100, 1),
            "patterns": sorted(patterns.items(), key=lambda x: -x[1])[:10],
        }

    def get_performance_summary(self, n: int = 50) -> Dict[str, Any]:
        """Aggregate performance metrics from recent traces."""
        recent = list(self.completed_traces)[-n:]
        if not recent:
            return {"total_traces": 0}

        latencies = [t.total_latency_ms for t in recent]
        tokens = [t.total_tokens for t in recent]
        steps = [t.total_steps for t in recent]

        return {
            "total_traces": len(recent),
            "latency_ms": {
                "avg": round(sum(latencies) / len(latencies), 1),
                "max": round(max(latencies), 1),
                "min": round(min(latencies), 1),
            },
            "tokens": {
                "avg": round(sum(tokens) / len(tokens), 0),
                "max": max(tokens),
                "min": min(tokens),
            },
            "steps": {
                "avg": round(sum(steps) / len(steps), 1),
                "max": max(steps),
                "min": min(steps),
            },
            "status_breakdown": {
                status: sum(1 for t in recent if t.final_status == status)
                for status in set(t.final_status for t in recent)
            },
        }


# Global instance
trace_manager = DecisionTraceManager(persist=True)