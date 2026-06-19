"""
app/core/rate_limiter.py — Token Bucket Rate Limiter
"""
from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger("rate_limiter")


class TokenBucket:
    """Simple token bucket rate limiter."""

    def __init__(self, capacity: float, refill_rate: float) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.monotonic()

    async def acquire(self, tokens: float = 1.0, timeout_s: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            await asyncio.sleep(0.1)
        return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now


class RateLimiters:
    """Collection of named token buckets."""

    def __init__(self) -> None:
        # AgentMail sends: 100/hour = ~1.67/min
        self.agentmail_send = TokenBucket(capacity=10.0, refill_rate=100 / 3600)
        # LLM calls: 30/min
        self.llm = TokenBucket(capacity=5.0, refill_rate=30 / 60)
        # Scraper pages: 20/min
        self.scraper = TokenBucket(capacity=10.0, refill_rate=20 / 60)

    async def acquire(self, name: str, tokens: float = 1.0, timeout_s: float = 60.0) -> bool:
        bucket = getattr(self, name, None)
        if bucket is None:
            log.warning("Unknown rate limiter bucket: %s", name)
            return True
        return await bucket.acquire(tokens, timeout_s)


limiters = RateLimiters()