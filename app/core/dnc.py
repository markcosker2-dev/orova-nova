"""DNC / do-not-call suppression gate for the outbound calling lane.

The calling lane had only a daily-count cap — no consent/DNC guardrail — which is
real TCPA exposure ($500-1,500 statutory damages per call). This adds a fail-CLOSED
suppression check: any number on the DNC list (opt-outs, manual entries) — or a
missing number — is never dialed. National-registry scrubbing needs a paid API and
is tracked as a follow-up; this internal list is the always-on floor.
"""
import os
import time
import logging

import httpx

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

_DNC_KEY = "dnc_suppression_list"
DNC_CACHE_TTL_DAYS = 31          # TCPA safe-harbor: re-scrub <=31 days before calling
_DNC_HTTP_TIMEOUT = 8.0
_unconfigured_logged = False


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


async def is_dnc_registered(phone: str) -> bool:
    """True if `phone` is on the National DNC Registry and must NOT be called.

    An ADDITIONAL gate on top of is_suppressed (the manual opt-out list).
    Env-gated by DNC_SCRUB_API_KEY + DNC_SCRUB_URL (a national-registry scrub
    provider). Unlike is_suppressed, this FAILS OPEN — returns False (don't
    block) when unconfigured or on any error — because there is no registry
    data source on the $0 tier yet, so it must never break the live call lane
    by its absence. Results cache <=31 days (TCPA safe-harbor cadence).
    """
    global _unconfigured_logged
    norm = _normalize(phone)
    if not norm:
        return False  # empty numbers are already fail-closed by is_suppressed
    api_key = os.getenv("DNC_SCRUB_API_KEY")
    url = os.getenv("DNC_SCRUB_URL")
    if not api_key or not url:
        if not _unconfigured_logged:
            logger.info("[DNC] National registry scrub unconfigured (set DNC_SCRUB_API_KEY + DNC_SCRUB_URL) — registry check skipped, opt-out list still enforced.")
            _unconfigured_logged = True
        return False

    cache_key = f"dnc_registry_cache:{norm}"
    try:
        cached = await DatabaseManager.get_state(cache_key)
        if cached and (time.time() - cached.get("ts", 0)) < DNC_CACHE_TTL_DAYS * 86400:
            return bool(cached.get("registered"))
    except Exception:
        pass  # cache miss/unavailable -> live lookup

    try:
        async with httpx.AsyncClient(timeout=_DNC_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params={"phone": norm},
                                    headers={"Authorization": f"Bearer {api_key}"})
        if resp.status_code != 200:
            logger.warning(f"[DNC] Registry provider returned {resp.status_code} — failing open (not blocking).")
            return False
        data = resp.json()
        registered = bool(data.get("on_registry") if "on_registry" in data else data.get("registered"))
        try:
            await DatabaseManager.set_state(cache_key, {"registered": registered, "ts": time.time()})
        except Exception:
            pass
        return registered
    except Exception as e:
        logger.warning(f"[DNC] Registry lookup failed ({e}) — failing open (not blocking).")
        return False
