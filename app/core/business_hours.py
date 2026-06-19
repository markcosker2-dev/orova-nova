"""
app/core/business_hours.py — PST Business Hours Enforcement
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import wraps
from zoneinfo import ZoneInfo

from app.config import settings

log = logging.getLogger("business_hours")

PST = ZoneInfo("America/Los_Angeles")


def is_business_hours() -> bool:
    """Check if current time is within configured PST business hours."""
    now = datetime.now(PST)
    return settings.biz_hours_start <= now.hour < settings.biz_hours_end


def require_business_hours(func):
    """Decorator: return None if outside business hours."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not is_business_hours():
            log.info("Outside business hours \u2014 skipping %s", func.__name__)
            return None
        return await func(*args, **kwargs)
    return wrapper


async def wait_until_business_hours() -> None:
    """Block until next business hours start."""
    while not is_business_hours():
        now = datetime.now(PST)
        next_start = now.replace(
            hour=settings.biz_hours_start, minute=0, second=0, microsecond=0
        )
        if now.hour >= settings.biz_hours_end:
            # Advance to tomorrow
            next_start = next_start.replace(day=now.day + 1)
        sleep_s = (next_start - now).total_seconds()
        if sleep_s > 0:
            log.info("Waiting %.0fs until business hours", sleep_s)
            await asyncio.sleep(min(sleep_s, 300))