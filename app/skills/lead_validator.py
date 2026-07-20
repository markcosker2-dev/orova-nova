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
    if owner and _FIXTURE_OWNER_RE.search(owner):
        reasons.append(f"dropped fixture owner name {owner!r}")
        owner = ""
    cleaned["owner"] = owner
    cleaned.pop("owner_name", None)

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
    phone — E.164-normalized & valid 70 (no verification source exists for
      phones; never claim more) · present but unnormalized 30.
    owner — plausible two-word name 60 · +20 when a title corroborates it
      (LinkedIn pass = independent second signal) · +10 for a profile URL.
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
            phone_conf = 70 if phonenumbers.is_valid_number(phonenumbers.parse(phone)) else 30
        except phonenumbers.NumberParseException:
            phone_conf = 30
    else:
        phone_conf = 30

    if not owner or len(owner.split()) < 2:
        owner_conf = 0
    else:
        owner_conf = 60
        if (lead.get("owner_title") or "").strip():
            owner_conf += 20
        if (lead.get("linkedin_url") or "").strip():
            owner_conf += 10

    return {"email": email_conf, "phone": phone_conf, "owner": owner_conf}


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
    "info@", "contact@", "support@", "hello@", "admin@", "office@", "sales@",
    "service@", "team@", "enquiries@", "inquiries@", "help@",
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
    # business's own web presence).
    _url = (lead.get("url") or "").strip()
    website = (lead.get("website") or ("" if "yelp.com" in _url.lower() else _url)).strip()
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


def score_lead(company_name: str, company_size: str = "unknown", industry: str = "unknown", 
               response_signals: dict = None, contact_type: str = "unknown") -> dict:
    """
    Score a lead 0-100 based on engagement likelihood.
    
    Scoring factors:
    - Company size: larger = higher score
    - Industry match: aligned with your services = +points
    - Response history: past engagement = +points
    - Contact type: Decision maker > IC = higher
    
    Args:
        company_name: Business name
        company_size: "1-10", "11-50", "51-250", "250+"
        industry: Business vertical
        response_signals: dict with keys like "email_opens", "clicks", "prev_responses"
        contact_type: "decision_maker", "influencer", "individual_contributor"
    
    Returns:
        dict with score (0-100), breakdown, and recommendation
    """
    score = 50  # Base score
    breakdown = {}
    
    # Company size scoring
    size_scores = {
        "1-10": 30,
        "11-50": 60,
        "51-250": 75,
        "250+": 85,
    }
    size_score = size_scores.get(company_size, 50)
    score += (size_score - 50) * 0.3
    breakdown["company_size"] = size_score
    
    # Industry alignment (premium B2B verticals)
    high_value_industries = [
        "technology", "saas", "fintech", "healthcare", "real_estate", 
        "insurance", "e-commerce", "logistics", "manufacturing", "construction"
    ]
    if industry.lower() in high_value_industries:
        score += 15
        breakdown["industry_alignment"] = 15
    else:
        breakdown["industry_alignment"] = 0
    
    # Response signals (if available)
    if response_signals:
        if response_signals.get("email_opens", 0) > 0:
            score += 10
        if response_signals.get("clicks", 0) > 0:
            score += 15
        if response_signals.get("prev_responses", 0) > 0:
            score += 20
        breakdown["response_signals"] = response_signals.get("email_opens", 0) * 2
    else:
        breakdown["response_signals"] = 0
    
    # Contact type
    contact_scores = {
        "decision_maker": 20,
        "influencer": 10,
        "individual_contributor": 5,
        "unknown": 0,
    }
    contact_score = contact_scores.get(contact_type, 0)
    score += contact_score
    breakdown["contact_type"] = contact_score
    
    # Normalize to 0-100
    score = min(100, max(0, score))
    
    # Recommendation
    if score >= 80:
        recommendation = "🔥 HOT LEAD — Call immediately"
    elif score >= 60:
        recommendation = "⭐ WARM LEAD — Email first, then call"
    elif score >= 40:
        recommendation = "📧 COLD LEAD — Email sequence, monitor response"
    else:
        recommendation = "❓ LOW PRIORITY — Add to nurture list"
    
    return {
        "score": int(score),
        "breakdown": breakdown,
        "recommendation": recommendation,
        "company": company_name
    }


def score_lead_for_orova(lead: dict) -> dict:
    """
    Score a raw lead dict 0-10 for OROVA's luxury/high-ticket targeting.
    Returns the lead dict augmented with orova_score, score_reasons, filter_decision.
    """
    score = 5
    reasons = []

    # Contact quality
    email = (lead.get("email") or "").lower()
    phone = lead.get("phone") or ""
    name = lead.get("owner_name") or lead.get("name") or ""

    has_personal_email = email and not email.startswith(("info@", "contact@", "support@", "hello@", "admin@"))
    has_name = len(name.split()) >= 2
    has_phone = len(phone) >= 10

    if has_personal_email:
        score += 2
        reasons.append("personal email")
    elif email:
        score += 0.5
        reasons.append("generic email")

    if has_name:
        score += 1.5
        reasons.append("owner name found")

    if has_phone:
        score += 1
        reasons.append("phone number")

    # Source quality bonus
    source = lead.get("source", "")
    if source == "apollo_browser":
        score += 1
        reasons.append("apollo verified")

    # Email verification status (set by enrichment waterfall)
    email_status = lead.get("email_status", "")
    if email_status == "verified":
        score += 1
        reasons.append("email verified")
    elif email_status == "guessed":
        score -= 1
        reasons.append("email guessed")

    if lead.get("owner_title"):
        score += 0.5
        reasons.append("title known")

    score = min(10, max(0, score))

    # Filter decision
    if score >= 7 and (has_personal_email or has_name):
        decision = "PASS"
    elif score >= 5 and email:
        decision = "PASS"
    elif score >= 4:
        decision = "BORDERLINE"
    else:
        decision = "REJECT"

    lead["orova_score"] = round(score, 1)
    lead["score_reasons"] = reasons
    lead["filter_decision"] = decision
    return lead
