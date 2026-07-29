import os
import logging
import asyncio
import re
import json
import socket
import httpx
from urllib.parse import quote
from typing import Optional
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup

from app.skills.light_enrich import ad_signals_json

logger = logging.getLogger(__name__)

# Shared httpx client — reuse across all enrichment calls instead of creating per-call
_shared_http_client: Optional[httpx.AsyncClient] = None


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient, creating it lazily on first use."""
    global _shared_http_client
    if _shared_http_client is None or _shared_http_client.is_closed:
        _shared_http_client = httpx.AsyncClient(timeout=15.0, follow_redirects=True)
    return _shared_http_client


async def _close_http_client() -> None:
    """Close the shared httpx client and clear the module reference.

    Call from app shutdown (lifespan) so the underlying connection pool is released.
    """
    global _shared_http_client
    if _shared_http_client is not None and not _shared_http_client.is_closed:
        await _shared_http_client.aclose()
    _shared_http_client = None

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD GEN V3 — Advanced Lead Generation with 4-Strategy Enrichment Chain
# ═══════════════════════════════════════════════════════════════════════════════
# 
# Enrichment Chain (4 Strategies):
#   1. Website scraping (homepage, /contact, /about) → owner name + email + phone
#   2. WHOIS domain lookup → registrant name + org + email
#   3. State business registry lookup → owner name + contact info
#   4. DDG site-search → owner/CEO mentions for verification
#
# Output: Clean JSON with only owner_name, email, phone
#

BANNED_DOMAINS = [
    "wikipedia.org", "reddit.com", "youtube.com", "pinterest.com",
    "quora.com", "medium.com", "twitter.com", "tiktok.com",
    "dictionary.com", "merriam-webster.com", "thefreedictionary.com",
    "britannica.com", "facebook.com", "instagram.com", "yelp.com/search",
    "pornhub.com", "xvideos.com", "xnxx.com",
]

FALSE_POSITIVE_NAMES = frozenset({
    "About Us", "Contact Us", "Read More", "Learn More", "Our Team",
    "Get Started", "Meet Our", "Our Story", "Click Here", "Sign Up",
    "Log In", "View More", "See All", "Find Out", "Call Now",
    "Free Quote", "Get Quote", "Request Quote", "Schedule Now",
    "Book Now", "In Silver Lake",
})

def _is_plausible_name(text: str) -> bool:
    # Canonical check moved to lead_validator.is_plausible_person_name
    # (three divergent copies let "THANKS TO" through, live 2026-07-20);
    # this module keeps only its extra FALSE_POSITIVE_NAMES denylist.
    from app.skills.lead_validator import is_plausible_person_name
    if text in FALSE_POSITIVE_NAMES:
        return False
    return is_plausible_person_name(text)

def _normalize_phone_to_e164(phone: str) -> str:
    """Validate and format phone to E.164 using the `phonenumbers` library.
    
    Falls back to basic digit-based formatting if phonenumbers is unavailable.
    Retains fake-number pre-checks (repeated digits, sequential, 999-prefix).
    """
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 10:
        return ""
    raw_number = digits[-10:]
    # Reject repeated digits
    if len(set(raw_number)) == 1:
        return ""
    # Reject sequential patterns
    sequential_patterns = ["1234567890", "9876543210", "0123456789"]
    if raw_number in sequential_patterns:
        return ""
    # Reject numbers starting with 999
    if raw_number.startswith("999"):
        return ""
    
    # ── phonenumbers library (proper validation) ──
    try:
        import phonenumbers
        parsed = phonenumbers.parse(phone, "US")
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        return ""
    except Exception:
        pass  # Fall through to basic formatting
    
    # ── Fallback: basic digit formatting ──
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    else:
        return f"+{digits}"


# Regex patterns
PHONE_RE = re.compile(r'\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}')
# Extended phone: international, extensions, dotted, tel: links
PHONE_RE_EXTENDED = re.compile(
    r'(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}'
    r'(?:\s*(?:ext|extension|x|#)\s*\d{2,6})?',
    re.IGNORECASE
)
EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)

def _extract_phones_from_html(html: str) -> list:
    """Extract ALL phone numbers from HTML including tel: links and data attributes."""
    phones = []
    if not html:
        return phones
    
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. tel: href links (highest quality)
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.lower().startswith("tel:"):
            raw = href[4:].split("?")[0].strip()
            normalized = _normalize_phone_to_e164(raw)
            if normalized and normalized not in phones:
                phones.append(normalized)
    
    # 2. data-* attributes with phone
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if isinstance(val, str) and "phone" in attr.lower():
                for m in PHONE_RE_EXTENDED.findall(val):
                    normalized = _normalize_phone_to_e164(m)
                    if normalized and normalized not in phones:
                        phones.append(normalized)
    
    # 3. Full text regex (extended pattern)
    text = soup.get_text(separator=" ", strip=True)
    for m in PHONE_RE_EXTENDED.findall(text):
        normalized = _normalize_phone_to_e164(m)
        if normalized and normalized not in phones:
            phones.append(normalized)
    
    return phones
OWNER_PATTERNS = [
    re.compile(r'(?:owner|co[-\s]?owner|founder|co[-\s]?founder|ceo|chief\s+executive|president|principal|operator|partner|managing\s+director|managing\s+partner|director)[:\s,\-–]+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,3})', re.IGNORECASE),
    re.compile(r'([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,3})[,\s\-–]+(?:owner|co[-\s]?owner|founder|co[-\s]?founder|ceo|chief\s+executive|president|principal|operator|partner|managing\s+director|managing\s+partner)', re.IGNORECASE),
    re.compile(r"I(?:'m| am)\s+([A-Za-z\'\-]+\s+[A-Za-z\'\-]+),?\s*(?:owner|founder|ceo|president|principal)", re.IGNORECASE),
    re.compile(r'(?:founded|owned|run|operated|started|led)\s+by\s+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})', re.IGNORECASE),
    re.compile(r'(?:meet|introducing)\s+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})[,\s]+(?:our\s+)?(?:owner|founder|ceo|president)', re.IGNORECASE),
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*[-–—]\s*(?:owner|ceo|president|founder|director|principal|partner)', re.IGNORECASE),
    re.compile(r'(?:proprietor|managing\s+member|general\s+partner|executive\s+director)[:\s,\-–]+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,3})', re.IGNORECASE),
]

ABOUT_PAGES = ["/about", "/team", "/contact", "/about-us", "/our-team", "/our-story",
               "/our-company", "/company", "/leadership", "/staff", "/people",
               "/meet-the-team", "/our-people", "/management"]
CONTACT_PAGES = ["/contact", "/contact-us", "/contactus", "/connect",
                 "/get-in-touch", "/reach-us", "/request-quote"]


def normalize_url(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        query = parse_qs(parsed.query)
        for param in ["utm_source", "utm_medium", "utm_campaign", "gclid", "fbclid"]:
            query.pop(param, None)
        cleaned = parsed._replace(query=urlencode(query, doseq=True), fragment="")
        return urlunparse(cleaned)
    except Exception:
        return url


def extract_domain(url: str) -> str:
    try:
        host = httpx.URL(url).host or ""
        parts = host.replace("www.", "").split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return ""


def is_banned_url(url: str) -> bool:
    try:
        host = httpx.URL(url).host or ""
        return any(d in host for d in BANNED_DOMAINS)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 1: Website Scraping (homepage, contact, about pages)
# ═══════════════════════════════════════════════════════════════════════════════

async def _ai_extract_owner(page_text: str, host: str) -> dict:
    """Extract owner/email/phone from page text via UnifiedAIClient.

    Render-safe (no browser). UnifiedAIClient falls Groq -> Gemini -> OpenRouter
    free models, so this works whenever any provider key is live. Returns {} on
    any failure so the caller keeps its regex result.
    """
    page_text = (page_text or "").strip()
    if not page_text:
        return {}
    try:
        from app.core.ai_client import UnifiedAIClient
        ai = UnifiedAIClient()
        prompt = (
            "From the website text below, extract the business OWNER / founder / "
            "principal's full name, a personal-looking email (prefer a named address "
            "over info@/contact@), and a direct phone. "
            f"Business domain: {host}\n\nText:\n{page_text[:6000]}\n\n"
            "Return ONLY JSON: {\"owner_name\": str|null, \"email\": str|null, "
            "\"phone\": str|null}. Use null when not clearly present — never guess."
        )
        resp = await ai.chat(prompt, role="hawk", temperature=0.1, max_tokens=180)
        content = getattr(resp, "content", None) or (resp if isinstance(resp, str) else "")
        m = re.search(r"\{.*\}", content or "", re.DOTALL)
        if not m:
            return {}
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"[SCRAPE] AI owner extract failed: {e}")
        return {}


async def _scrape_website(url: str) -> dict:
    """Scrape website for owner name, email, and phone. Scans up to 7 pages and collects ALL candidates."""
    result = {"owner_name": "", "email": "", "phone": "", "ad_signals": ""}
    
    if not url:
        return result
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        base_url = url.rstrip("/")
        host = httpx.URL(url).host or ""
        
        # Collect ALL candidate emails and phones across pages, then pick best
        all_emails = []
        all_phones = []
        
        client = await _get_http_client()
        # Owner names live on about/team/leadership pages — check those FIRST so
        # they are not cut off by the page cap (contact pages mainly give email/phone).
        ordered_paths = []
        for path in ABOUT_PAGES + CONTACT_PAGES:
            if path not in ordered_paths:
                ordered_paths.append(path)
        pages_to_check = [base_url] + [f"https://{host}{path}" for path in ordered_paths]

        all_text = []  # accumulate cleaned text for the AI pass
        # Scan up to 9 pages (homepage + about/team + contact)
        for page_url in pages_to_check[:9]:
            try:
                resp = await client.get(page_url, timeout=8.0, headers=headers)
                if resp.status_code != 200:
                    continue

                text = resp.text

                # Ad signals off the first page we actually get (the homepage
                # unless it 404s). Pixels and marketplace badges live in the
                # site-wide <head>/footer template, so any reachable page
                # carries them. This hook is what covers leads that arrive
                # already-complete: light_enrich's Step 2 short-circuits when
                # owner+email+phone are all set and then never fetches a
                # homepage at all — which is exactly the best leads.
                if not result["ad_signals"]:
                    result["ad_signals"] = ad_signals_json(text)

                # Extract ALL phones using enhanced extraction (tel: links, data attrs, extended regex)
                phones = _extract_phones_from_html(text)
                for p in phones:
                    if p not in all_phones:
                        all_phones.append(p)

                # Extract ALL emails (not just first)
                emails = EMAIL_RE.findall(text)
                for e in emails:
                    if _is_valid_business_email(e) and e.lower() not in all_emails:
                        all_emails.append(e.lower())

                clean = re.sub(r'<[^>]+>', ' ', text)
                clean = re.sub(r'\s+', ' ', clean)
                if len(" ".join(all_text)) < 6000:
                    all_text.append(clean)

                # Extract owner name (first plausible wins)
                if not result["owner_name"]:
                    for pattern in OWNER_PATTERNS:
                        match = pattern.search(clean)
                        if match:
                            name = match.group(1).strip()
                            if _is_plausible_name(name):
                                result["owner_name"] = name
                                break

                # Early exit only if we have ALL three fields
                if result["owner_name"] and all_emails and all_phones:
                    break

            except Exception:
                continue

        # Pick best email from all collected
        if all_emails and not result["email"]:
            result["email"] = _prioritize_email(all_emails)

        # Pick best phone from all collected
        if all_phones and not result["phone"]:
            result["phone"] = all_phones[0]

        # AI pass (Render-safe UnifiedAIClient) fills what regex missed —
        # owner names phrased in ways the patterns don't catch.
        if all_text and not (result["owner_name"] and result["email"]):
            ai_data = await _ai_extract_owner(" ".join(all_text), host)
            if not result["owner_name"] and ai_data.get("owner_name"):
                if _is_plausible_name(ai_data["owner_name"]):
                    result["owner_name"] = ai_data["owner_name"]
            if not result["email"] and ai_data.get("email") and _is_valid_business_email(ai_data["email"]):
                result["email"] = ai_data["email"].lower()
            if not result["phone"] and ai_data.get("phone"):
                norm = _normalize_phone_to_e164(ai_data["phone"])
                if norm:
                    result["phone"] = norm

    except Exception as e:
        logger.debug(f"[SCRAPE] Error for {url}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 2: WHOIS Enrichment
# ═══════════════════════════════════════════════════════════════════════════════

async def _whois_lookup(domain: str) -> dict:
    """Perform WHOIS lookup via free RDAP API (no API key needed).
    
    RDAP (Registration Data Access Protocol) is the IETF standard
    replacing legacy WHOIS. https://rdap.org is a free bootstrap
    server that redirects to the correct registry — no API key,
    no rate limit, no cost.
    """
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not domain:
        return result
    
    # ── Primary: Free RDAP API ──────────────────────────────────
    try:
        rdap_url = f"https://rdap.org/domain/{domain}"
        headers = {
            "Accept": "application/rdap+json, application/json",
            "User-Agent": "OROVA-Enrichment/1.0",
        }
        client = await _get_http_client()
        resp = await client.get(rdap_url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            
            # Extract from entities (RDAP standard structure)
            entities = data.get("entities", [])
            for entity in entities:
                roles = entity.get("roles", [])
                vcard = entity.get("vcardArray", [])
                
                # Registrant is the domain owner
                if "registrant" in roles:
                    # vcardArray format: ["vcard", [[fn, {}, "text", "Name"], ...]]
                    if len(vcard) >= 2 and isinstance(vcard[1], list):
                        for field in vcard[1]:
                            if len(field) >= 4 and field[0] == "fn":
                                _cand = str(field[3]).strip()
                                if _is_plausible_name(_cand):  # skip WHOIS org/privacy names
                                    result["owner_name"] = _cand
                            elif len(field) >= 4 and field[0] == "email":
                                _e = str(field[3]).strip()
                                if _is_valid_business_email(_e):
                                    result["email"] = _e
                            elif len(field) >= 4 and field[0] == "tel":
                                result["phone"] = str(field[3]).strip()

                # Also check administrative/technical contacts
                if "administrative" in roles and not result["owner_name"]:
                    if len(vcard) >= 2 and isinstance(vcard[1], list):
                        for field in vcard[1]:
                            if len(field) >= 4 and field[0] == "fn":
                                _cand = str(field[3]).strip()
                                if _is_plausible_name(_cand):
                                    result["owner_name"] = _cand
            
            # Fallback: check top-level name/handle fields
            if not result["owner_name"]:
                ldh_name = data.get("ldhName", "")
                # Some registries put org name in events or notices
                for notice in data.get("notices", []):
                    desc = " ".join(notice.get("description", []))
                    if desc and len(desc) < 200 and not result["owner_name"]:
                        # Only accept a description that is actually a person name
                        if _is_plausible_name(desc.strip()):
                            result["owner_name"] = desc.strip()
    except Exception as e:
        logger.debug(f"[RDAP] Error for {domain}: {e}")
    
    # ── Fallback: whois.vu (free, no key) ───────────────────────
    if not result["owner_name"]:
        try:
            alt_url = f"https://api.whois.vu/?q={domain}"
            client = await _get_http_client()
            resp = await client.get(alt_url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("registrant") and _is_plausible_name(str(data["registrant"]).strip()):
                    result["owner_name"] = str(data["registrant"]).strip()
                if data.get("email") and _is_valid_business_email(str(data["email"])):
                    result["email"] = data["email"]
        except Exception:
            pass
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 3: State Business Registry Lookup
# ═══════════════════════════════════════════════════════════════════════════════

STATE_REGISTRY_URLS = {
    "CA": "https://bizfile.sos.ca.gov/api/businesssearch",
    "TX": "https://direct.sos.state.tx.us/acct/acctsearch.asp",
    "FL": "https://search.sunbiz.org/Inquiry/CorporationSearch",
    "NY": "https://appext20.dos.ny.gov/pls/dosprod.search_businesses",
    "WA": "https://ccfs.sos.wa.gov/api/BusinessSearch",
    "CO": "https://www.sos.state.co.us/biz/BusinessSearchCriteria.do",
    "AZ": "https://azcc.gov/search/business",
    "GA": "https://ecorp.sos.ga.gov/BusinessSearch",
    "NC": "https://www.sosnc.gov/online_services/search/by_title/_llc",
    "IL": "https://www.ilsos.gov/entitysearch/",
    "OH": "https://businesssearch.ohiosos.gov/",
    "PA": "https://www.corporations.pa.gov/search/corpsearch",
    "NJ": "https://www.nj.gov/lpbs/businesssearch/",
    "MA": "https://corp.sec.state.ma.us/corpweb/CorpSearch/CorpSearch.aspx",
    "VA": "https://cis.scc.virginia.gov/",
}

async def _state_registry_lookup(business_name: str, state: str = "") -> dict:
    """Look up business in state registry for owner info."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not business_name:
        return result
    
    # Extract state from business name if not provided
    if not state:
        state_match = re.search(r'\b(CA|TX|FL|NY|WA|CO|AZ|GA|NC|IL|OH|PA|NJ|MA|VA)\b', business_name.upper())
        state = state_match.group(1) if state_match else ""
    
    if state not in STATE_REGISTRY_URLS:
        # Try top states if no state specified
        for fallback_state in ["CA", "TX", "FL", "NY"]:
            if fallback_state in STATE_REGISTRY_URLS:
                state = fallback_state
                break
        if state not in STATE_REGISTRY_URLS:
            return result
    
    try:
        registry_url = STATE_REGISTRY_URLS[state]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; KiloBot/1.0)",
        }
        
        params = {"q": business_name}
        
        client = await _get_http_client()
        resp = await client.get(registry_url, params=params, headers=headers)
        if resp.status_code == 200:
            text = resp.text
            
            if "registered agent" in text.lower() or "agent" in text.lower():
                agent_match = re.search(r'(?:Registered\s+)?Agent[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text, re.IGNORECASE)
                if agent_match:
                    result["owner_name"] = agent_match.group(1)
            
            if not result["email"]:
                for _e in EMAIL_RE.findall(text):
                    if _is_valid_business_email(_e):
                        result["email"] = _e.lower()
                        break
    except Exception as e:
        logger.debug(f"[REGISTRY] Error for {business_name}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 4: DDG Site Search for Owner Mentions
# ═══════════════════════════════════════════════════════════════════════════════

async def _ddg_owner_verification(url: str, domain: str) -> dict:
    """Use DuckDuckGo to verify owner name via site search.
    
    Runs multiple query patterns to maximize hit rate:
    1. site-scoped title search (original)
    2. broad "owner of" query
    3. LinkedIn / BBB / Manta cross-reference
    """
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not domain:
        return result
    
    # Multiple query patterns — each targets a different angle
    search_queries = [
        f'site:{domain} "Owner" OR "CEO" OR "Founder"',
        f'"owner of" OR "founded by" "{domain}"',
        f'"{domain}" owner OR president OR principal',
        f'site:linkedin.com "{domain}" owner OR founder',
        f'site:bbb.org "{domain}" owner OR principal',
        f'site:manta.com "{domain}" owner',
    ]
    
    try:
        def _search(query):
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=5, safesearch="strict"))
        
        for query in search_queries:
            if result["owner_name"]:
                break
            try:
                results = await asyncio.get_running_loop().run_in_executor(None, _search, query)
                
                for res in results:
                    combined = (res.get("title", "") + " " + res.get("body", "")).lower()
                    # Skip results that are just LinkedIn/Facebook directory pages
                    if "linkedin.com/in/" in combined or "facebook.com/" in combined:
                        continue
                    text = res.get("body", "") + " " + res.get("title", "")
                    for pattern in OWNER_PATTERNS:
                        match = pattern.search(text)
                        if match:
                            name = match.group(1).strip()
                            if _is_plausible_name(name):
                                result["owner_name"] = name
                                break
                    if result["owner_name"]:
                        break
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[DDG-VERIFY] Error for {domain}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 5: BBB.org Profile Lookup
# ═══════════════════════════════════════════════════════════════════════════════

