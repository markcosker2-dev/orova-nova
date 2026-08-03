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
import phonenumbers

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

_DNC_KEY = "dnc_suppression_list"
DNC_CACHE_TTL_DAYS = 31          # TCPA safe-harbor: re-scrub <=31 days before calling
_DNC_HTTP_TIMEOUT = 8.0
_unconfigured_logged = False


_DEFAULT_REGION = "US"


def _normalize(phone: str) -> str:
    """Canonical E.164 key for a number, or "" if it cannot be resolved to one.

    ── The bug this replaces (2026-08-03) ──────────────────────────────────
    The previous implementation reduced to digits and kept a leading "+"
    verbatim, without ever reconciling the US country code. One number
    therefore produced several non-matching keys, and a suppressed number
    queried in a different format was reported as NOT suppressed:

        stored '+13239352985' -> is_suppressed('+13239352985')   = True
        stored '+13239352985' -> is_suppressed('3239352985')     = False  BYPASS
        stored '+13239352985' -> is_suppressed('(323) 935-2985') = False  BYPASS
        stored '+13239352985' -> is_suppressed('13239352985')    = False  BYPASS
        stored '+13239352985' -> is_suppressed('323-935-2985')   = False  BYPASS

    4 of 6 real-world formats bypassed the gate. Production was safe only by
    coincidence: every ingestion path already normalises to E.164
    (lead_gen_v3._normalize_phone_to_e164, light_enrich._normalize_phone_to_e164,
    lead_finder._normalize_phone) and the sole DNC writer is the Retell webhook
    (app/main.py:1124), also E.164. Anything reaching the dial lane in another
    shape — a Sheets/backup restore, a CSV import, a legacy row predating
    normalisation, or a future manual DNC entry UI — would have been dialled
    despite being on the list.

    The old unit test could not catch it: it asserted the two mismatched
    outputs as CORRECT ("(323) 935-2985" -> "3239352985" alongside
    "+1 323 935 2985" -> "+13239352985"), i.e. it encoded the defect.

    ── Why this is strictly a strengthening ────────────────────────────────
    Fail-closed behaviour is preserved exactly and extended, never relaxed:
      · ""/None            -> "" -> is_suppressed True (unchanged)
      · unparseable input  -> "" -> is_suppressed True (unchanged for "abc";
        NEWLY blocked for digit-bearing junk like "123" or "ext 456", which
        previously produced a key that matched nothing and so was dialable)
      · DB error           -> True, handled by the caller (unchanged)
    No input that was previously BLOCKED becomes dialable.

    `phonenumbers` is already a hard dependency (lead_validator.py:27 formats
    to E164 with it), so this introduces no new package.
    """
    raw = (phone or "").strip()
    if not raw:
        return ""
    try:
        # A leading "+" means the number carries its own country code; anything
        # else is interpreted against the US plan, which is the only geography
        # this system dials (ADR-0012: US West Coast).
        parsed = phonenumbers.parse(raw, None if raw.startswith("+") else _DEFAULT_REGION)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        pass  # fall through to the NANP shape check below
    # Fallback for values phonenumbers rejects as invalid but which are still
    # unambiguous NANP shapes (legacy rows, test fixtures, partially-cleaned
    # imports). Store and query must agree on these too, or the bypass returns.
    # Deliberately narrow: never invent a country code for any other length.
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return ""


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


# ── Email suppression ────────────────────────────────────────────────────────
# The same defect the phone gate fixed, on the other channel: agentmail_skill
# DETECTS opt-out language ("unsubscribe", "remove me", "no thanks") and
# classifies the reply COLD so nothing auto-replies — but nothing PERSISTED it,
# and send_outreach had no pre-send check. A later drip cycle could therefore
# email someone who had explicitly asked to be left alone, which is the exact
# CAN-SPAM failure the footer's opt-out promise is supposed to prevent
# (15 U.S.C. §7704 requires honouring an opt-out within 10 business days).
#
# Kept in this module rather than app/core/compliance.py: that module is a
# second, unused implementation of CAN-SPAM validation, and the live footer
# already lives in agentmail_skill. Adding a third owner would repeat the
# divergence this repo has been bitten by before.
_EMAIL_SUPPRESSION_KEY = "email_suppression_list"


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


async def is_email_suppressed(email: str) -> bool:
    """True if `email` must NOT be sent to.

    Fails CLOSED on a lookup error — the cost of skipping one send is nil, the
    cost of mailing someone who opted out is a compliance breach. An EMPTY
    address returns True as well: there is nothing to send to.
    """
    norm = _normalize_email(email)
    if not norm:
        return True
    try:
        lst = await DatabaseManager.get_state(_EMAIL_SUPPRESSION_KEY, []) or []
        return norm in {_normalize_email(x) for x in lst}
    except Exception as e:
        logger.error(f"[SUPPRESS] Email lookup failed ({e}) — blocking send (fail-closed).")
        return True


async def add_email_suppression(email: str, reason: str = "") -> bool:
    """Record an email opt-out. Idempotent."""
    norm = _normalize_email(email)
    if not norm or "@" not in norm:
        return False
    try:
        lst = await DatabaseManager.get_state(_EMAIL_SUPPRESSION_KEY, []) or []
        if norm not in {_normalize_email(x) for x in lst}:
            lst.append(norm)
            await DatabaseManager.set_state(_EMAIL_SUPPRESSION_KEY, lst)
            logger.info(f"[SUPPRESS] Email opt-out recorded (reason: {reason or 'n/a'}).")
        return True
    except Exception as e:
        # Loud: a lost opt-out is a compliance problem, not a cosmetic one.
        logger.error(f"[SUPPRESS] FAILED to record email opt-out: {e}")
        return False


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
