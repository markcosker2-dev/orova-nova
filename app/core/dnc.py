"""DNC / do-not-call suppression gate for the outbound calling lane.

The calling lane had only a daily-count cap — no consent/DNC guardrail — which is
real TCPA exposure ($500-1,500 statutory damages per call). This adds a fail-CLOSED
suppression check: any number on the DNC list (opt-outs, manual entries) — or a
missing number — is never dialed. National-registry scrubbing needs a paid API and
is tracked as a follow-up; this internal list is the always-on floor.
"""
import logging

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

_DNC_KEY = "dnc_suppression_list"


def _normalize(phone: str) -> str:
    """Reduce to digits (keeping a leading +) so formatting differences can't
    slip a suppressed number past the check."""
    p = (phone or "").strip()
    digits = "".join(ch for ch in p if ch.isdigit())
    if not digits:
        return ""
    return ("+" + digits) if p.startswith("+") else digits


async def is_suppressed(phone: str) -> bool:
    """True if `phone` must NOT be called. Fails CLOSED — a missing number or a
    lookup error resolves to suppressed, so nothing unvetted is ever dialed."""
    norm = _normalize(phone)
    if not norm:
        return True
    try:
        dnc = await DatabaseManager.get_state(_DNC_KEY, []) or []
        return norm in {_normalize(x) for x in dnc}
    except Exception as e:
        logger.error(f"[DNC] Suppression lookup failed for {phone} ({e}) — blocking call (fail-closed).")
        return True


async def add_suppression(phone: str, reason: str = "") -> bool:
    """Add a number to the DNC list (opt-out / manual). Idempotent."""
    norm = _normalize(phone)
    if not norm:
        return False
    try:
        dnc = await DatabaseManager.get_state(_DNC_KEY, []) or []
        if norm not in {_normalize(x) for x in dnc}:
            dnc.append(norm)
            await DatabaseManager.set_state(_DNC_KEY, dnc)
            logger.info(f"[DNC] Added a number to the suppression list (reason: {reason or 'n/a'}).")
        return True
    except Exception as e:
        logger.error(f"[DNC] Failed to add to suppression list: {e}")
        return False
