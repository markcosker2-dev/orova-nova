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

# ── Off-ICP domain classes (live 2026-07-26) ────────────────────────────────
# Production held 47 rows that passed every existing check: an Argentine
# GOVERNMENT MUSEUM (museo@adolfoalsina.gov.ar), an Argentine news site, and a
# named automotive journalist at a trade publisher (lvellequette@crain.com).
# The outreach gate stopped them being contacted, but they still occupied the
# pipeline — and a journalist receiving OROVA cold outreach is a reputational
# risk, not a data-quality nit.
#
# Deliberately narrow: only classes that can NEVER be a home-remodeling
# prospect. Anything merely *unlikely* is left alone — a false quarantine of a
# real contractor costs more than a junk row.

# Institutions. A government agency, school or military site is not a
# remodeler. Matched as a TLD or as a second-level segment so ".gov.ar" and
# ".edu.au" are caught alongside ".gov".
_INSTITUTIONAL_DOMAIN_RE = re.compile(r"\.(gov|edu|mil|int)(\.[a-z]{2})?$", re.IGNORECASE)

# Country-code TLDs plainly outside the US West Coast ICP. Conservative on
# purpose — ambiguous ones US businesses genuinely use (.co, .io, .ai, .me,
# .tv, .cc) are NOT listed.
_FOREIGN_CCTLD_RE = re.compile(
    r"\.(ar|br|mx|cl|pe|co\.uk|uk|ie|fr|de|es|it|nl|pl|ru|ua|cn|jp|kr|in|pk|"
    r"ph|id|vn|th|my|sg|au|nz|za|ng|ke|il|tr|gr|pt|se|no|fi|dk|cz|ro|hu)$",
    re.IGNORECASE)

# Publishers and trade press observed in production. A named journalist is a
# real person who must never receive cold outreach. Empirical rather than
# principled, so it is a short explicit list — extend it as junk appears, and
# never widen it to guesswork.
_PUBLISHER_DOMAINS = frozenset({
    "crain.com", "crainsdetroit.com", "automotiveworld.com", "infobae.com",
    "autonews.com", "wardsauto.com", "just-auto.com", "motortrend.com",
})


# ── Off-ICP verticals (ADR-0012, enforced 2026-07-26) ───────────────────────
# ADR-0012 re-ranked the ICP to custom home builders / high-end remodelers and
# says to "disqualify on sight: general auto repair (~$400/job -> ~16 jobs/mo to
# break even) - franchised new-car dealers (OEM co-op mandates)".
#
# That decision was never enforced in code, and the cost was real: on 2026-07-25
# the outreach lane worked through 51 legacy rows all tagged vertical
# "Automotive" and sent 48 cold emails — to google.com, an Argentine government
# museum, autotrader.com, two trade publications, and placeholder addresses like
# name@hotmail.com. Zero replies, 550 rejections from Microsoft, and sender
# reputation spent on a segment the ICP had already ruled out.
#
# The lesson generalises: a strategy decision that lives only in an ADR is not a
# control. Encoded here so the SAME rule quarantines stored rows at the boot
# hygiene sweep and blocks a send.
#
# NOT disqualified: exotic/luxury auto, which ADR-0012 keeps as "opportunistic
# only" rather than excluded.
_OFF_ICP_VERTICALS = {
    "automotive",           # the generic bucket that produced repair shops + trade press
    "auto repair",
    "auto service",
    "car repair",
    "mechanic",
    "car dealer",
    "auto dealer",
    "dealership",
}
_OPPORTUNISTIC_VERTICAL_MARKERS = ("exotic", "luxury", "classic", "supercar")

# Cosmetic/appearance auto services — added 2026-08-02 after the owner asked
# why Telegram kept surfacing automotive leads. These fail the ADR-0012
# qualifying test harder than the repair shops already listed above: a ceramic
# coating or a tint job grosses a few hundred dollars, so covering a
# ~$6.5-7.5K/mo retainer needs dozens of extra jobs a month, not one.
#
# They reached Mark because they appear in NO off-ICP list while
# `ceramic coating auto detailing california` sat in the hunt rotation — and
# because `_ICP_VERTICAL_KEYWORDS` in the scorer actively REWARDS "detail",
# "ceramic", "ppf" and "tint" with +10, a leftover from OROVA's original
# luxury-automotive vertical. That scorer inversion is NOT fixed here (the
# owner's standing rule is not to rush the scorer); it is recorded in the PR.
_OFF_ICP_VERTICAL_SUBSTRINGS = (
    "auto repair", "auto service", "car repair",
    "auto detailing", "car detailing", "ceramic coating",
    "paint protection", "window tint", "vinyl wrap",
    # The dealer terms live in _OFF_ICP_VERTICALS too, but that set is matched
    # EXACTLY — and a hunt row's vertical is the whole query string
    # ('exotic car dealer california'), which never equals a bare label. Without
    # a substring leg, "Sunset Motors" off that query walked the gate. Genuine
    # exotic/luxury businesses are still exempt: the business-name carve-out
    # above returns before this runs.
    "car dealer", "auto dealer", "dealership",
)


