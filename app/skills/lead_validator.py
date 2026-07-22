"""
Lead Validation & Scoring for Meta Lead Gen Agency
Validates email/phone before cold outreach and scores leads for prioritization.
"""
import re
import logging
from email_validator import validate_email, EmailNotValidError
import phonenumbers

logger = logging.getLogger(__name__)

def validate_email_address(email: str) -> dict:
    """Validate email format and deliverability."""
    try:
        valid = validate_email(email)
        return {"valid": True, "email": valid.email, "normalized": str(valid)}
    except EmailNotValidError as e:
        logger.warning(f"[Validator] Invalid email {email}: {e}")
        return {"valid": False, "email": email, "reason": str(e)}

def validate_phone_number(phone: str, country_code: str = "US") -> dict:
    """Validate and normalize international phone number."""
    try:
        parsed = phonenumbers.parse(phone, country_code)
        if phonenumbers.is_valid_number(parsed):
            formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            return {"valid": True, "phone": formatted, "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)}
        else:
            return {"valid": False, "phone": phone, "reason": "Invalid format for region"}
    except phonenumbers.NumberParseException as e:
        logger.warning(f"[Validator] Invalid phone {phone}: {e}")
        return {"valid": False, "phone": phone, "reason": str(e)}

# ─── STORAGE GATE (Phase 0 data integrity, 2026-07-20) ──────────────────────
# The single set of rules deciding what may enter the leads table. Live prod
# had (a) the repo's own sample_webhook_payload.json fixture stored as a lead
# ("Acme Remodeling Co" / jane.doe@acme.com / +1-555-123-4567 / score 85 taken
# verbatim from the payload) via the ungated Sheets restore, and (b) a row
# with no business name whose phone rendered in Mission Control's Business
# column. Rule: if a field can't be verified it is stored EMPTY — never a
# placeholder, never fabricated.

_PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net", "test.com", "acme.com",
    "email.com", "domain.com", "yourcompany.com", "yourdomain.com",
    "company.com", "sample.com", "mailinator.com", "acme.example.com",
}
_PLACEHOLDER_EMAIL_LOCALS = {"test", "example", "sample", "demo", "placeholder", "noreply", "no-reply", "donotreply"}
# Fixture/sample markers that mean the whole row is fake, not a real prospect.
_FIXTURE_BUSINESS_RE = re.compile(r"\b(acme|example|lorem|ipsum|fake|placeholder)\b", re.IGNORECASE)
_FIXTURE_OWNER_RE = re.compile(r"\b(jane|john)\s+doe\b|\btest\s+user\b", re.IGNORECASE)
_EMAIL_LIKE_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}")

# ─── Person-name plausibility (single source of truth) ──────────────────────
# Three divergent copies of this check lived in lead_gen_v3, light_enrich and
# owner_finder; the weakest one let scraped sentence fragments through as
# owner names — live 2026-07-20: "THANKS TO", "We Proudly", "Good People"
# stored as owners, and the email guesser then fabricated
# thanks@calabasasluxurymotorcars.com FROM the fake name. This is the
# canonical check; the skill modules delegate here and may add their own
# extra denylists on top.

_NAME_PARTICLES = frozenset({
    "van", "von", "de", "del", "della", "der", "den", "la", "le", "du", "da",
    "di", "dos", "das", "bin", "al", "ter", "ten", "st",
})

