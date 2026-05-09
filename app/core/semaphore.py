"""
semaphore.py — OROVA Global Execution Semaphore
Single source of truth for all RAM-heavy skill concurrency control.
Ensures Render (512MB RAM) is protected from OOM kills.
"""

import asyncio
import functools
import logging
import time
from contextlib import asynccontextmanager
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ── [P6] The One Semaphore (Limit = 1) ──
RAM_HEAVY_SEMAPHORE = asyncio.Semaphore(1)
SEMAPHORE_TIMEOUT_SECONDS = 120

@asynccontextmanager
async def ram_guarded(skill_name: str = "unknown"):
    """Context manager for RAM-heavy operations with timeout."""
    t_start = time.monotonic()
    logger.info(f"[Semaphore] '{skill_name}' waiting for RAM slot...")

    try:
        await asyncio.wait_for(RAM_HEAVY_SEMAPHORE.acquire(), timeout=SEMAPHORE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(f"[Semaphore] '{skill_name}' timed out after {SEMAPHORE_TIMEOUT_SECONDS}s. Aborting.")
        raise TimeoutError(f"RAM slot busy. Could not start '{skill_name}'.")

    logger.info(f"[Semaphore] '{skill_name}' acquired slot (Waited {time.monotonic()-t_start:.1f}s).")
    try:
        yield
    finally:
        RAM_HEAVY_SEMAPHORE.release()
        logger.info(f"[Semaphore] '{skill_name}' released slot.")

def ram_heavy(skill_name: str | None = None):
    """Decorator for RAM-heavy async functions."""
    def decorator(fn: Callable) -> Callable:
        name = skill_name or fn.__name__
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async with ram_guarded(name):
                return await fn(*args, **kwargs)
        return wrapper
    return decorator

def semaphore_status() -> dict:
    """Returns current semaphore health for telemetry."""
    return {
        "limit": 1,
        "available": RAM_HEAVY_SEMAPHORE._value,
        "locked": RAM_HEAVY_SEMAPHORE._value == 0
    }