def off_icp_vertical_reason(lead: dict) -> str:
    """Why this lead's vertical is outside the ADR-0012 ICP, or '' if it is fine.

    Empty verticals are NOT disqualified — absence of a label is not evidence of
    being off-ICP, and other gate rules judge such rows.
    """
    vertical = (lead.get("vertical") or "").strip().lower()
    if not vertical:
        return ""
    # NOTE (2026-08-02): this leg was briefly changed to read the marker from
    # the BUSINESS NAME instead, on the reasoning that worker.py sets
    # `vertical = niche` (the raw query string), so an 'exotic car dealer
    # california' search exempted everything it returned. That was over-reach
    # and is deliberately NOT done: tests/test_outreach_icp_and_canspam_gates
    # asserts these verticals survive, and it is right to — a CSV import or a
    # human labelling `vertical="exotic car dealer"` is real evidence, and
    # over-blocking silently deletes a segment ADR-0012 chose to keep.
    #
    # The residual leak is narrow: a generically-named business (e.g. "Sunset
    # Motors") found BY an exotic-dealer query stays exempt. That is acceptable,
    # because a lead found by that query probably IS an exotic dealer — and the
    # real control is upstream, where automotive was removed from the hunt
    # rotation entirely. Anything with an off-ICP NAME is still caught by
    # off_icp_business_name_reason, which runs alongside this leg.
    if any(m in vertical for m in _OPPORTUNISTIC_VERTICAL_MARKERS):
        return ""   # exotic/luxury auto stays opportunistic, per ADR-0012
    if vertical in _OFF_ICP_VERTICALS or any(
            v in vertical for v in _OFF_ICP_VERTICAL_SUBSTRINGS):
        return (f"off-ICP vertical {vertical!r} — ADR-0012 disqualifies general "
                f"auto repair, franchised dealers and cosmetic auto services "
                f"on sight")
    return ""


# ── Off-ICP by BUSINESS NAME (2026-07-29) ───────────────────────────────────
# The vertical gate above only fires on a POPULATED `vertical`. On 2026-07-29,
# production held exactly one lead: "Keith's Auto Repair" — vertical EMPTY,
# status 'Contacted'. The boot sweep ran the (then new) gate over it and logged
# "[HYGIENE] sweep clean: 1 leads OK". A general auto repair shop, the segment
# ADR-0012 disqualifies on sight, passed the ICP gate because nothing read the
# business name.
#
# This is not an edge case, it is the common case going forward: the licence
# registries adopted in ADR-0014 carry NO vertical field at all, so a gate keyed
# solely on `vertical` is blind on precisely the rows discovery is about to
# start ingesting in volume.
#
# Word boundaries are mandatory here, not stylistic. Naive substring matching
# produces false positives on real in-ICP names:
#   "mechanic"  matches "Mechanical Contractors"  (a real construction trade)
#   "tire"      matches "Retirement Living Builders"
#   "auto"      matches "Autumn Ridge Custom Homes"
# A wrongly-blocked remodeler is a lost prospect, so every pattern below is
# anchored and was checked against real in-ICP naming (see
# tests/test_icp_name_gate.py, which asserts a 0% false-positive rate).
_OFF_ICP_NAME_RE = re.compile(
    r"""(?xi)
    \b auto (?:motive)? \s+ (?: repair | body | service s? | glass | parts |
                                sales | care | center | centre | shop ) \b
  | \b car \s+ (?: repair | wash | care | service s? ) \b
  | \b (?: muffler s? | radiator s? | transmission s? ) \b
  | \b tire s? \b
  | \b brake s? \b
  | \b collision \b
  | \b mechanic s? \b
  | \b dealership s? \b
  | \b towing \b
  | \b tow \s+ truck s? \b
  | \b smog \b
  | \b oil \s+ change \b
  | \b (?: quick \s+ )? lube \b
  | \b auto \s* (?: nation | zone | parts ) \b
  # Cosmetic auto services (2026-08-02). Same 0%-false-positive discipline as
  # above — each of these was checked against the in-ICP control list before
  # being added, which is why "wrap" is anchored to "vinyl wrap" (bare \bwraps?\b
  # is one porch away from blocking a real builder) and "detailing" is used
  # rather than "detail" (a name may legitimately read "Detail Oriented Homes").
  | \b detailing \b
  | \b ceramic \s+ coating \b
  | \b paint \s+ protection (?: \s+ film )? \b
  | \b ppf \b
  | \b window \s+ tint (?: ing )? \b
  | \b vinyl \s+ wrap s? \b
    """
)