_NON_NAME_TOKENS = frozenset({
    # business/entity/page words (from lead_gen_v3, the strongest copy)
    "auto", "automotive", "repair", "repairs", "maintenance", "manual", "manuals",
    "service", "services", "servicing", "dealer", "dealers", "dealership",
    "detailing", "collision", "bodyshop", "towing", "roadside", "transmission",
    "brakes", "tire", "tires", "wheel", "wheels", "engine", "upholstery",
    "ceramic", "coating", "coatings", "tint", "tinting", "wrap", "wraps",
    "remodel", "remodeling", "renovation", "construction", "builders", "roofing",
    "plumbing", "hvac", "landscaping", "realty", "realtors", "brokerage",
    "llc", "inc", "ltd", "corp", "corporation", "incorporated", "company",
    "motors", "motor", "enterprises", "holdings", "group", "industries",
    "solutions", "systems", "technologies", "associates", "management",
    "member", "members", "circles", "center", "centre", "store", "shop",
    "mobile", "express", "premium", "luxury", "exotic", "rental", "rentals",
    "leasing", "financing", "warranty", "insurance", "appointment", "quote",
    "welcome", "about", "contact", "team", "staff", "login", "search",
    "results", "privacy", "policy", "terms", "menu", "gallery",
    # sentence-fragment function words (live fakes 2026-07-20)
    "thanks", "thank", "to", "we", "our", "you", "your", "their", "they",
    "us", "and", "the", "for", "with", "from", "proudly", "proud", "good",
    "people", "all", "best", "since", "family", "owned", "operated", "here",
    "why", "choose", "buy", "sell", "browse", "view", "call", "today", "now",
    "more", "learn", "inventory", "sales", "customer", "customers",
})
# NOTE: deliberately omits words that are also common surnames (Baker, Page,
# Mason, Taylor, Wood, Berry, Marsh, Home) to avoid rejecting real people.
# "good" IS a rare surname — accepted trade-off after the live "Good People"
# fake: never-fabricate outranks rare-name completeness, and registry-sourced
# names (owner_finder) bypass this check entirely.


def is_plausible_person_name(text: str) -> bool:
    """True when `text` is shaped like a real person's name — Title Case
    2-4 alpha tokens, lowercase only for known name particles (van/de/…),
    and no token from the business/sentence-fragment denylist."""
    if not text or len(text) < 4 or len(text) > 50:
        return False
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Za-z'\-]+$", p) for p in parts):
        return False
    if not parts[0][0].isupper():
        return False
    for p in parts:
        core = p.lstrip("'-")
        if not core:
            return False
        if not core[0].isupper() and p.lower() not in _NAME_PARTICLES:
            return False
    if any(p.lower().strip("'-") in _NON_NAME_TOKENS for p in parts):
        return False
    return True


def _looks_like_phone(text: str) -> bool:
    """True when a string is a phone number wearing a name tag (e.g. the
    live 'Business: 14047334400' row)."""
    if not text:
        return False
    digits = re.sub(r"\D", "", text)
    compact = re.sub(r"\s", "", text)
    return len(digits) >= 7 and compact and (len(digits) / len(compact)) > 0.6


def is_placeholder_email(email: str) -> bool:
    email = (email or "").strip().lower()
    if "@" not in email:
        return False
    local, _, domain = email.rpartition("@")
    return (domain in _PLACEHOLDER_EMAIL_DOMAINS
            or domain.endswith((".example.com", ".test"))
            or local in _PLACEHOLDER_EMAIL_LOCALS)


def clean_email_for_storage(email: str) -> str:
    """Normalized email, or '' when invalid/placeholder. Never store junk.

    Format + placeholder check ONLY — no DNS deliverability lookup here.
    Storage runs inside DB transactions and the boot sweep; a network hiccup
    must not silently drop a real address. Deliverability stays an
    outreach-time concern (validate_email_address)."""
    email = (email or "").strip()
    if not email:
        return ""
    if is_placeholder_email(email):
        logger.info(f"[LEAD-GATE] dropped placeholder email: {email}")
        return ""
    try:
        valid = validate_email(email, check_deliverability=False)
        return valid.normalized.lower()
    except EmailNotValidError:
        logger.info(f"[LEAD-GATE] dropped malformed email: {email}")
        return ""


