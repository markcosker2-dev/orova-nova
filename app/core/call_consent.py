"""Prior-express-consent gate for AI-VOICE outbound calls.

## Why this exists — the legal position, verified 2026-08-06

The calling lane already has a fail-closed DNC gate (`app/core/dnc.py`). DNC is
necessary and **not sufficient**, because it only answers "did this person ask
us to stop?". For an AI voice it is the wrong question. The right one is "did
this person ever say yes?", and by default the answer is no.

Researched against current guidance rather than assumed:

* The **B2B exemption is real but narrow**. Live-human calls to a verified
  business landline are generally exempt from federal telemarketing
  restrictions.
* **It does not survive an artificial voice.** The FCC's February 2024
  declaratory ruling (FCC 24-17) holds that AI-generated voices are
  "artificial" under the TCPA. Prerecorded/artificial-voice calls require
  **prior express consent regardless of the B2B exemption**.
* A **personal mobile used for business is treated as residential**, so the
  business carve-out does not rescue it either.
* Damages are **$500 per call, trebled to $1,500 for a wilful violation**
  (47 U.S.C. §227). Per call — a 100-lead list is a six-figure exposure.

**Measured consequence for THIS pipeline:** of the 23 numbers queued for
calling in production on 2026-08-06, `phonenumbers` classified **20 as
FIXED_OR_MOBILE** — meaning US numbering plus number portability makes it
*impossible to tell from the number alone* whether it is a landline or a cell.
Only 3 were unambiguously business (toll-free). We therefore cannot establish
the exemption applies, even before the artificial-voice problem removes it.

So: **an AI call without recorded consent is not defensible**, and this gate
fails closed the same way the DNC one does.

## What counts as consent

The Fifth Circuit held in February 2026 that prior express consent need not be
*written* — oral consent can suffice. That ruling **binds only the Fifth
Circuit** (TX/LA/MS). OROVA's ICP is California, Oregon and Washington, all in
the **Ninth**, where the FCC's written-consent rule still effectively governs.
This module therefore does not treat "we think they said yes on a call" as
consent.

What it does accept is an unambiguous, attributable, recorded act by the
prospect — the canonical one for this funnel being **a reply to Mark's manual
Instagram DM in which they agree to a call**. That is positive, direct and
unequivocal, it is attributable to a person, and the DM thread is the
independently verifiable record the guidance asks for.

Consent is stored WITH its provenance, because undocumented consent is
worthless in exactly the dispute where it matters.

## What this module deliberately does NOT do

It does not touch `dnc.py`. Suppression and consent are different questions and
both must pass; a suppression entry always wins.
"""
import logging
import time
from typing import Optional

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

_CONSENT_KEY = "ai_call_consent_ledger"

# Channels through which consent can be captured. Anything not on this list is
# rejected rather than silently trusted — a source we cannot point at later is
# not evidence.
VALID_CONSENT_SOURCES = frozenset({
    "ig_dm_reply",       # replied to Mark's manual DM agreeing to a call
    "inbound_call",      # they rang us — consent is the call itself
    "web_form",          # submitted a form asking to be contacted
    "email_reply",       # replied to correspondence agreeing to a call
    "manual",            # Mark recorded it himself; detail must say how
})


def _normalize(phone: str) -> str:
    """Digits only, with a leading + preserved.

    Mirrors dnc._normalize deliberately so the two gates agree on what "the
    same number" means. (dnc.py is not modified here — see module docstring.)
    """
    p = (phone or "").strip()
    digits = "".join(ch for ch in p if ch.isdigit())
    if not digits:
        return ""
    return ("+" + digits) if p.startswith("+") else digits


def _same_number(a: str, b: str) -> bool:
    """Compare two numbers ignoring a missing country code.

    '+15035757663' and '5035757663' are the same line written two ways, and a
    consent record must not be missed because of it. Compares the last ten
    digits, which is the NANP subscriber number.
    """
    da = "".join(ch for ch in (a or "") if ch.isdigit())
    db = "".join(ch for ch in (b or "") if ch.isdigit())
    if not da or not db:
        return False
    return da[-10:] == db[-10:]