def off_icp_business_name_reason(lead: dict) -> str:
    """Why this lead's BUSINESS NAME puts it outside the ADR-0012 ICP, or ''.

    Companion to off_icp_vertical_reason for the (now dominant) case of a lead
    that carries no vertical label. Same ADR-0012 rule, different evidence.

    Exotic/luxury/classic auto is exempt for the same reason it is exempt from
    the vertical gate — ADR-0012 keeps it "opportunistic", not excluded. That
    exemption is what keeps "West Coast Exotic Cars" (a real, deliberately-kept
    lead) out of the quarantine.
    """
    name = (lead.get("business") or "").strip().lower()
    if not name:
        return ""
    if any(m in name for m in _OPPORTUNISTIC_VERTICAL_MARKERS):
        return ""   # exotic/luxury/classic auto stays opportunistic, per ADR-0012
    hit = _OFF_ICP_NAME_RE.search(name)
    if hit:
        return (f"off-ICP business name {lead.get('business')!r} (matched "
                f"{hit.group(0).strip()!r}) — ADR-0012 disqualifies general auto "
                f"repair and franchised dealers on sight")
    return ""


def off_icp_trade_reason(lead: dict) -> str:
    """The single ADR-0012 trade check: vertical first, then business name.

    One entry point so the storage gate, the boot hygiene sweep and the
    pre-send gate cannot drift apart — the divergence that let 48 emails ship.
    """
    return off_icp_vertical_reason(lead) or off_icp_business_name_reason(lead)


def _lead_domains(lead: dict) -> set:
    """Every domain this lead points at — email host plus website/url host."""
    out = set()
    email = (lead.get("email") or "").strip().lower()
    if "@" in email:
        out.add(email.rsplit("@", 1)[-1].strip().strip("."))
    for field in ("website", "url"):
        raw = (lead.get(field) or "").strip().lower()
        if not raw:
            continue
        host = raw.split("//")[-1].split("/")[0].split("?")[0]
        host = host.split(":")[0].removeprefix("www.").strip().strip(".")
        if host:
            out.add(host)
    return {d for d in out if "." in d}


def off_icp_domain_reason(lead: dict) -> str:
    """Why this lead can never be a prospect, or '' if nothing disqualifies it.

    Checked against the email host AND the website host, because the observed
    junk carried the giveaway in either position.
    """
    for domain in sorted(_lead_domains(lead)):
        if domain in _PUBLISHER_DOMAINS:
            return f"publisher/trade-press domain: {domain!r}"
        if _INSTITUTIONAL_DOMAIN_RE.search(domain):
            return f"government/education domain: {domain!r}"
        if _FOREIGN_CCTLD_RE.search(domain):
            return f"non-US domain, outside the West Coast ICP: {domain!r}"
    return ""
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
    # Off-ICP by domain class — a government museum, a foreign site or a trade
    # publisher can never be a remodeling prospect. Rejected here so the same
    # rule covers BOTH new ingest and the boot hygiene sweep, which re-runs
    # this gate over restored rows (app/core/lead_hygiene.py).
    off_icp = off_icp_domain_reason(cleaned)
    if off_icp:
        return {"ok": False, "lead": cleaned, "reasons": [off_icp]}
    # Off-ICP by TRADE (ADR-0012) — vertical label first, then business name.
    # Same placement and same reasoning as the domain rule above: one
    # implementation covers new ingest and the boot hygiene sweep over restored
    # rows. The name leg exists because `vertical` is empty on most real rows
    # (all of the ADR-0014 licence-registry data), which is how "Keith's Auto
    # Repair" survived the sweep on 2026-07-29.
    off_trade = off_icp_trade_reason(cleaned)
    if off_trade:
        return {"ok": False, "lead": cleaned, "reasons": [off_trade]}
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

    # Sources where a real person is named in a legal filing or licence record,
    # so the name is authoritative rather than text-mined. wa_lni is WA L&I's
    # contractor licence principal; wa_sos is kept because rows stored before
    # that swap still carry it.
    _REGISTRY_SOURCES = ("ca_sos", "wa_sos", "wa_lni", "or_sos", "opencorporates")
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