async def _bbb_lookup(business_name: str, domain: str = "") -> dict:
    """Scrape BBB.org for owner/principal name and contact info."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not business_name:
        return result
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Search BBB for the business
        search_url = f"https://www.bbb.org/search?find_country=USA&find_entity={quote(business_name)}"
        
        client = await _get_http_client()
        resp = await client.get(search_url, headers=headers)
        if resp.status_code != 200:
            return result
        
        text = resp.text
        
        # Look for owner/principal/contact name patterns on BBB pages
        bbb_patterns = [
            re.compile(r'(?:Principal|Owner|Contact|Manager)[:\s]+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})', re.IGNORECASE),
            re.compile(r'(?:Business\s+Owner|Owner/Manager)[:\s]+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})', re.IGNORECASE),
        ]
        
        for pattern in bbb_patterns:
            match = pattern.search(text)
            if match:
                name = match.group(1).strip()
                if _is_plausible_name(name):
                    result["owner_name"] = name
                    break
        
        # Extract phone from BBB listing
        phones = _extract_phones_from_html(text)
        if phones:
            result["phone"] = phones[0]
        
        # Extract email
        emails = EMAIL_RE.findall(text)
        for e in emails:
            if _is_valid_business_email(e):
                result["email"] = e.lower()
                break

    except Exception as e:
        logger.debug(f"[BBB] Error for {business_name}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 6: Google Business Profile Lookup
# ═══════════════════════════════════════════════════════════════════════════════

async def _google_business_lookup(business_name: str, domain: str = "") -> dict:
    """Search Google for business profile info (maps, knowledge panel)."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not business_name:
        return result
    
    try:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    f'"{business_name}" owner OR founder OR CEO phone',
                    max_results=5,
                    safesearch="strict"
                ))
        
        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        
        for res in results:
            text = res.get("body", "") + " " + res.get("title", "")
            
            # Extract owner name
            if not result["owner_name"]:
                for pattern in OWNER_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        name = match.group(1).strip()
                        if _is_plausible_name(name):
                            result["owner_name"] = name
                            break
            
            # Extract phone
            if not result["phone"]:
                phones = PHONE_RE_EXTENDED.findall(text)
                for p in phones:
                    normalized = _normalize_phone_to_e164(p)
                    if normalized:
                        result["phone"] = normalized
                        break
            
            # Extract email
            if not result["email"]:
                emails = EMAIL_RE.findall(text)
                for e in emails:
                    if _is_valid_business_email(e):
                        result["email"] = e.lower()
                        break
            
            if result["owner_name"] and result["phone"]:
                break
                
    except Exception as e:
        logger.debug(f"[GBIZ] Error for {business_name}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT CHAIN - Combines all 6 strategies with prioritization
# ═══════════════════════════════════════════════════════════════════════════════

# Generic inbox local-parts, best-to-worst. A PERSONAL address (not in this set)
# always beats these — we want to reach the owner, not a shared inbox.
_GENERIC_LOCALPARTS = [
    "owner", "founder", "ceo", "president", "principal",   # decision-maker inboxes
    "manager", "office", "admin",
    "sales", "hello", "contact", "enquiries", "inquiries",
    "info", "support", "help", "team",
]
_JUNK_LOCALPARTS = {"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster"}

# Domains (and any subdomain of them) that never belong to a prospect's inbox —
# platform/telemetry addresses scraped out of page source. Must be suffix-matched:
# exact-match let 605a...@sentry-next.wixpress.com through as a lead email
# (live-observed 2026-07-13).
_NOISE_EMAIL_DOMAINS = (
    "example.com", "domain.com", "test.com", "yourdomain.com",
    "wix.com", "wixpress.com", "squarespace.com", "sentry.io", "bbb.org",
)

def _is_noise_email(email: str) -> bool:
    """True if the email's domain is (or is a subdomain of) a noise domain."""
    domain = email.rsplit("@", 1)[-1].lower()
    return any(domain == d or domain.endswith("." + d) for d in _NOISE_EMAIL_DOMAINS)

# The loose EMAIL_RE (…@dom.\w{2,}) can't tell a real TLD from a scraped asset
# filename or trailing page text, so it produced junk "emails" that reached the
# DB (2026-07-13): a-logo-black-@1x.png, info@…phfooterLink, hex@ingest-prd.
# sentry.zalora.net. _is_valid_business_email() is the gate every accepted email
# must pass.
_ASSET_TLDS = frozenset({
    "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tiff", "tif",
    "css", "js", "mjs", "json", "xml", "html", "htm", "pdf", "mp4", "mp3",
    "woff", "woff2", "ttf", "eot", "otf", "zip", "gz", "webmanifest", "map",
})
# Business gTLDs; any 2-letter alpha suffix is accepted as a ccTLD. Generous on
# purpose — dropping a real lead's email costs more than storing a rare junk
# one, and the ICP (auto / real-estate / high-end services) uses niche gTLDs.
_KNOWN_GTLDS = frozenset({
    # generic / most common
    "com", "net", "org", "io", "co", "biz", "info", "dev", "app", "xyz",
    "online", "site", "store", "shop", "email", "live", "group", "company",
    "pro", "tv", "me", "cc", "ws", "name", "mobi", "edu", "gov", "mil",
    # automotive ICP
    "cars", "auto", "autos", "dealer", "car", "tires", "motorcycles", "bike",
    "limo", "parts",
    # real-estate / builder ICP
    "realtor", "realty", "estate", "homes", "house", "build", "builders",
    "construction", "properties", "property", "rentals", "land", "villas",
    # premium / services
    "luxury", "vip", "gold", "style", "design", "studio", "agency", "media",
    "digital", "marketing", "services", "solutions", "consulting", "capital",
    "ventures", "expert", "guru", "tech", "systems", "works", "world", "life",
    "club", "care", "coach", "events", "photography", "fashion", "jewelry",
    # common geo
    "la", "nyc", "vegas", "miami", "london", "us", "uk", "ca",
})
# Any domain containing one of these markers is platform/telemetry, never a
# prospect inbox (catches sentry.zalora.net, ingest-prd.*, etc.).
_NOISE_DOMAIN_MARKERS = ("sentry", "ingest", "wixpress", "cloudfront",
                         "googleusercontent", "gstatic", "w3.org", "schema.org")

def _valid_tld(domain: str) -> bool:
    tld = domain.rsplit(".", 1)[-1]
    if tld in _ASSET_TLDS:
        return False
    if len(tld) == 2 and tld.isalpha():   # ccTLD (us, ca, ph, uk, …)
        return True
    return tld in _KNOWN_GTLDS

def _is_valid_business_email(email: str) -> bool:
    """The single gate for accepting a scraped email. Rejects malformed captures
    (asset filenames, trailing junk making a bogus TLD), telemetry/platform
    domains, and noreply-style localparts."""
    email = (email or "").strip().lower().rstrip(".")
    if email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    if not local or "." not in domain or ".." in domain:
        return False
    if local in _JUNK_LOCALPARTS:
        return False
    if _is_noise_email(email):
        return False
    if any(marker in domain for marker in _NOISE_DOMAIN_MARKERS):
        return False
    return _valid_tld(domain)

def _prioritize_email(emails: list) -> str:
    """Pick the best email: personal address first, then the most useful generic
    inbox. Junk (noreply etc.) is dropped entirely."""
    cleaned = [e for e in emails if _is_valid_business_email(e)]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    def email_score(email: str) -> int:
        local = email.split("@", 1)[0].lower()
        for i, prefix in enumerate(_GENERIC_LOCALPARTS):
            if local == prefix or local.startswith(prefix + "."):
                return 1 + i  # generic inbox, ranked by usefulness
        return 0  # personal-looking address — best

    return sorted(cleaned, key=email_score)[0]


async def enrich_lead_4step(url: str, business_name: str = "", state: str = "", score: float = 0.0) -> dict:
    """
    Owner-name-FIRST enrichment: try the public-registry resolver before the
    6-strategy text-mining chain (see app/skills/owner_finder.py). Registry
    hits are real officer/agent names from a legal filing — short-circuit
    the free-text owner_name strategies below on a hit, but still run them
    for email/phone since those aren't the registry's job.
    Returns clean output with owner_name, email, phone only.
    """
    domain = extract_domain(url) if url else ""

    registry_owner = ""
    registry_title = ""
    registry_source = ""
    try:
        from app.skills.owner_finder import resolve_owner
        hit = await resolve_owner(business_name, state=state, domain=domain, score=score)
        if hit.get("owner"):
            registry_owner = hit["owner"]
            registry_title = hit.get("title", "")
            # resolve_owner names its winning stage (ca_registry, wa_registry,
            # opencorporates, website, serpapi) — keep it; a registry officer
            # name from a legal filing outranks any text-mined guess.
            registry_source = hit.get("source", "owner_finder")
    except Exception as e:
        logger.debug(f"[ENRICH] owner_finder registry lookup failed for {business_name}: {e}")

    # Run all strategies concurrently. Removed three junk producers (live-verified
    # 2026-07-05): _state_registry_lookup returned the registry's own contact email
    # (bizfile@sos.ca.gov), _whois_lookup returned WHOIS boilerplate as an "owner"
    # ("Service subject to Terms of Use"), and _ddg_owner_verification uses the
    # deprecated duckduckgo_search. Real owner names come from owner_finder (above)
    # + _scrape_website; email/phone from the site and Google Business.
    # Priority = list order: the business's own site over BBB over Google.
    strategies = [
        ("website", _scrape_website(url)),
        ("bbb", _bbb_lookup(business_name, domain)),
        ("google_business", _google_business_lookup(business_name, domain)),
    ]
    strategy_results = await asyncio.gather(*(coro for _, coro in strategies),
                                            return_exceptions=True)
    results = [(name, res) for (name, _), res in zip(strategies, strategy_results)
               if isinstance(res, dict)]

    # Merge in priority order, RECORDING the source of every field — the old
    # merge collapsed everything anonymously, so Mission Control could never
    # tell a legal-filing officer name from an AI-scraped guess.
    final = {"owner_name": registry_owner, "owner_title": registry_title,
             "email": "", "phone": "",
             "owner_source": registry_source if registry_owner else "",
             "email_source": "", "phone_source": "",
             "email_status": "", "phone_verified": False, "ad_signals": ""}

    phones_seen: dict = {}  # source -> E.164, for cross-source corroboration
    for src, res in results:
        if res.get("ad_signals") and not final["ad_signals"]:
            final["ad_signals"] = res["ad_signals"]
        if res.get("email") and not final["email"]:
            final["email"] = res["email"]
            final["email_source"] = src
            final["email_status"] = "found"
        norm = _normalize_phone_to_e164(res.get("phone", "")) if res.get("phone") else ""
        if norm:
            phones_seen[src] = norm
            if not final["phone"]:
                final["phone"] = norm
                final["phone_source"] = src
        if res.get("owner_name") and not final["owner_name"]:
            final["owner_name"] = res["owner_name"]
            final["owner_source"] = src

    # Two independent sources agreeing on the same number is real verification
    # (site + Google Business Profile is the classic pair).
    if final["phone"] and list(phones_seen.values()).count(final["phone"]) >= 2:
        final["phone_verified"] = True

    # Fallback: pattern-guessed email — mark it GUESSED. The old code returned
    # the guess bare and light_enrich later stamped unlabeled emails 'found',
    # so guesses masqueraded as scraped facts (confidence 65 instead of 35).
    if not final["email"] and final["owner_name"] and domain:
        guess = _guess_email(final["owner_name"], domain)
        if guess:
            final["email"] = guess
            final["email_source"] = "pattern_guess"
            final["email_status"] = "guessed"

    return final


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL GUESS — Generate likely email patterns when enrichment fails
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_GUESS_PATTERNS = [
    lambda first, last, domain: f"{first}@{domain}",
    lambda first, last, domain: f"{first}.{last}@{domain}",
    lambda first, last, domain: f"{first[0]}{last}@{domain}",
    lambda first, last, domain: f"{first}{last[0]}@{domain}",
    lambda first, last, domain: f"{first}.{last[0]}@{domain}",
    lambda first, last, domain: f"{first[0]}.{last}@{domain}",
    lambda first, last, domain: f"{first}_{last}@{domain}",
    lambda first, last, domain: f"{first[0]}_{last}@{domain}",
    lambda first, last, domain: f"{last}@{domain}",
    lambda first, last, domain: f"{first}{last}@{domain}",
]

def _guess_email(owner_name: str, domain: str) -> str:
    """Generate likely email patterns from owner name + domain. MX-verifies domain first. Returns empty if can't parse name or domain has no MX."""
    if not owner_name or not domain:
        return ""
    
    # MX-verify domain before guessing (free, no API key)
    try:
        import dns.resolver
        dns.resolver.resolve(domain, "MX", lifetime=3)
    except Exception:
        # Fallback: basic connectivity check
        try:
            socket.gethostbyname(domain)
        except Exception:
            return ""  # Domain doesn't exist or can't receive mail
    
    parts = owner_name.strip().lower().split()
    if len(parts) < 2:
        return ""
    
    first = parts[0]
    last = parts[-1]
    
    # Remove middle initials/names for pattern generation
    # e.g. "John A. Smith" → first="john", last="smith"
    
    # Clean special chars
    first = re.sub(r'[^a-z]', '', first)
    last = re.sub(r'[^a-z]', '', last)
    
    if not first or not last:
        return ""
    
    # Return the most common pattern: first@domain
    # The actual verification happens when AgentMail sends
    return f"{first}@{domain}"


# ═══════════════════════════════════════════════════════════════════════════════
# LEAD SOURCES (Google Maps, DDG, Yelp)
# ═══════════════════════════════════════════════════════════════════════════════

async def _source_google_maps(query: str, count: int) -> list:
    """Scrape Google Maps mobile search page."""
    leads = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
        }
        search_url = f"https://www.google.com/maps/search/{quote(query)}"
        
        client = await _get_http_client()
        resp = await client.get(search_url, headers=headers)
        if resp.status_code != 200:
            return leads
        
        html = resp.text
        json_match = re.search(r'window\.APP_INITIALIZATION_STATE\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                for item in data[3] if len(data) > 3 else []:
                    if isinstance(item, list) and len(item) >= 5:
                        business = ""
                        phone = ""
                        website = ""
                        i = 0
                        while i < len(item):
                            val = item[i]
                            if isinstance(val, str):
                                if not business and i >= 2 and not val.startswith("http"):
                                    business = val
                                if PHONE_RE.match(val):
                                    phone = val
                                if val.startswith("http") and "google.com" not in val:
                                    website = val
                            i += 1
                        if business:
                            leads.append({
                                "business": business,
                                "url": website or "",
                                "phone": phone,
                            })
                            if len(leads) >= count:
                                break
            except Exception:
                pass
    except Exception as e:
        logger.error(f"[GMAPS] Error: {e}")
    return leads[:count]


async def _source_duckduckgo(query: str, count: int) -> list:
    """DDGS search for business websites."""
    leads = []
    try:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=count, safesearch="strict", region="us-en"))
        
        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        seen_domains = set()
        
        for res in results:
            url = res.get("href", res.get("link", ""))
            if not url or not url.startswith("http") or is_banned_url(url):
                continue
            domain = extract_domain(url)
            if domain in seen_domains:
                continue
            seen_domains.add(domain)
            leads.append({
                "business": "",
                "url": url,
                "phone": "",
            })
            if len(leads) >= count:
                break
    except Exception as e:
        logger.error(f"[DDG] Error: {e}")
    return leads