def is_placeholder_phone(phone: str) -> bool:
    """Fictional/dummy numbers: NANP 555 exchange, repeated or sequential digits."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return False
    national = digits[1:] if len(digits) == 11 and digits[0] == "1" else digits
    if len(national) == 10 and (national[3:6] == "555" or national[:3] == "555"):
        return True  # 555 exchange (fictional range) or 555 area code (sample data)
    if len(set(digits)) == 1:
        return True  # 0000000000, 1111111111, …
    if digits in ("1234567890", "0123456789", "12345678901"):
        return True
    return False


def clean_phone_for_storage(phone: str, country: str = "US") -> str:
    """E.164 phone, or '' when invalid/placeholder. Never store fake numbers."""
    phone = (phone or "").strip()
    if not phone:
        return ""
    if is_placeholder_phone(phone):
        logger.info(f"[LEAD-GATE] dropped placeholder phone: {phone}")
        return ""
    result = validate_phone_number(phone, country)
    return result["e164"] if result["valid"] else ""


def clean_url_for_storage(url: str) -> str:
    """URL, or '' when it points at a documentation/placeholder host."""
    url = (url or "").strip()
    if not url:
        return ""
    host = re.sub(r"^https?://", "", url.lower()).split("/")[0].split(":")[0]
    bare = host[4:] if host.startswith("www.") else host
    if bare in ("example.com", "example.org", "example.net", "test.com") or \
            bare.endswith((".example.com", ".example.org", ".example.net", ".test")):
        logger.info(f"[LEAD-GATE] dropped placeholder URL: {url}")
        return ""
    return url


def validate_lead_for_storage(lead: dict) -> dict:
    """The storage gate. Returns {ok, lead (cleaned copy), reasons (list)}.

    ok=False → the row must not be stored/displayed at all (no business name,
    phone-number-as-name, or recognizable fixture data). ok=True → store the
    cleaned copy: unverifiable email/phone/url are EMPTIED, with the drop
    recorded in reasons. Callers must persist the cleaned copy, not the input.
    """
    cleaned = dict(lead)
    reasons = []

    # Gate inputs are NOT guaranteed to be strings: gspread's
    # get_all_records() returns ints for numeric-looking Sheet cells
    # (Google Sheets coerces "+14047334400" to the number 14047334400),
    # and that int crashed .strip() in the boot restore loop — killing
    # every fresh deploy with uvicorn exit 3 (live 2026-07-21, three
    # consecutive update_failed deploys). Coerce every consumed field.
    for _f in ("business", "owner", "owner_name", "email", "phone", "url", "website"):
        _v = cleaned.get(_f)
        if _v is not None and not isinstance(_v, str):
            cleaned[_f] = str(_v)

    business = (cleaned.get("business") or "").strip()
    if not business:
        return {"ok": False, "lead": cleaned, "reasons": ["no business name"]}
    if _looks_like_phone(business):
        return {"ok": False, "lead": cleaned, "reasons": [f"business name is a phone number: {business!r}"]}
    if "@" in business and _EMAIL_LIKE_RE.search(business):
        return {"ok": False, "lead": cleaned, "reasons": [f"business name is an email address: {business!r}"]}
    if _FIXTURE_BUSINESS_RE.search(business):
        return {"ok": False, "lead": cleaned, "reasons": [f"fixture/sample business name: {business!r}"]}
    cleaned["business"] = business

    owner = (cleaned.get("owner") or cleaned.get("owner_name") or "").strip()
    dropped_owner_first = ""
    # A positive owner_confidence means the decision-maker waterfall already
    # cross-referenced and vetted this name (incl. recognized single first
    # names like "Blake"); trust it over the shape heuristic. The heuristic
    # still guards ungated ingest (CSV/Sheets) where confidence is 0.
    owner_vetted = int(cleaned.get("owner_confidence") or 0) > 0
    if owner and _FIXTURE_OWNER_RE.search(owner):
        reasons.append(f"dropped fixture owner name {owner!r}")
        owner = ""
    elif owner and not owner_vetted and not is_plausible_person_name(owner):
        # live 2026-07-20: "THANKS TO", "We Proudly", "Good People" stored as
        # owners — scraped sentence fragments, not people.
        reasons.append(f"dropped implausible owner name {owner!r}")
        dropped_owner_first = owner.split()[0].lower().strip("'-")
        owner = ""
    cleaned["owner"] = owner
    cleaned.pop("owner_name", None)

    # An email GUESSED from a name we just rejected is fabrication squared
    # (live: thanks@calabasasluxurymotorcars.com from "THANKS TO") — drop it.
    email_now = (cleaned.get("email") or "").strip().lower()
    if dropped_owner_first and email_now:
        local = email_now.split("@")[0]
        if local == dropped_owner_first or local.startswith(dropped_owner_first + "."):
            reasons.append(f"dropped email {email_now!r} derived from rejected owner name")
            cleaned["email"] = ""
            cleaned["email_status"] = ""

    for field, cleaner in (("email", clean_email_for_storage),
                           ("phone", clean_phone_for_storage),
                           ("url", clean_url_for_storage),
                           ("website", clean_url_for_storage)):
        raw = (cleaned.get(field) or "").strip()
        if raw:
            kept = cleaner(raw)
            if not kept:
                reasons.append(f"dropped unverifiable {field} {raw!r}")
            cleaned[field] = kept

    # The stored score is always server-computed — never trusted from a
    # payload (the Sheets fixture arrived pre-scored at 85).
    cleaned["score"] = score_lead_icp(cleaned)["score"]
    return {"ok": True, "lead": cleaned, "reasons": reasons}


def contact_confidence(lead: dict) -> dict:
    """Deterministic 0-100 confidence per contact field, from signals the
    pipeline already records. Computed (not stored) so it can never go stale.

    email — anchored on email_status set by enrichment:
      'verified' (Verifalia deliverable) 90 · 'found' (scraped from the
      business's own site/API source) 65 · 'guessed' (pattern guess, MX ok) 35
      · present with unknown provenance 50; generic inboxes (info@…) −15.
    phone — corroborated by 2+ independent sources (phone_verified) 90 ·
      E.164-normalized & valid 70 · present but unnormalized 30.
    owner — base by provenance: state-registry/legal-filing source 85 ·
      other/unknown source 60; +10 when a title corroborates it, +5 for a
      LinkedIn profile URL (cap 95 — nothing is 100 without a human check).
    """
    email = (lead.get("email") or "").strip().lower()
    phone = (lead.get("phone") or "").strip()
    owner = (lead.get("owner") or lead.get("owner_name") or "").strip()

    if not email:
        email_conf = 0
    else:
        status = (lead.get("email_status") or "").strip().lower()
        email_conf = {"verified": 90, "found": 65, "guessed": 35}.get(status, 50)
        if email.startswith(_GENERIC_EMAIL_PREFIXES):
            email_conf = max(email_conf - 15, 10)

    if not phone:
        phone_conf = 0
    elif phone.startswith("+") and not is_placeholder_phone(phone):
        try:
            valid = phonenumbers.is_valid_number(phonenumbers.parse(phone))
        except phonenumbers.NumberParseException:
            valid = False
        phone_conf = (90 if lead.get("phone_verified") else 70) if valid else 30
    else:
        phone_conf = 30

    _REGISTRY_SOURCES = ("ca_sos", "wa_sos", "or_sos", "opencorporates")
    if not owner:
        owner_conf = 0
    elif int(lead.get("owner_confidence") or 0) > 0:
        # The waterfall already cross-referenced sources into a real
        # confidence — that ledger-derived number is authoritative.
        owner_conf = int(lead["owner_confidence"])
    elif len(owner.split()) < 2:
        owner_conf = 0
    else:
        owner_conf = 85 if (lead.get("owner_source") or "") in _REGISTRY_SOURCES else 60
        if (lead.get("owner_title") or "").strip():
            owner_conf += 10
        if (lead.get("linkedin_url") or "").strip():
            owner_conf += 5
        owner_conf = min(owner_conf, 95)

    return {"email": email_conf, "phone": phone_conf, "owner": owner_conf}


# Outreach-ready bar (owner requirement 2026-07-22): every lead we contact needs
# the DECISION-MAKER'S NAME (to bypass the gatekeeper and personalize), a DIRECT
# email (never a generic info@/sales@ mailbox), and a phone — a business line is
# fine for calling as long as the name is present (TCPA: business line + name is
# the compliant cold-call combo; never a personal cell). Computed at read time
# over the same signals as contact_confidence — never stored.
_OUTREACH_MIN_NAME_CONF = 60   # below this, the "name" is an unvetted guess
_OUTREACH_MIN_EMAIL_CONF = 35  # guessed-but-MX-ok or better (generic is penalised in contact_confidence)


def outreach_ready(lead: dict) -> dict:
    """Does this lead clear the outreach bar? Computed, never stored.

    Returns {ready, emailable, callable, has_name, has_direct_email, has_phone,
    blockers}. The decision-maker NAME is mandatory for every channel. Email must
    be a DIRECT mailbox — a generic info@/sales@ does not count. Phone may be a
    business line as long as the name is present (so we can ask for the person).
    """
    conf = contact_confidence(lead)
    email = (lead.get("email") or "").strip().lower()

    has_name = conf["owner"] >= _OUTREACH_MIN_NAME_CONF
    is_generic = bool(email) and email.startswith(_GENERIC_EMAIL_PREFIXES)
    has_direct_email = bool(email) and not is_generic and conf["email"] >= _OUTREACH_MIN_EMAIL_CONF
    has_phone = conf["phone"] > 0

    emailable = has_name and has_direct_email
    callable_via_gatekeeper = has_name and has_phone
    ready = emailable or callable_via_gatekeeper

    blockers = []
    if not has_name:
        blockers.append("no verified decision-maker name")
    if not has_direct_email:
        if is_generic:
            blockers.append("email is generic (info@/sales@) — needs a direct mailbox")
        elif not email:
            blockers.append("no email")
        else:
            blockers.append("email unverified / low confidence")
    if not has_phone:
        blockers.append("no phone")

    return {
        "ready": ready,
        "emailable": emailable,
        "callable": callable_via_gatekeeper,
        "has_name": has_name,
        "has_direct_email": has_direct_email,
        "has_phone": has_phone,
        "blockers": blockers,
    }


def validate_contact(email: str = None, phone: str = None, country: str = "US") -> dict:
    """
    Validate both email and phone. Returns combined result.
    Use before sending cold outreach to ensure contact validity.
    """
    result = {"email_valid": False, "phone_valid": False, "contact_valid": False}
    
    if email:
        email_result = validate_email_address(email)
        result["email_valid"] = email_result["valid"]
        result["email_normalized"] = email_result.get("email")
    
    if phone:
        phone_result = validate_phone_number(phone, country)
        result["phone_valid"] = phone_result["valid"]
        result["phone_formatted"] = phone_result.get("phone")
    
    # Lead is "valid to contact" if at least one channel is valid
    result["contact_valid"] = result["email_valid"] or result["phone_valid"]
    return result


# ─── LEAD SCORING ───────────────────────────────────────────────────────
# Simple rule-based + ML-ready scoring for lead prioritization

# ── Deterministic ICP scoring (SDR refocus, 2026-07-14) ────────────────────
# The old score_lead() weighed company_size / B2B-industry / email-opens —
# data the hunt pipeline NEVER has (worker.py passes "unknown" for all of
# them), so every live lead scored exactly 50 and the score was decorative.
# score_lead_icp() scores only on fields enrichment actually collects, so the
# score discriminates and Mark's "email the best 10" is a real ranking.

# Luxury/premium signals in the business name or vertical (OROVA's lead
# vertical is luxury automotive; the ICP stays mixed per owner 2026-07-13).
_ICP_LUXURY_KEYWORDS = (
    "exotic", "luxury", "supercar", "ferrari", "lamborghini", "porsche",
    "bentley", "rolls", "mclaren", "aston", "maserati", "high end", "high-end",
    "premium", "prestige", "elite", "custom home", "estate",
)
_ICP_VERTICAL_KEYWORDS = (
    # automotive services (the lead vertical)
    "dealer", "dealership", "rental", "detail", "ceramic", "ppf",
    "paint protection", "wrap", "tint", "performance", "tuning", "restoration",
    "motorsport", "collision",
    # rest of the mixed ICP
    "builder", "remodel", "renovation", "real estate", "realty", "interior design",
    "landscape", "med spa", "medspa",
)
_GENERIC_EMAIL_PREFIXES = (
    "info@", "contact@", "support@", "hello@", "hi@", "admin@", "office@", "sales@",
    "leads@", "service@", "services@", "team@", "enquiries@", "inquiries@", "help@",
    "marketing@", "careers@", "jobs@", "hr@", "billing@", "accounts@", "accounting@",
    "reception@", "frontdesk@", "shop@", "store@", "orders@", "parts@", "finance@",
    "leasing@", "web@", "webmaster@", "postmaster@", "noreply@", "no-reply@",
    "general@", "main@", "mail@", "email@",
)


def score_lead_icp(lead: dict) -> dict:
    """Deterministic 0-100 ICP-fit score from fields the pipeline collects.

    Weights (documented so the score is debuggable, not vibes):
      +25 owner name found (a real person to write to — the #1 reply factor)
      +25 direct/personal email  (+10 if only a generic inbox)
      +10 phone (E.164)
      +10 website
      +20 luxury/premium keyword in name or vertical (can-afford-$4k signal)
      +10 ICP vertical keyword match
    Thresholds: >=70 HOT (email first, everything verified), 45-69 WARM,
    25-44 COLD, <25 SKIP (not worth Mark's time).
    """
    name = (lead.get("owner") or lead.get("owner_name") or "").strip()
    email = (lead.get("email") or "").strip().lower()
    phone = (lead.get("phone") or "").strip()
    # Hunted leads often carry the site in `url` with `website` unset —
    # credit either, but never a directory link (a Yelp page isn't the
    # business's own web presence). Host check is dot-anchored on the parsed
    # netloc — 'notyelp.com' and 'site.com/yelp.com' must not match (CodeQL).
    from urllib.parse import urlparse
    _url = (lead.get("url") or "").strip()
    _host = urlparse(_url).netloc.lower().split(":")[0]
    _is_yelp = _host == "yelp.com" or _host.endswith(".yelp.com")
    website = (lead.get("website") or ("" if _is_yelp else _url)).strip()
    haystack = f"{lead.get('business') or ''} {lead.get('vertical') or ''} {lead.get('niche') or ''}".lower()

    score = 0
    breakdown = {}

    has_owner = len(name.split()) >= 2
    breakdown["owner_name"] = 25 if has_owner else 0

    if email:
        if email.startswith(_GENERIC_EMAIL_PREFIXES):
            breakdown["email"] = 10
        else:
            breakdown["email"] = 25
    else:
        breakdown["email"] = 0

    breakdown["phone"] = 10 if phone.startswith("+") and len(phone) >= 11 else 0
    breakdown["website"] = 10 if website.startswith("http") else 0
    breakdown["luxury_signal"] = 20 if any(k in haystack for k in _ICP_LUXURY_KEYWORDS) else 0
    breakdown["vertical_match"] = 10 if any(k in haystack for k in _ICP_VERTICAL_KEYWORDS) else 0

    score = sum(breakdown.values())

    if score >= 70:
        recommendation = "🔥 HOT — direct owner contact, on-ICP: email today"
    elif score >= 45:
        recommendation = "⭐ WARM — contactable, partial fit: email this week"
    elif score >= 25:
        recommendation = "📧 COLD — thin contact data: enrich further before outreach"
    else:
        recommendation = "⏭️ SKIP — not worth outreach time"

    return {
        "score": int(score),
        "breakdown": breakdown,
        "recommendation": recommendation,
        "company": lead.get("business", ""),
    }
