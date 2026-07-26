"""
Phase 4 Hardening: Comprehensive Error Handling, Retry Logic, and Resilience.
"""
import asyncio
import logging
import time
import json
from functools import wraps
from typing import Any, Callable, Optional, Dict, List
import collections
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ─────── [P4.1] CIRCUIT BREAKER PATTERNS ─────────
class CircuitBreaker:
    """Enhanced circuit breaker with half-open state tracking."""
    
    def __init__(self, threshold: int = 5, cooldown: float = 60.0, name: str = "circuit"):
        self.threshold = threshold
        self.cooldown = cooldown
        self.name = name
        self.failures = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half-open
        
    def record_success(self):
        if self.state != "closed":
            logger.info(f"[BREAKER] {self.name}: CLOSED (recovered)")
        self.failures = 0
        self.state = "closed"
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.threshold:
            self.state = "open"
            logger.warning(f"[BREAKER] {self.name}: OPEN (threshold reached: {self.failures})")
            
    def can_attempt(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time >= self.cooldown:
                self.state = "half-open"
                logger.info(f"[BREAKER] {self.name}: HALF-OPEN (attempting recovery)")
                return True
            return False
        return True  # half-open allows attempt

# ─────── [P4.2] RETRY DECORATOR ─────────
def async_retry(max_attempts: int = 3, backoff_base: float = 1.0, max_backoff: float = 30.0, 
                exponential: bool = True, reraise: bool = True):
    """
    Decorator for exponential backoff retry on async functions.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = min(backoff_base * (2 ** attempt if exponential else attempt), max_backoff)
                        logger.warning(f"[RETRY] {func.__name__} attempt {attempt + 1}/{max_attempts} failed: {str(e)[:100]}. Retrying in {delay}s...")
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"[RETRY] {func.__name__} failed after {max_attempts} attempts")
            
            if reraise and last_exception:
                raise last_exception
            return None
        return wrapper
    return decorator

# ─────── [P4.3] RATE LIMITER ─────────
class RateLimiter:
    """Token bucket rate limiter per client/endpoint."""
    
    def __init__(self, rate: float, period: float = 60.0):
        """rate: requests per period (in seconds)"""
        self.rate = rate
        self.period = period
        # Cap at 10,000 unique clients; evict LRU automatically
        self._MAX_CLIENTS = 10_000
        self.tokens: dict = {}
        self.last_update: dict = {}
        self._access_order: collections.OrderedDict = collections.OrderedDict()
        
    def _evict_if_needed(self, client_id: str):
        if client_id not in self._access_order:
            if len(self._access_order) >= self._MAX_CLIENTS:
                evicted, _ = self._access_order.popitem(last=False)
                self.tokens.pop(evicted, None)
                self.last_update.pop(evicted, None)
            self._access_order[client_id] = True
        else:
            self._access_order.move_to_end(client_id)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        self._evict_if_needed(client_id)
        last = self.last_update.get(client_id, now)
        time_passed = now - last
        
        # Refill tokens
        current_tokens = self.tokens.get(client_id, self.rate)
        self.tokens[client_id] = min(self.rate, current_tokens + time_passed * (self.rate / self.period))
        self.last_update[client_id] = now
        
        if self.tokens[client_id] >= 1:
            self.tokens[client_id] -= 1
            return True
        return False
    
    def get_retry_after(self, client_id: str) -> float:
        """Returns seconds to wait before retry is allowed."""
        self._evict_if_needed(client_id)
        current_tokens = self.tokens.get(client_id, self.rate)
        if current_tokens < 1:
            return (1 - current_tokens) * (self.period / self.rate)
        return 0.0


# [S-12] Per-route rate limiter — allows different limits per route pattern
class PerRouteRateLimiter:
    """Rate limiter with per-route configuration.
    
    Routes are matched by prefix. More specific routes should be registered first.
    Default limit applies to any route not explicitly configured.
    """
    
    def __init__(self, default_rate: int = 100, default_period: float = 60.0):
        self._default = RateLimiter(rate=default_rate, period=default_period)
        # Ordered list of (prefix, RateLimiter) — first match wins
        self._routes: list[tuple[str, RateLimiter]] = []
    
    def add_route(self, prefix: str, rate: int, period: float = 60.0):
        """Register a per-route rate limit. More specific prefixes should be added first."""
        self._routes.append((prefix, RateLimiter(rate=rate, period=period)))
    
    def is_allowed(self, client_id: str, path: str) -> bool:
        """Check if request is allowed for the given client and path."""
        for prefix, limiter in self._routes:
            if path.startswith(prefix):
                return limiter.is_allowed(client_id)
        return self._default.is_allowed(client_id)
    
    def get_retry_after(self, client_id: str, path: str) -> float:
        """Returns seconds to wait before retry is allowed."""
        for prefix, limiter in self._routes:
            if path.startswith(prefix):
                return limiter.get_retry_after(client_id)
        return self._default.get_retry_after(client_id)

# ─────── [P4.4] REQUEST SANITIZATION ─────────
class RequestSanitizer:
    """Validate and sanitize user inputs to prevent injection/overflow attacks."""
    
    @staticmethod
    def sanitize_string(value: str, max_len: int = 10000) -> str:
        """Sanitize string input."""
        if not isinstance(value, str):
            return ""
        # Remove null bytes
        value = value.replace('\x00', '')
        # Truncate to max length
        return value[:max_len]
    
    @staticmethod
    def sanitize_dict(data: dict, max_depth: int = 10, current_depth: int = 0) -> dict:
        """Recursively sanitize dict to prevent deeply nested bomb attacks."""
        if current_depth > max_depth:
            logger.warning(f"[SANITIZER] Dict nesting exceeded {max_depth} levels")
            return {}
        
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = RequestSanitizer.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = RequestSanitizer.sanitize_dict(value, max_depth, current_depth + 1)
            elif isinstance(value, list):
                sanitized[key] = [RequestSanitizer.sanitize_string(str(v), 1000) if isinstance(v, str) else v for v in value[:100]]
            else:
                sanitized[key] = value
        return sanitized
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Basic email validation."""
        if not email or '@' not in email:
            return False
        parts = email.split('@')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return False
        if len(email) > 254:
            return False
        return True
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Basic URL validation."""
        if not url or len(url) > 2048:
            return False
        if not url.startswith(('http://', 'https://')):
            return False
        return True

# ─────── [P4.5] ERROR RECOVERY HANDLERS ─────────
class ErrorRecoveryHandler:
    """Handles various error types and provides recovery strategies."""
    
    @staticmethod
    def should_retry(error: Exception) -> bool:
        """Determine if error is retryable."""
        retryable_keywords = [
            "timeout", "connection", "reset", "temporarily unavailable",
            "rate limit", "429", "503", "502", "50", "transient"
        ]
        error_str = str(error).lower()
        return any(keyword in error_str for keyword in retryable_keywords)
    
    @staticmethod
    def get_error_category(error: Exception) -> str:
        """Categorize error type."""
        error_str = str(error).lower()
        if "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif "timeout" in error_str or "timed out" in error_str:
            return "timeout"
        elif "not found" in error_str or "404" in error_str:
            return "not_found"
        elif "unauthorized" in error_str or "401" in error_str:
            return "auth"
        elif "connection" in error_str or "reset" in error_str:
            return "connection"
        return "unknown"
    
    @staticmethod
    async def handle_error(error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive error handling with logging and recovery suggestions."""
        category = ErrorRecoveryHandler.get_error_category(error)
        should_retry = ErrorRecoveryHandler.should_retry(error)
        
        response = {
            "success": False,
            "error_category": category,
            "error_message": str(error)[:200],
            "retryable": should_retry,
            "context": {
                "timestamp": datetime.utcnow().isoformat(),
                "function": context.get("function", "unknown"),
                "client_id": context.get("client_id", 0),
            }
        }
        
        # Log error with context
        logger.error(f"[ERROR] {category}: {context.get('function', 'unknown')} - {str(error)[:200]}")
        
        # Return structured response
        return response

# ─────── [P4.6] MEMORY MANAGEMENT ─────────
class MemoryMonitor:
    """Monitor and cap memory usage to prevent OOM on free tier."""
    
    def __init__(self, max_memory_mb: int = 400):  # 400MB cap on 512MB free tier
        self.max_memory_mb = max_memory_mb
        self.memory_usage_log: List[Dict] = []
        
    async def check_memory(self) -> Dict[str, Any]:
        """Check current memory usage."""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            self.memory_usage_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "memory_mb": memory_mb,
                "percent": process.memory_percent()
            })
            
            # Keep only last 1000 records
            if len(self.memory_usage_log) > 1000:
                self.memory_usage_log = self.memory_usage_log[-1000:]
            
            is_critical = memory_mb > self.max_memory_mb
            if is_critical:
                logger.critical(f"[MEMORY] CRITICAL: {memory_mb:.1f}MB exceeds limit {self.max_memory_mb}MB")
            
            return {
                "memory_mb": memory_mb,
                "limit_mb": self.max_memory_mb,
                "critical": is_critical,
                "percent_of_limit": (memory_mb / self.max_memory_mb) * 100
            }
        except ImportError:
            logger.warning("[MEMORY] psutil not available")
            return {"available": False}
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory statistics from log."""
        if not self.memory_usage_log:
            return {}
        
        memories = [m["memory_mb"] for m in self.memory_usage_log]
        return {
            "current_mb": memories[-1],
            "average_mb": sum(memories) / len(memories),
            "peak_mb": max(memories),
            "min_mb": min(memories),
            "measurements": len(self.memory_usage_log),
        }

# ─────── [P4.7] HEALTH CHECK REGISTRY ─────────
class HealthCheckRegistry:
    """Registry for component health checks."""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
        
    def register(self, name: str, check_func: Callable):
        """Register a health check function."""
        self.checks[name] = check_func
        
    async def run_all(self) -> Dict[str, Dict[str, Any]]:
        """Run all registered health checks."""
        results = {}
        for name, check_func in self.checks.items():
            try:
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                results[name] = {"status": "ok", **result}
            except Exception as e:
                logger.warning(f"[HEALTH] {name} check failed: {e}")
                results[name] = {"status": "failed", "error": str(e)[:100]}
        
        self.results = results
        return results
    
    def get_overall_status(self) -> str:
        """Get overall system status."""
        if not self.results:
            return "unknown"
        if all(r.get("status") == "ok" for r in self.results.values()):
            return "healthy"
        if any(r.get("status") == "ok" for r in self.results.values()):
            return "degraded"
        return "critical"

# ─────── [P4.8] REQUEST TRACING ─────────
class RequestTracer:
    """Trace requests for debugging and analytics."""
    
    def __init__(self):
        self.traces: Dict[str, List[Dict]] = defaultdict(list)
        self._trace_count = 0
        self._CLEANUP_INTERVAL = 500   # clean every 500 traces written
        
    def trace(self, request_id: str, event: str, data: Dict[str, Any] = None):
        """Record a trace event."""
        self.traces[request_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "data": data or {}
        })
        self._trace_count += 1
        if self._trace_count >= self._CLEANUP_INTERVAL:
            self._trace_count = 0
            self.clear_old_traces(max_age_hours=1)
        
        # Cleanup old traces (keep max 1000 per request)
        if len(self.traces[request_id]) > 1000:
            self.traces[request_id] = self.traces[request_id][-500:]
    
    def get_trace(self, request_id: str) -> List[Dict]:
        """Retrieve trace for request."""
        return self.traces.get(request_id, [])
    
    def clear_old_traces(self, max_age_hours: int = 24):
        """Clear traces older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        for request_id in list(self.traces.keys()):
            self.traces[request_id] = [
                t for t in self.traces[request_id]
                if datetime.fromisoformat(t["timestamp"]) > cutoff
            ]
            if not self.traces[request_id]:
                del self.traces[request_id]