# google_maps returns ~20 local_results per page; `start` pages through them.
_SERPAPI_MAPS_PAGE_SIZE = 20
# Bounded so a single hunt can never drain the shared monthly quota. 3 pages =
# up to ~60 businesses for 3 units of a 250/mo budget.
_SERPAPI_MAPS_MAX_PAGES = 3


async def _source_serpapi_maps(query: str, count: int,
                               max_pages: int = _SERPAPI_MAPS_MAX_PAGES) -> list:
    """Reliable discovery via SerpAPI's Google Maps engine.

    Returns real business name + phone + website + address. The DDG/Maps-scrape
    sources are deprecated/blocked server-side and return junk (WHOIS text,
    image filenames), which is why owner/email/phone yield was near zero. This
    shares the one SerpAPI monthly quota (250/mo) with owner_finder's SerpAPI
    fallback — it rations against the same counter and skips cleanly when the
    quota is spent or SERPAPI_KEY is unset (falls back to the legacy sources).

    Paginates rather than falling through to those legacy sources when a page
    comes up short. Two reasons:

    1. A page is billed whether or not we read it. The previous code sliced
       `[:count]` BEFORE the has-a-website filter, so it threw away results
       already paid for and then reported a shortfall it had manufactured.
    2. A DDG lead cannot become a customer. That source yields a bare URL —
       no name (the business becomes "otbaybuilders.com"), no phone (so the
       Retell lane can never dial it), and no address, so `_state_from_address`
       returns "" and owner_finder routes to the dead OpenCorporates branch.
       Spending one more quota unit on a structured page strictly beats it.
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []

    async def _ration_ok() -> bool:
        try:
            from app.skills.owner_finder import _ration_check_and_increment, SERPAPI_MONTHLY_CAP
            return await _ration_check_and_increment(
                "owner_finder:serp_monthly", SERPAPI_MONTHLY_CAP, "month")
        except Exception as e:
            logger.debug(f"[SERPMAPS] ration check unavailable ({e}); proceeding.")
            return True

    leads: list = []
    seen: set = set()
    pages_used = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(max(1, max_pages)):
                if len(leads) >= count:
                    break
                if not await _ration_ok():
                    logger.info("[SERPMAPS] SerpAPI monthly quota reached — "
                                f"stopping discovery after {pages_used} page(s).")
                    break
                resp = await client.get("https://serpapi.com/search", params={
                    "engine": "google_maps", "q": query, "type": "search",
                    "api_key": api_key, "start": page * _SERPAPI_MAPS_PAGE_SIZE,
                })
                pages_used += 1
                if resp.status_code != 200:
                    logger.warning(f"[SERPMAPS] SerpAPI status {resp.status_code} for '{query}'")
                    break
                results = resp.json().get("local_results") or []
                if not results:
                    break  # exhausted — further pages would just burn quota
                for b in results:
                    website = (b.get("website") or "").strip()
                    if not website:
                        continue  # need a site to enrich email/owner
                    domain = extract_domain(website)
                    if domain and domain in seen:
                        continue
                    if domain:
                        seen.add(domain)
                    leads.append({
                        "business": (b.get("title") or "").strip(),
                        "url": website,
                        "phone": (b.get("phone") or "").strip(),
                        "address": (b.get("address") or "").strip(),
                        "source": "serpapi_maps",
                    })
                if len(results) < _SERPAPI_MAPS_PAGE_SIZE:
                    break  # last page
        logger.info(f"[SERPMAPS] {len(leads)} businesses w/ websites for '{query}' "
                    f"({pages_used} page(s), {len(leads)}/{count} requested)")
    except Exception as e:
        logger.error(f"[SERPMAPS] Error: {e}")
    # Truncate AFTER filtering, never before — the old order discarded
    # website-bearing results in favour of phone-only listings that were
    # dropped a line later.
    return leads[:count]


# West Coast ICP state names as they appear in the free-text hunt query
# (e.g. "exotic car dealer california") — the only jurisdiction signal
# available at this call site today. Best-effort only; owner_finder routes
# to OpenCorporates when no state match is found.
_QUERY_STATE_HINTS = {"california": "CA", "washington": "WA", "oregon": "OR"}


def _infer_state_from_query(query: str) -> str:
    q = (query or "").lower()
    for name, code in _QUERY_STATE_HINTS.items():
        if name in q:
            return code
    return ""


_US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
_US_STATE_NAMES = {
    "california": "CA", "oregon": "OR", "washington": "WA", "nevada": "NV",
    "arizona": "AZ", "texas": "TX", "florida": "FL", "new york": "NY",
    "colorado": "CO", "utah": "UT", "idaho": "ID",
}


def _state_from_address(address: str) -> str:
    """US state code from an address string, or '' when not confidently found.

    Prefers the standard '..., CA 95030' / '..., CA,' form (validated against the
    real state codes), then a full state name. Never guesses — the registry
    (contact_waterfall._source_registry) needs the RIGHT state, so a wrong one is
    worse than none.
    """
    if not address:
        return ""
    a = str(address).strip()
    # Standard US mailing form: two-letter code before a ZIP, a comma, or the end.
    m = re.search(r",\s*([A-Za-z]{2})\b(?:\s*,|\s+\d{5}(?:-\d{4})?|\s*$)", a)
    if m and m.group(1).upper() in _US_STATE_CODES:
        return m.group(1).upper()
    al = a.lower()
    for name, code in _US_STATE_NAMES.items():
        if re.search(r"\b" + re.escape(name) + r"\b", al):
            return code
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def find_leads_v3(count: int = 5, query: str = "business leads") -> dict:
    """
    Main entry point with 4-strategy enrichment chain.
    Returns clean output: owner_name, email, phone only.
    """
    count = int(count)
    query = (query or "business leads").strip()
    state = _infer_state_from_query(query)
    logger.info(f"[LEAD GEN V3] Searching for {count} leads: '{query}'")
    
    all_leads = []

    # PRIMARY: SerpAPI Google Maps — reliable, structured business data.
    try:
        serp_leads = await _source_serpapi_maps(query, count * 3)
        all_leads.extend(serp_leads)
    except Exception as e:
        logger.warning(f"[V3] SerpAPI Maps failed: {e}")

    # LAST RESORT ONLY: the legacy scrape/DDG sources. These fire when SerpAPI
    # produced NOTHING (no key, or quota spent) — not merely when it came up
    # short, which is what let them dilute perfectly good runs.
    #
    # They are a different KIND of result, not just a worse one. Both yield a
    # bare URL: no business name (it degrades to the domain, so the call script
    # greets "otbaybuilders.com"), no phone (the Retell lane cannot dial), and
    # no address — so state resolves to "" and owner_finder routes to the dead
    # OpenCorporates branch, meaning the decision maker can never be found.
    # A lead from here can never reach outreach_ready, so topping up a partial
    # SerpAPI run with them adds rows to the dashboard and zero conversations.
    if not all_leads:
        logger.warning("[V3] SerpAPI produced nothing (no key or quota spent) — "
                       "falling back to legacy sources; expect URL-only leads "
                       "that cannot be called until re-enriched.")
        try:
            maps_leads = await _source_google_maps(query, count * 2)
            all_leads.extend(maps_leads)
        except Exception as e:
            logger.warning(f"[V3] Google Maps failed: {e}")

        try:
            ddg_leads = await _source_duckduckgo(query, count * 2)
            all_leads.extend(ddg_leads)
        except Exception as e:
            logger.warning(f"[V3] DuckDuckGo failed: {e}")
    
    # Deduplicate
    seen_domains = set()
    unique_leads = []
    for lead in all_leads:
        url = lead.get("url", "")
        if not url or not url.startswith("http") or is_banned_url(url):
            continue
        domain = extract_domain(url)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            unique_leads.append(lead)
    
    logger.info(f"[V3] Found {len(unique_leads)} unique leads to enrich")
    
    # Enrich with 4-strategy chain
    enriched_leads = []
    # Fan-out cap owned by app/core/hardening.CONCURRENCY_LIMITS.
    from app.core.hardening import concurrency_limit
    semaphore = asyncio.Semaphore(concurrency_limit("lead_enrich"))
    
    async def _enrich(lead):
        async with semaphore:
            result = await enrich_lead_4step(lead.get("url", ""), lead.get("business", ""), state=state)
            result["business"] = lead.get("business", "") or extract_domain(lead.get("url", "")) or "Unknown"
            # Prefer the Maps phone (normalized to E.164 so the call lane can
            # dial it) — and when Maps and an enrichment source agree on the
            # number, that's two independent sources: mark it verified.
            maps_phone = _normalize_phone_to_e164(lead.get("phone", ""))
            if maps_phone:
                if result.get("phone") and result["phone"] == maps_phone:
                    result["phone_verified"] = True
                    result["phone_source"] = f"maps+{result.get('phone_source') or 'enrichment'}"
                else:
                    result["phone"] = maps_phone
                    result["phone_source"] = "maps"
            result["website"] = result.get("website", "") or lead.get("url", "")
            # Persist the STATE so the decision-maker waterfall + reenrich lane can
            # fire the Secretary-of-State registry later (they read lead["state"];
            # without it the authoritative, zero-fabrication name source is dead).
            # Per-lead address is most accurate; fall back to the query-inferred state.
            result["state"] = _state_from_address(lead.get("address", "")) or state
            return result
    
    tasks = [_enrich(lead) for lead in unique_leads[:count * 2]]
    enriched_leads = await asyncio.gather(*tasks, return_exceptions=True)
    enriched_leads = [l for l in enriched_leads if isinstance(l, dict)]
    
    # Sort by completeness (leads with all 3 fields first)
    enriched_leads.sort(key=lambda l: sum(1 for f in [l.get("owner_name"), l.get("email"), l.get("phone")] if f), reverse=True)
    
    # Take top N
    final = enriched_leads[:count]
    
    # Build clean output — include ALL fields for sheets pipeline
    clean_output = []
    for lead in final:
        clean_output.append({
            "business": lead.get("business", ""),
            "owner_name": lead.get("owner_name", ""),
            "owner_title": lead.get("owner_title", ""),
            "email": lead.get("email", ""),
            "phone": lead.get("phone", ""),
            "website": lead.get("website", ""),
            "url": lead.get("url", ""),
            "score": lead.get("score", 0),
            "status": lead.get("status", "New"),
            # Provenance survives to storage — which source produced each
            # field, whether the email is found vs guessed, and whether two
            # independent sources corroborated the phone.
            "owner_source": lead.get("owner_source", ""),
            "email_source": lead.get("email_source", ""),
            "email_status": lead.get("email_status", ""),
            "phone_source": lead.get("phone_source", ""),
            "phone_verified": bool(lead.get("phone_verified", False)),
            # Paid-marketing signals read off their own homepage — "already
            # paying for leads" is the ICP qualifier (ADR-0012), so it has to
            # survive to storage, not die in the enrichment dict.
            "ad_signals": lead.get("ad_signals", ""),
            # The state _enrich() resolved above. Without it every stored lead
            # reaches owner_finder._registry_lookup with state="" and falls to
            # the OpenCorporates branch, which has no key — so the CA/WA/OR
            # Secretary-of-State lookups could never fire no matter what keys
            # were configured. This line is the whole point of computing it.
            "state": lead.get("state", ""),
        })
    
    if not clean_output:
        return {
            "text": f"No leads found for '{query}'. Try a more specific query like 'roofing contractors Miami'.",
            "leads": [],
        }
    
    # Build text summary
    lines = [f"**Found {len(clean_output)} Business Leads for '{query}':**\n"]
    for i, lead in enumerate(clean_output, 1):
        lines.append(
            f"{i}. **{lead.get('owner_name', 'Unknown')}**\n"
            f"   Email: {lead.get('email', '—')}\n"
            f"   Phone: {lead.get('phone', '—')}\n"
        )
    
    return {
        "text": "\n".join(lines),
        "leads": clean_output,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    async def _run_test():
        test_query = sys.argv[1] if len(sys.argv) > 1 else "roofing contractors Austin"
        test_count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        result = await find_leads_v3(count=test_count, query=test_query)
        print("\n" + "=" * 60)
        print(result.get("text", "No results"))
        print("=" * 60)
        for lead in result.get("leads", []):
            print(f"  {lead}")
    
    asyncio.run(_run_test())

find_leads = find_leads_v3