# 65 = 'found' (scraped from the business's own site) or 'verified'. A pure
# pattern GUESS scores 35 and must never clear this bar.
#
# This was 35, and that is exactly how the 2026-07-25 incident happened: a
# guessed address scored 35, the threshold was `>= 35`, so 48 invented strings
# came back emailable with an EMPTY blocker list and were mailed. Microsoft
# answered `550 5.4.1` — Directory-Based Edge Blocking, i.e. "no such mailbox"
# — for the ones that were pure fabrication.
#
# The old comment read "guessed-but-MX-ok". That reasoning is the trap: the MX
# check proves the DOMAIN accepts mail, and says nothing about whether the
# MAILBOX exists. `marc@realcompany.com` passes MX and still bounces when there
# is no Marc. Provenance was already recorded correctly (email_status
# 'guessed'); nothing acted on it. A label that no gate reads is not a control.
#
# Consequence, accepted deliberately: a lead whose email could only be guessed
# is no longer `emailable`. It stays `callable` when a phone and name exist, so
# nothing is lost from the phone lane — and per ADR-0008 a miss always beats a
# fabricated contact.
_OUTREACH_MIN_EMAIL_CONF = 65


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

# Luxury/premium signals in the BUSINESS NAME (see the haystack note in
# score_lead_icp). The lead vertical is custom home builders / high-end
# remodelers — ADR-0012, narrowed by ADR-0015. Rewritten 2026-08-09; the old
# list was the original luxury-automotive vocabulary plus accretions.
_ICP_LUXURY_KEYWORDS = (
    "luxury", "high end", "high-end", "premium", "prestige", "elite",
    "custom home", "estate", "bespoke", "architectural",
)
_ICP_VERTICAL_KEYWORDS = (
    # Custom home building / high-end remodeling — THE lead vertical.
    # "construction" and "contractor" were MISSING entirely until 2026-08-09,
    # even though licence registries (WA L&I / OR CCB / CSLB) have been the
    # primary source since ADR-0014 and name their rows exactly that way:
    # HAWK CONSTRUCTION, GOLAN CONSTRUCTION LLC, FOREVER QUALITY CONSTRUCT LLC.
    "builder", "build", "construction", "construct", "contractor", "contracting",
    "remodel", "renovation", "renovate", "restoration",
    "kitchen", "bath", "cabinet", "carpentry", "millwork", "ceramic", "tile",
    "design build", "design-build",
    # Secondary — luxury real estate top producers + premium design.
    "real estate", "realty", "interior design", "landscape",
)
# Removed 2026-08-09: the automotive vocabulary ADR-0012 demoted (dealer,
# dealership, rental, detail, ppf, paint protection, wrap, tint, performance,
# tuning, motorsport, collision) and med spa/medspa (ADR-0015). "restoration"
# and "ceramic" are KEPT despite their automotive origin — home and
# water-damage restoration, and ceramic tile, are real remodeling work, so
# dropping them would cost genuine remodelers points.
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
      +20 luxury/premium keyword in the BUSINESS NAME (can-afford-$4k signal)
      +10 ICP vertical keyword in the BUSINESS NAME
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
    # BUSINESS NAME ONLY (2026-08-09). This used to be
    #     f"{business} {vertical} {niche}"
    # and `worker.py` sets lead["vertical"] to the SEARCH QUERY STRING. So the
    # two ICP components scored the query rather than the business: every lead
    # returned by 'luxury home remodeling washington' collected +20 luxury and
    # +10 vertical, making 30 of 100 points a constant per hunt run.
    #
    # Measured on the 13 live leads that day: nytimes.com and amazon.com scored
    # 65 WARM — identical to every real WA contractor — and customink.com, a
    # t-shirt company, scored 100 HOT, the highest-ranked lead in the pipeline.
    # Real-vs-junk separation was NEGATIVE (-1.2); on name alone it is +8.8.
    #
    # This is the "scorer inversion" flagged in the 2026-08-02 comment above,
    # generalized: that note framed it as an automotive-exemption problem, but
    # any query term leaks into every lead the query returns.
    haystack = (lead.get("business") or "").lower()

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