# ─────── CONCURRENCY LIMITS (single owner) ─────────
# Fan-out caps for RAM-heavy work on the 512MB free tier. Centralised here,
# beside memory_monitor, because this module is the canonical owner of resource
# guarding — memory_monitor measures real RSS and is what the re-enrich lane
# checks after the 2026-07-21 OOM kill wiped the disk mid-run.
#
# These replace app/core/semaphore.py, deleted 2026-07-26. That module declared
# itself "the single source of truth for all RAM-heavy skill concurrency
# control" but was imported by NOTHING, while three call sites each hard-coded
# their own magic number. Its design was also unusable as written: a global
# limit of 1 would serialise whole lanes past Render's 30s request kill, and
# would deadlock wherever one guarded coroutine awaits another (enrich_lead_lite
# -> _fetch_page).
#
# Numbers are caps on CONCURRENT work inside one operation, not a process-wide
# gate. Actual memory decisions stay with memory_monitor.
#
# CRAWL: was 10 while the page list is built as [homepage] + prioritized[:4]
# (max 5, or 7 on the hard-coded fallback) — so the semaphore never blocked and
# guarded nothing. 4 actually binds, and each slot holds a fetched page plus its
# BeautifulSoup tree, which is several times the HTML size.
CONCURRENCY_LIMITS = {
    "page_crawl": 4,        # concurrent page fetches within one enrichment
    "lead_enrich": 5,       # concurrent per-lead enrichment within one hunt
    "lead_enrich_batch": 3, # concurrent leads in enrich_leads_batch
}


