"""
Circuit Breaker — Agent Execution Loop Guard
==============================================
Enforces hard termination limits on agentic task execution:
- Max 20 steps per task (hard ceiling)
- Max 10,000 tokens per task
- Infinite loop detection (repeated tool calls with same parameters)
- Memory leak prevention (context budget enforcement)
- Cooldown periods between tasks to prevent runaway agents

Integrated into TaskPlanner.execute() as a non-negotiable guardrail layer.
"""

import time
import logging
import json
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class TripReason(str, Enum):
    """Why the circuit breaker tripped."""
    MAX_STEPS = "max_steps"
    MAX_TOKENS = "max_tokens"
    LOOP_DETECTED = "loop_detected"
    TIMEOUT = "timeout"
    MEMORY_OVERFLOW = "memory_overflow"
    REPETITIVE_CALLS = "repetitive_calls"
    MANUAL_TRIP = "manual_trip"


@dataclass
class CircuitState:
    """Current state of a circuit breaker instance."""
    tripped: bool = False
    trip_reason: Optional[TripReason] = None
    trip_time: Optional[float] = None
    step_count: int = 0
    total_tokens: int = 0
    total_chars: int = 0
    last_call_hash: str = ""
    repeat_count: int = 0
    last_activity_time: float = 0.0
    cooldown_until: float = 0.0
    consecutive_loops: int = 0
    tool_call_history: List[Dict] = field(default_factory=list)


@dataclass
class CircuitBreakerConfig:
    """Configuration for the execution circuit breaker."""
    max_steps: int = 20  # Hard ceiling: 20 tool calls per task
    max_total_tokens: int = 10000  # Hard ceiling: 10K tokens per task
    max_context_chars: int = 20000  # Context budget before forced compression
    max_repeat_calls: int = 3  # Same call + same args = loop detection
    task_timeout_seconds: int = 300  # 5 minutes max per task
    cooldown_seconds: int = 30  # Wait 30s after trip before allowing retry
    max_consecutive_loops: int = 2  # After 2 loops, escalate to permanent blocked
    cooldown_budget_enabled: bool = True
    token_budget_enabled: bool = True


DEFAULT_CIRCUIT_CONFIG = CircuitBreakerConfig()


