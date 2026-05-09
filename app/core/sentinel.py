"""
SentinelNotify — credential failure escalation layer.
When any OAuth skill cannot refresh, Nova surfaces the failure
to the Admin via Telegram instead of silently crashing.
"""

import logging
import asyncio
from datetime import datetime
from functools import wraps
from typing import Callable, Optional

# Assuming this exists in your project structure
async def send_admin_message(text: str):
    import os
    import httpx
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("ADMIN_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

logger = logging.getLogger("sentinel")

SENTINEL_COOLDOWN_SECONDS = 3600  # Suppress duplicate alerts for same skill within 1h
_last_alert: dict[str, datetime] = {}

async def sentinel_notify(skill_name: str, error: str) -> None:
    """
    Dispatch a Telegram alert to the Admin when a credential fails.
    Suppresses duplicates within the cooldown window.
    """
    now = datetime.utcnow()
    last = _last_alert.get(skill_name)
    if last and (now - last).total_seconds() < SENTINEL_COOLDOWN_SECONDS:
        logger.debug(f"[Sentinel] Suppressed duplicate alert for {skill_name}.")
        return

    _last_alert[skill_name] = now

    message = (
        f"⚠️ *OROVA Sentinel: Credential Failure*\n"
        f"Skill: `{skill_name}`\n"
        f"Error: `{error}`\n\n"
        f"Action Required: Re-authenticate via the platform dashboard.\n"
        f"Time: {now.strftime('%Y-%m-%d %H:%M UTC')}"
    )
    try:
        await send_admin_message(message)
        logger.warning(f"[Sentinel] Alert dispatched for {skill_name}.")
    except Exception as e:
        logger.error(f"[Sentinel] Failed to dispatch alert: {e}")

def sentinel_guarded(skill_name: str):
    """
    Decorator. Wraps any OAuth-dependent function.
    On credential failure, fires SentinelNotify and returns None gracefully.
    """
    def decorator(fn: Callable):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(*args, **kwargs)
                return fn(*args, **kwargs)
            except Exception as e:
                err_str = str(e)
                # Detect credential-class failures specifically
                if any(kw in err_str.lower() for kw in (
                    "invalid_grant", "token expired", "refresh error",
                    "credentials", "unauthorized", "401"
                )):
                    await sentinel_notify(skill_name, err_str)
                    return None  # Caller must handle None as a dead-service signal
                raise  # Re-raise non-credential errors normally
        return wrapper
    return decorator
