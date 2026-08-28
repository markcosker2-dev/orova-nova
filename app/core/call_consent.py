"""Line-type + consent gate for AI-VOICE outbound calls.

## The legal position, corrected 2026-08-06

An earlier version of this module asserted that AI cold calling is simply
unlawful without consent. **That was too broad, and it was wrong.** The
restriction is *line-type dependent*, and the correction matters because the
over-broad rule would have blocked calls that are perfectly lawful.

Two SEPARATE statutory provisions, commonly conflated:

* **§227(b)(1)(B)** — artificial/prerecorded voice to a **"residential
  telephone line"** requires prior express consent. By its own text this does
  **not** reach a genuine business landline.
* **§227(b)(1)(A)(iii)** — a separate clause reaching *any* number assigned to
  **cellular** service, **or "any service for which the called party is charged
  for the call."** This one is not limited to residential use, so a business's
  mobile is squarely covered. Toll-free numbers are arguably covered too, since
  the called party pays — which makes them the *worst* AI-call candidates, not
  the safest, counterintuitive as that is.

Separately, the **Do-Not-Call rules (§227(c))** protect *residential*
subscribers, so B2B calling is largely outside them. DNC compliance alone,
however, says nothing about the artificial-voice question above.

The FCC's February 2024 declaratory ruling (FCC 24-17) confirms AI-generated
voices count as "artificial", so all of the above binds an AI caller
specifically. Damages: **$500 per call, trebled to $1,500 for a wilful
violation** (47 U.S.C. §227).

### So the rule this module implements

    verified business LANDLINE  ->  lawful, no consent required
    CELL / TOLL-FREE / UNKNOWN  ->  prior express consent required

### The real operational blocker, measured

Of the 23 numbers queued for calling in production on 2026-08-06:

    20  geographic, landline-or-cell UNKNOWN
     3  toll-free (called party charged -> treat as consent-required)

`phonenumbers` returns FIXED_OR_MOBILE for **every** US geographic number —
number portability destroyed prefix-based inference years ago. Determining
line type for real needs a carrier/HLR lookup, which is a paid API.

**That is the actual blocker: not legality, but not knowing which numbers are
cells.** Until a line type is known, this gate treats a number as
consent-required, because guessing wrong is $500-$1,500 per call.

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
_LINE_TYPE_KEY = "phone_line_type_cache"

# Toll-free NPAs. Under §227(b)(1)(A)(iii) the called party is charged for the
# call, so these are treated as consent-required rather than as "obviously a
# business line" — the opposite of the intuitive reading.
_TOLL_FREE_NPAS = frozenset({"800", "888", "877", "866", "855", "844", "833", "822"})

LINE_LANDLINE = "landline"
LINE_MOBILE = "mobile"
LINE_TOLL_FREE = "toll_free"
LINE_UNKNOWN = "unknown"

# Only a landline is callable by an artificial voice without consent.
_CONSENT_EXEMPT_LINE_TYPES = frozenset({LINE_LANDLINE})


async def record_line_type(phone: str, line_type: str, source: str = "") -> bool:
    """Cache a VERIFIED line type for a number.

    `line_type` must be one of landline/mobile/toll_free. This is written by a
    carrier/HLR lookup (a paid API — not enabled by default) or by a human who
    has confirmed it. It is never inferred from the number's prefix, because US
    number portability makes that unreliable.
    """
    norm = _normalize(phone)
    if not norm or line_type not in (LINE_LANDLINE, LINE_MOBILE, LINE_TOLL_FREE):
        logger.error(f"[LINETYPE] Refused to record {line_type!r} for {phone!r}.")
        return False
    try:
        cache = await DatabaseManager.get_state(_LINE_TYPE_KEY, {}) or {}
        cache[norm] = {"line_type": line_type, "source": source or "",
                       "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                   time.gmtime())}
        await DatabaseManager.set_state(_LINE_TYPE_KEY, cache)
        return True
    except Exception as e:
        logger.error(f"[LINETYPE] FAILED to record line type: {e}")
        return False


async def get_line_type(phone: str) -> str:
    """Best known line type, or LINE_UNKNOWN.

    Toll-free is derivable from the NPA and needs no lookup. Everything else
    geographic is UNKNOWN until a real lookup says otherwise — `phonenumbers`
    returns FIXED_OR_MOBILE for every US geographic number, which is not an
    answer.
    """
    norm = _normalize(phone)
    digits = "".join(ch for ch in norm if ch.isdigit())
    if len(digits) >= 10 and digits[-10:-7] in _TOLL_FREE_NPAS:
        return LINE_TOLL_FREE
    try:
        cache = await DatabaseManager.get_state(_LINE_TYPE_KEY, {}) or {}
    except Exception as e:
        logger.error(f"[LINETYPE] Cache read failed for {phone} ({e}).")
        return LINE_UNKNOWN
    entry = cache.get(norm)
    if isinstance(entry, dict) and entry.get("line_type"):
        return entry["line_type"]
    return LINE_UNKNOWN

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

    '+15035550102' and '5035550102' are the same line written two ways, and a
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

    # A VERIFIED business landline is outside both artificial-voice provisions:
    # §227(b)(1)(B) reaches only a "residential telephone line", and
    # §227(b)(1)(A)(iii) reaches cellular / called-party-charged services.
    # No consent is required to place an AI call to one.
    line = await get_line_type(phone)
    if line in _CONSENT_EXEMPT_LINE_TYPES:
        return True, f"verified business {line} — outside §227(b)(1)(B) and (A)(iii)"

    rec = await consent_record(phone)
    if rec is not None:
        return True, (f"consent via {rec.get('source')} on "
                      f"{rec.get('recorded_at')} (line: {line})")

    if line == LINE_TOLL_FREE:
        why = ("toll-free — the called party is charged, so §227(b)(1)(A)(iii) "
               "applies and consent is required")
    elif line == LINE_MOBILE:
        why = ("mobile — §227(b)(1)(A)(iii) covers cellular regardless of "
               "business use, so consent is required")
    else:
        why = ("line type UNKNOWN — cannot show it is a landline, and "
               "§227(b)(1)(A)(iii) makes a cell a $500-$1,500 mistake. Verify "
               "the line type or record consent")
    return False, why