class ExecutionCircuitBreaker:
    """
    Non-negotiable execution guard for agentic task loops.
    Trips when any limit is exceeded and enforces cooldown.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or DEFAULT_CIRCUIT_CONFIG
        self.sessions: Dict[str, CircuitState] = defaultdict(CircuitState)
        self.global_cooldown_until: float = 0.0
        self.global_consecutive_trips: int = 0
        self.trip_log: List[Dict] = []
        self.max_trip_log: int = 1000
        self._manual_override: bool = False

    def start_session(self, session_id: str):
        """Initialize a new session."""
        # Check global cooldown
        if not self._manual_override and self.global_cooldown_until > time.time():
            remaining = int(self.global_cooldown_until - time.time())
            logger.warning(f"[CIRCUIT] Global cooldown active for {remaining}s more")
            raise CircuitBreakerTripped(
                reason=TripReason.TIMEOUT,
                message=f"Global cooldown active for {remaining}s"
            )

        self.sessions[session_id] = CircuitState(
            last_activity_time=time.time()
        )
        logger.info(f"[CIRCUIT] Session {session_id} started")

    def check_call(self, session_id: str, fn_name: str, fn_args: Dict[str, Any],
                   token_count: int = 0, char_count: int = 0) -> bool:
        """
        Check if a tool call is allowed. Returns True if allowed, False if circuit is open.
        Raises CircuitBreakerTripped if hard limits are exceeded.
        """
        state = self.sessions.get(session_id)
        if not state:
            logger.warning(f"[CIRCUIT] Unknown session {session_id}, allowing call")
            return True

        # 1. Step count check (hard ceiling)
        if state.step_count >= self.config.max_steps:
            self._trip(session_id, TripReason.MAX_STEPS,
                       f"Step limit: {state.step_count}/{self.config.max_steps}")
            return False

        # 2. Token budget check
        if self.config.token_budget_enabled:
            new_total = state.total_tokens + token_count
            if new_total > self.config.max_total_tokens:
                self._trip(session_id, TripReason.MAX_TOKENS,
                           f"Token budget: {new_total}/{self.config.max_total_tokens}")
                return False

        # 3. Context char budget check
        new_total_chars = state.total_chars + char_count
        if new_total_chars > self.config.max_context_chars:
            self._trip(session_id, TripReason.MEMORY_OVERFLOW,
                       f"Context budget: {new_total_chars}/{self.config.max_context_chars}")
            return False

        # 4. Repeat call detection (loop prevention)
        call_hash = self._compute_call_hash(fn_name, fn_args)
        if call_hash == state.last_call_hash:
            state.repeat_count += 1
            if state.repeat_count >= self.config.max_repeat_calls:
                self._trip(session_id, TripReason.LOOP_DETECTED,
                           f"Repeated call #{state.repeat_count}: {fn_name}")
                return False
        else:
            state.repeat_count = 0
            state.last_call_hash = call_hash

        # 5. Timeout check
        elapsed = time.time() - state.last_activity_time
        if elapsed > self.config.task_timeout_seconds:
            self._trip(session_id, TripReason.TIMEOUT,
                       f"Task timeout: {elapsed:.0f}s/{self.config.task_timeout_seconds}s")
            return False

        # Update state
        state.step_count += 1
        state.total_tokens += token_count
        state.total_chars += char_count
        state.last_activity_time = time.time()

        # Track tool call
        state.tool_call_history.append({
            "tool_name": fn_name,
            "step": state.step_count,
            "timestamp": time.time(),
        })

        return True

    def record_tokens(self, session_id: str, tokens: int):
        """Accumulate token usage."""
        state = self.sessions.get(session_id)
        if state:
            state.total_tokens += tokens

    def complete_session(self, session_id: str, status: str = "completed"):
        """Gracefully end a session (release resources)."""
        state = self.sessions.pop(session_id, None)
        if state:
            logger.info(f"[CIRCUIT] Session {session_id} completed: {status} ({state.step_count} steps)")

    def _trip(self, session_id: str, reason: TripReason, message: str):
        """Trip the circuit breaker for a session."""
        state = self.sessions.get(session_id)
        if state:
            state.tripped = True
            state.trip_reason = reason
            state.trip_time = time.time()
            state.cooldown_until = time.time() + self.config.cooldown_seconds

        # Track globally
        self.trip_log.append({
            "session_id": session_id,
            "reason": reason.value,
            "message": message,
            "timestamp": time.time(),
        })
        if len(self.trip_log) > self.max_trip_log:
            self.trip_log = self.trip_log[-self.max_trip_log:]

        self.global_consecutive_trips += 1

        # After max consecutive loops, apply global cooldown
        if self.global_consecutive_trips >= self.config.max_consecutive_loops:
            self.global_cooldown_until = time.time() + self.config.cooldown_seconds * 3
            logger.warning(f"[CIRCUIT] Global cooldown activated after {self.global_consecutive_trips} consecutive trips")
            self.global_consecutive_trips = 0

        logger.warning(f"[CIRCUIT] TRIPPED [{reason.value}] {session_id}: {message}")

    def is_tripped(self, session_id: str) -> Tuple[bool, Optional[str]]:
        """Check if a session is currently tripped."""
        # Global cooldown check
        if self.global_cooldown_until > time.time():
            return True, "Global cooldown active"

        state = self.sessions.get(session_id)
        if not state:
            return False, None

        if not state.tripped:
            return False, None

        # Check cooldown expiration
        if state.cooldown_until > time.time():
            remaining = int(state.cooldown_until - time.time())
            return True, f"Cooldown: {remaining}s remaining"

        # Cooldown expired: reset and allow
        self._reset_session(session_id)
        return False, None

    def _reset_session(self, session_id: str):
        """Reset a session after cooldown."""
        state = self.sessions.get(session_id)
        if state:
            logger.info(f"[CIRCUIT] Resetting session {session_id} after cooldown")
            state.tripped = False
            state.trip_reason = None
            state.trip_time = None
            state.repeat_count = 0
            state.last_call_hash = ""

    def manual_trip(self, session_id: str, reason: str = "manual_override"):
        """Manually trip a session."""
        self._trip(session_id, TripReason.MANUAL_TRIP, reason)

    def manual_reset(self, session_id: Optional[str] = None):
        """Admin override to reset circuit breaker."""
        if session_id:
            self._reset_session(session_id)
        else:
            self.global_cooldown_until = 0.0
            self.global_consecutive_trips = 0
            logger.info("[CIRCUIT] Global reset applied")

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """Get current status of a session."""
        state = self.sessions.get(session_id)
        if not state:
            return {"session_id": session_id, "status": "unknown"}

        is_open, reason = self.is_tripped(session_id)
        return {
            "session_id": session_id,
            "status": "open" if is_open else "closed",
            "reason": reason,
            "steps": state.step_count,
            "total_tokens": state.total_tokens,
            "total_chars": state.total_chars,
            "repeat_count": state.repeat_count,
            "last_activity": state.last_activity_time,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get overall circuit breaker statistics."""
        total_sessions = len(self.sessions)
        active_tripped = sum(
            1 for s in self.sessions.values()
            if s.tripped and s.cooldown_until > time.time()
        )

        # Aggregate trip reasons
        reason_counts = defaultdict(int)
        for entry in self.trip_log:
            reason_counts[entry["reason"]] += 1

        return {
            "total_active_sessions": total_sessions,
            "active_tripped": active_tripped,
            "total_trips_logged": len(self.trip_log),
            "global_cooldown": self.global_cooldown_until > time.time(),
            "trip_reason_breakdown": dict(reason_counts),
            "recent_trips": self.trip_log[-10:] if self.trip_log else [],
        }

    def _compute_call_hash(self, fn_name: str, fn_args: dict) -> str:
        """Compute a hash of function name + args for repeat detection."""
        payload = json.dumps({"fn": fn_name, "args": fn_args}, sort_keys=True)
        return hashlib.md5(payload.encode()).hexdigest()


class CircuitBreakerTripped(Exception):
    """Exception raised when a circuit breaker trips."""
    def __init__(self, reason: TripReason, message: str):
        self.reason = reason
        self.message = message
        super().__init__(f"Circuit breaker tripped [{reason.value}]: {message}")


# Global instance
execution_circuit_breaker = ExecutionCircuitBreaker()