async def record_call_consent(phone: str, source: str, detail: str = "",
                              actor: str = "") -> bool:
    """Record that this number's owner agreed to be called.

    `source` must be one of VALID_CONSENT_SOURCES. `detail` should carry the
    verbatim evidence where it exists (the DM text, the form submission id) —
    consent that cannot be pointed at later is not consent.

    Returns False and logs loudly on a bad source or a write failure, because
    a silently-lost consent record means a lawful call gets blocked, and a
    silently-invented one means an unlawful call gets made.
    """
    norm = _normalize(phone)
    if not norm:
        logger.error("[CONSENT] Refused to record consent for an empty number.")
        return False
    if source not in VALID_CONSENT_SOURCES:
        logger.error(f"[CONSENT] Refused to record consent from unrecognised "
                     f"source {source!r}. Valid: {sorted(VALID_CONSENT_SOURCES)}")
        return False
    try:
        ledger = await DatabaseManager.get_state(_CONSENT_KEY, []) or []
        entry = {
            "phone": norm,
            "source": source,
            "detail": (detail or "")[:2000],
            "actor": actor or "",
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        ledger.append(entry)
        await DatabaseManager.set_state(_CONSENT_KEY, ledger)
        logger.info(f"[CONSENT] Recorded call consent via {source} "
                    f"(actor: {actor or 'n/a'}).")
        return True
    except Exception as e:
        logger.error(f"[CONSENT] FAILED to record call consent: {e}")
        return False


async def consent_record(phone: str) -> Optional[dict]:
    """The most recent consent entry for this number, or None."""
    norm = _normalize(phone)
    if not norm:
        return None
    try:
        ledger = await DatabaseManager.get_state(_CONSENT_KEY, []) or []
    except Exception as e:
        logger.error(f"[CONSENT] Ledger read failed for {phone} ({e}).")
        return None
    hits = [e for e in ledger
            if isinstance(e, dict) and _same_number(e.get("phone", ""), norm)]
    return hits[-1] if hits else None


async def has_call_consent(phone: str) -> bool:
    """True only if prior express consent is on record for this number.

    Fails CLOSED: an empty number, a missing record, or a lookup error all
    resolve to False. The cost of skipping one call is nil; the cost of an
    undocumented AI call is $500-$1,500 statutory damages.
    """
    if not _normalize(phone):
        return False
    try:
        return await consent_record(phone) is not None
    except Exception as e:
        logger.error(f"[CONSENT] Lookup failed for {phone} ({e}) — "
                     f"blocking call (fail-closed).")
        return False


async def ai_call_allowed(phone: str) -> tuple:
    """(allowed, reason) — the single gate the AI calling lane must consult.

    BOTH conditions must hold, and suppression always wins:
      · not on the DNC/opt-out list  (app/core/dnc.py, unmodified)
      · prior express consent on record for an artificial-voice call

    Returns a reason string on refusal so the lane can log WHY a number was
    skipped, rather than leaving a silent gap the way the email path once did.
    """
    norm = _normalize(phone)
    if not norm:
        return False, "no phone number"

    # Suppression first — an opt-out overrides any earlier consent.
    try:
        from app.core.dnc import is_suppressed
        if await is_suppressed(phone):
            return False, "on the DNC/opt-out list (or lookup failed; fail-closed)"
    except Exception as e:
        logger.error(f"[CONSENT] DNC check failed for {phone} ({e}) — "
                     f"blocking call (fail-closed).")
        return False, "DNC lookup error (fail-closed)"

    rec = await consent_record(phone)
    if rec is None:
        return False, ("no prior express consent on record — an AI/artificial "
                       "voice call requires it regardless of the B2B exemption "
                       "(FCC 24-17)")
    return True, f"consent via {rec.get('source')} on {rec.get('recorded_at')}"
