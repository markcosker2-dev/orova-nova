"""
app/services/call_manager.py
Retell AI V2 outbound calling.

FIXES APPLIED:
  - from_number now required (was missing — caused silent failures)
  - agent_id replaces override_agent_id (V2 param name)
  - E.164 normalisation before every call (prevents silent Retell errors)
  - Calling hours enforced (Mon–Fri, 9am–5pm Eastern only)
  - Weekends blocked
"""

import os
import logging
from datetime import datetime
from typing import Optional

try:
    from retell import Retell
except ImportError:
    Retell = None
    logging.warning("retell package not installed. Run: pip install retell-sdk")

from app.core.ai_client import UnifiedAIClient
from app.core.phone_utils import to_e164

logger = logging.getLogger("orova.calls")

_retell_client = None


def _get_retell():
    global _retell_client
    if Retell is None:
        return None
    if _retell_client is None:
        key = os.getenv("RETELL_API_KEY")
        if not key:
            logger.warning("[CALLS] RETELL_API_KEY not set")
            return None
        _retell_client = Retell(api_key=key)
    return _retell_client


def _is_calling_hours(phone_number: str = None) -> bool:
    """
    Check calling hours. If phone_number provided, uses prospect's local timezone.
    Otherwise falls back to US Eastern business hours.
    Mon–Fri, 9am–5pm only.
    """
    try:
        if phone_number:
            from app.core.smart_calling import calling_hours
            tz = calling_hours.get_prospect_timezone(phone_number)
            return calling_hours.is_prospect_calling_hours(tz)
    except Exception:
        pass

    # Fallback: US Eastern
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = datetime.now()
    if now.weekday() >= 5:
        return False
    start = int(os.getenv("CALL_HOUR_START", 9))
    end   = int(os.getenv("CALL_HOUR_END",   17))
    return start <= now.hour < end





async def draft_reminder_call(prospect_name: str, meeting_time: str,
                               meeting_topic: str) -> str:
    """Generate a personalised call script using the AI client."""
    system_prompt = (
        "You are an expert sales script writer for a premium AI agency called OROVA. "
        "Write a short, natural, 1-2 sentence opening line for a phone call "
        "reminding a prospect about an upcoming meeting. "
        "Tone: professional, direct, confident. No fluff."
    )
    user_prompt = (
        f"Prospect: {prospect_name}\nTime: {meeting_time}\nTopic: {meeting_topic}"
    )
    ai = UnifiedAIClient()
    response = await ai.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ])
    return response.content or "Looking forward to our call."


async def execute_call(phone_number: str, prospect_name: str,
                        script_content: str) -> Optional[str]:
    """
    Trigger an outbound call via Retell AI V2.

    FIXES:
      1. E.164 normalisation — returns None early if number is invalid
      2. from_number required — reads RETELL_FROM_NUMBER from env
      3. agent_id param — V2 uses agent_id not override_agent_id
      4. Calling hours enforced — will not call outside 9am–5pm ET Mon–Fri
    """
    retell = _get_retell()
    if not retell:
        logger.error("[CALLS] Retell client not initialised")
        return None

    # Enforce calling hours (prospect's local time)
    if not _is_calling_hours(phone_number):
        logger.info("[CALLS] Outside prospect's calling hours — call queued for next window")
        return None

    # E.164 normalisation — hard requirement for Retell V2
    phone_e164 = to_e164(phone_number)
    if not phone_e164:
        logger.error(
            f"[CALLS] Cannot normalise '{phone_number}' to E.164 — call skipped"
        )
        return None

    from_number = os.getenv("RETELL_FROM_NUMBER", "")
    from_e164   = to_e164(from_number)
    if not from_e164:
        logger.error(
            f"[CALLS] RETELL_FROM_NUMBER '{from_number}' is not valid E.164. "
            "Update your .env — format: +12137774445"
        )
        return None

    agent_id = os.getenv("RETELL_AGENT_ID")
    if not agent_id:
        logger.error("[CALLS] RETELL_AGENT_ID not set")
        return None

    try:
        call_response = retell.call.create_phone_call(
            from_number=from_e164,        # FIX: was missing entirely
            to_number=phone_e164,          # FIX: now E.164 validated
            agent_id=agent_id,             # FIX: V2 param (was override_agent_id)
            retell_llm_dynamic_variables={
                "prospect_name":  prospect_name,
                "custom_script":  script_content,
                "call_context":   "Meeting reminder. Professional and concise.",
            },
        )
        call_id = call_response.call_id
        logger.info(f"[CALLS] Call initiated → {phone_e164} call_id={call_id}")
        return call_id

    except Exception as e:
        logger.error(f"[CALLS] Retell call failed: {e}")
        return None