def concurrency_limit(name: str) -> int:
    """Fan-out cap for a named RAM-heavy operation.

    Unknown names fall back to 1 (the safe direction on a 512MB tier) and log,
    rather than silently running unbounded.
    """
    if name in CONCURRENCY_LIMITS:
        return CONCURRENCY_LIMITS[name]
    logger.warning(f"[CONCURRENCY] unknown limit {name!r}; defaulting to 1")
    return 1


# ─────── SINGLETON INSTANCES ─────────
circuit_breaker = CircuitBreaker(name="default")
rate_limiter = RateLimiter(rate=100, period=60.0)  # 100 requests per minute
memory_monitor = MemoryMonitor()
health_checks = HealthCheckRegistry()
tracer = RequestTracer()
sanitizer = RequestSanitizer()

# [S-12] Per-route rate limiter — stricter limits for write/agent endpoints
api_rate_limiter = PerRouteRateLimiter(default_rate=100, default_period=60.0)
# Stricter: agent run endpoints (5 req/min per client)
api_rate_limiter.add_route("/api/agents/run", rate=5, period=60.0)
api_rate_limiter.add_route("/api/agents/retry", rate=5, period=60.0)
api_rate_limiter.add_route("/api/agents/cancel", rate=10, period=60.0)
# Stricter: key generation (3 req/min per client)
api_rate_limiter.add_route("/api/keys/new", rate=3, period=60.0)
# Moderate: lead mutation endpoints (20 req/min per client)
api_rate_limiter.add_route("/api/leads/clear", rate=20, period=60.0)
api_rate_limiter.add_route("/api/leads/", rate=20, period=60.0)
# Lenient: read-only endpoints use default (100 req/min)
