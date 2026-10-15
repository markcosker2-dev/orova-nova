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
import os
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


# ── Jurisdiction (state ADAD statutes), separate from federal §227(b) ──────
# This started life in scripts/nova.py, which was the wrong place and a repeat
# of the exact hole the consent gate below was written to close: FIVE paths
# reach trigger_retell_call, and a gate that lives in one of them protects one
# of them. planner exposes the dialler to the LLM as a tool, and an
# LLM-invokable path cannot be gated by convention at all.
#
# §227(b) is FEDERAL and consent cures it. RCW 80.36.400 (WA) and CA PUC §2874
# are STATE statutes with their own rules — 80.36.400 appears to have no
# consent cure at all — so a consent record says nothing about them.
#
# The allowlist is EMPTY by default and is configuration, never a list compiled
# from anyone's reading of the statutes. State ADAD laws vary, several are
# stricter than federal, and a wrong entry is $500-$1,500 per call.
#
#     AI_CALL_ALLOWED_STATES=OR        after Oregon is cleared
#     AI_CALL_ALLOWED_STATES=OR,CA     after the lawyer answers
_ALLOWED_STATES_VAR = "AI_CALL_ALLOWED_STATES"

# Enough NPAs to decide the states OROVA actually works. Deliberately partial:
# an unlisted NPA resolves to UNKNOWN and is REFUSED, which is the safe
# direction. Number portability means an NPA is evidence, not proof, so an
# explicit `state` from the lead row always wins over this map.
_NPA_STATE = {
    "206": "WA", "253": "WA", "360": "WA", "425": "WA", "509": "WA", "564": "WA",
    "503": "OR", "541": "OR", "971": "OR", "458": "OR",
    "209": "CA", "213": "CA", "279": "CA", "310": "CA", "323": "CA", "341": "CA",
    "408": "CA", "415": "CA", "424": "CA", "442": "CA", "510": "CA", "530": "CA",
    "559": "CA", "562": "CA", "619": "CA", "626": "CA", "628": "CA", "650": "CA",
    "657": "CA", "661": "CA", "669": "CA", "707": "CA", "714": "CA", "747": "CA",
    "760": "CA", "805": "CA", "818": "CA", "820": "CA", "831": "CA", "858": "CA",
    "909": "CA", "916": "CA", "925": "CA", "949": "CA", "951": "CA",
    "480": "AZ", "520": "AZ", "602": "AZ", "623": "AZ", "928": "AZ",
    "702": "NV", "725": "NV", "775": "NV",
    "208": "ID", "986": "ID",
}


def allowed_states() -> set:
    """States cleared for an AI-placed call. Empty means none."""
    raw = (os.getenv(_ALLOWED_STATES_VAR) or "").strip()
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def state_for(phone: str, state: str = "") -> str:
    """Best available jurisdiction for this call, or '' when undecidable."""
    if state and state.strip():
        return state.strip().upper()
    norm = _normalize(phone)
    digits = "".join(c for c in norm if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return _NPA_STATE.get(digits[:3], "") if len(digits) == 10 else ""


def jurisdiction_allowed(phone: str, state: str = "") -> tuple:
    """(allowed, reason) — is an AI-placed call permitted in this state?"""
    allow = allowed_states()
    if not allow:
        return False, (f"{_ALLOWED_STATES_VAR} is empty — no state has been "
                       f"cleared for an AI-placed call. RCW 80.36.400 and CA "
                       f"PUC §2874 are separate from §227(b) and are not "
                       f"answered by a consent record.")
    # Toll-free has no geography, so a state test cannot say anything useful
    # about it. Defer: §227(b)(1)(A)(iii) refuses it below on the ground that
    # actually applies — the called party is charged — which is a far more
    # useful reason to read in a log than "unlisted area code".
    digits = "".join(c for c in _normalize(phone) if c.isdigit())
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if digits[:3] in _TOLL_FREE_NPAS:
        return True, "toll-free — no jurisdiction test applies; see §227(b)"

    st = state_for(phone, state)
    if not st:
        return False, ("state undetermined (unlisted area code, no state on "
                       "the lead) — cannot show the call is permitted")
    if st not in allow:
        return False, f"{st} is not in {_ALLOWED_STATES_VAR} ({sorted(allow)})"
    return True, f"{st} is cleared"


async def ai_call_allowed(phone: str, state: str = "") -> tuple:
    """(allowed, reason) — the single gate the AI calling lane must consult.

    ALL conditions must hold, and suppression always wins:
      · the STATE permits an AI-placed call at all (jurisdiction_allowed)
      · not on the DNC/opt-out list  (app/core/dnc.py, unmodified)
      · prior express consent on record for an artificial-voice call

    `state` is optional: pass it when the caller has the lead row, otherwise it
    is inferred from the area code and an unlisted NPA REFUSES.

    Returns a reason string on refusal so the lane can log WHY a number was
    skipped, rather than leaving a silent gap the way the email path once did.
    """
    norm = _normalize(phone)
    if not norm:
        return False, "no phone number"

    # Jurisdiction first: if the state does not permit an AI-placed call, no
    # amount of consent makes it lawful, so there is nothing further to check.
    ok_state, why_state = jurisdiction_allowed(phone, state)
    if not ok_state:
        return False, f"jurisdiction: {why_state}"

    # Suppression next — an opt-out overrides any earlier consent.
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
