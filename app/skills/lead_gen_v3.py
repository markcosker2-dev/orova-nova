import os
import logging
import asyncio
import re
import json
import socket
import httpx
from datetime import datetime, timedelta
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


# ── WA L&I contractor licences as a DISCOVERY source (ADR-0014 seam 1) ───────
# SerpAPI is the only working discovery source and it is exhausted (250/250,
# 0 left). This dataset is free, needs no key, has no quota, and inverts the
# hard direction of the pipeline: instead of discovering a business and then
# hunting for its owner, the licence record gives the legally-named principal
# and a phone number up front.
#
# Live-measured 2026-07-30 against the real dataset (not the ADR's numbers):
#   75,463  ACTIVE licences
#   55,942  + specialty GENERAL|RESIDENTIAL
#   16,322  + Seattle metro + owner and phone present
#   15,069  + licence type CONSTRUCTION CONTRACTOR
#   ~4,280  + passes the ICP name filter below (28.4% of the 15,069)
# Fill on businessname / primaryprincipalname / phonenumber / address1: 100%.
#
# CORRECTION to ADR-0014, found by reading real rows: specialty 'GENERAL' does
# NOT mean "general contractor". The GENERAL bucket is full of landscapers,
# window cleaners, drywall, tile, masonry and handymen — the ADR's
# "6,249 on-ICP rows" figure counts those. Licence type and the name filter
# below are what actually isolate remodelers, and they are why this source
# emits ~4.3K rows rather than 15K.
#
# Deliberately NOT filtered on: employee count (absent from the dataset) and
# licence age / bond amount as a size proxy. ADR-0014 flags that proxy as
# unvalidated, so it stays out until there is evidence for it.
# ── Jurisdiction → licence registry (ADR-0014) ──────────────────────────────
# Jurisdiction is FIRST-CLASS DATA: adding a state is a row in this table, not
# a new branch in find_leads_v3. Each value is an async callable taking (count)
# and returning the licence-lead shape find_leads_v3's emit block consumes.
#
# Registered here == "this state has a free, keyless registry that supplies the
# decision maker directly". A state that is absent is not a bug, it is a fact
# about that state's open data (California's CSLB has no API at all), and
# find_leads_v3 says so out loud rather than quietly falling through to a
# scraper — which is exactly how "California falls through to a scraper that
# produces uncallable leads" survived undiagnosed for weeks.
LICENCE_REGISTRIES: dict = {}


def register_licence_registry(state: str, source) -> None:
    """Bind a state code to its licence-registry discovery source."""
    LICENCE_REGISTRIES[state.strip().upper()] = source


def licence_registry_for(state: str):
    """The discovery source for `state`, or None when that state has none."""
    return LICENCE_REGISTRIES.get((state or "").strip().upper())


_WA_LNI_ENV_FLAG = "WA_LNI_DISCOVERY_ENABLED"

# Seattle metro. Uppercase because the dataset stores city inconsistently
# ("AUBURN" and "Auburn" both occur), so matching is done on upper(city).
_WA_METRO_CITIES = (
    "SEATTLE", "BELLEVUE", "KIRKLAND", "REDMOND", "RENTON", "KENT", "BOTHELL",
    "ISSAQUAH", "SAMMAMISH", "MERCER ISLAND", "SHORELINE", "EDMONDS",
    "LYNNWOOD", "EVERETT", "TACOMA", "FEDERAL WAY", "AUBURN", "BURIEN",
    "WOODINVILLE", "KENMORE", "SNOHOMISH", "PUYALLUP",
)

# Two tiers, because one flat keyword list gets this wrong in both directions.
#
# STRONG: unambiguously a remodeler/builder. Accepted even alongside a trade
# word, so "ACTION ROOFING & REMODELING" and "ARK ROOFING & RENOVATIONS" are
# kept — a roofer who also remodels is in-ICP, and a flat denylist dropped them.
_ICP_STRONG_RE = re.compile(
    r"(?i)\b(remodel\w*|renovat\w*|custom\s+home\w*|home\s*build\w*|homebuild\w*|"
    r"design[\s/+-]*build|kitchen|bath\w*|builders?|fine\s+home\w*)\b")

# GENERIC: consistent with a remodeler but also with any trade. Accepted only
# when no trade word is present, so "2K CONSTRUCTION" is kept while
# "ANDY TILE CONSTRUCTION" and "AFS CONSTRUCTION + HANDYMAN" are not.
_ICP_GENERIC_RE = re.compile(
    r"(?i)\b(construction|constructs?|contracting|residential|carpentry)\b")

# Trades and services that are not the ADR-0012 ICP. Only consulted for
# GENERIC-tier names (see above).
_NON_ICP_TRADE_RE = re.compile(
    r"(?i)\b(landscap\w*|lawn|window\s+clean\w*|janitorial|maid|carpet\s+clean\w*|"
    r"pressure\s+wash\w*|power\s+wash\w*|tree\s+(service|care|removal)|"
    r"gutter\w*|pool\s+(service|clean\w*)|moving|hauling|junk|handy\w*|"
    r"cleaning|sprinkler|fence|paint\w*|drywall|tile|masonry|concrete|"
    r"flooring|roof\w*|plumb\w*|electric\w*|hvac|septic|excavat\w*|"
    r"demolition|solar|sign\w*|glass|asphalt|paving|insulation)\b")


def icp_business_name_reason(business_name: str) -> str:
    """'' if this licence holder looks like an ADR-0012 remodeler, else why not.

    Precision-biased on purpose. There are ~15K licence rows in the metro and
    Nova needs tens of calls, so a missed remodeler costs nothing while a
    landscaper in the call queue wastes a Retell dial and Mark's credibility.
    Known and accepted misses: abbreviated names ("1ST CHOICE HOME IMPRVMNT")
    and bare-word names ("SMITH & SONS LLC") carry no usable signal.
    """
    name = (business_name or "").strip()
    if not name:
        return "no business name"
    if _ICP_STRONG_RE.search(name):
        return ""
    if _ICP_GENERIC_RE.search(name):
        trade = _NON_ICP_TRADE_RE.search(name)
        if trade:
            return f"specialty trade, not a remodeler ({trade.group(0).lower()!r})"
        return ""
    return "no remodeling/building signal in the name"


# Back-compat alias: this filter was introduced for the WA L&I source. Existing
# callers and tests keep working.
wa_lni_icp_reason = icp_business_name_reason


def off_icp_trade_in_name(business_name: str) -> str:
    """Only the NEGATIVE half of the name filter: an explicit off-ICP trade word.

    `icp_business_name_reason` also REQUIRES a construction keyword, because the
    WA licence registry has no category field and the name is the only signal
    there. That requirement is wrong wherever a category IS available: plenty of
    real builders are named after their founder. Live 2026-07-31, Yelp returned
    "Neil Kelly" — a genuine Portland design-build firm, categorised by Yelp as
    General Contractors — and the keyword requirement rejected it. "Smith & Sons"
    would fail the same way.

    So sources with trustworthy categories use this narrower check: trust the
    category for FIT, and use the name only to catch a self-declared contractor
    that is really a handyman or a tiler.
    """
    name = (business_name or "").strip()
    if not name:
        return "no business name"
    hit = _NON_ICP_TRADE_RE.search(name)
    if hit:
        return f"specialty trade in name ({hit.group(0).lower()!r})"
    return ""


async def _source_wa_lni_licences(count: int, cities: tuple = _WA_METRO_CITIES) -> list:
    """Discover WA remodelers from the L&I licence registry. Free, no key, no quota.

    Emits the same lead shape as the other sources but with NO url/website —
    licence data carries neither, and resolving a domain is ADR-0014 seam 2, not
    this one. Callers must therefore not assume a URL is present.

    What each row DOES carry is what the phone lane needs: a real business name,
    the legally-named principal, and a phone at 100% fill. Retell owns all cold
    dialling, so these are immediately actionable without any enrichment.

    Kill switch: WA_LNI_DISCOVERY_ENABLED=0.
    """
    if os.getenv(_WA_LNI_ENV_FLAG, "1") != "1":
        logger.info("[WA_LNI] discovery disabled by env flag")
        return []
    # Reuse owner_finder's helpers rather than reimplementing them — it already
    # queries this dataset (PR #113) and owns the "LAST, FIRST" principal
    # parsing and the legal-suffix normalisation.
    from app.skills.owner_finder import (
        _WA_LNI_DATASET, _person_from_principal, _is_plausible_name,
    )

    city_list = ",".join(f"'{c}'" for c in cities)
    # ── Licence-age floor (2026-08-09) ──────────────────────────────────────
    # ADR-0012 qualifies on AFFORDABILITY: does ONE extra closed deal per month
    # more than cover the all-in cost? A contractor licensed last week has no
    # revenue history, no crew and no book of business, so the answer is no —
    # and business_context.json lists "No payroll (solo operator) - no urgency"
    # as an outright kill signal.
    #
    # This source used to ORDER BY licenseeffectivedate DESC on the reasoning
    # that "a recently-licensed contractor is more likely to still be building
    # a client base". That optimises for who NEEDS leads, which is the opposite
    # of who can PAY for them. Measured on the live registry 2026-08-09: the
    # three verifiable leads it had produced were all licensed 3-4 days earlier,
    # all single-principal, all carrying the $1M minimum insurance — precisely
    # the segment the playbook says to disqualify.
    #
    # Supply is not the constraint: 11,105 active GENERAL/RESIDENTIAL
    # contractors in the target cities were licensed 3+ years ago, against an
    # outreach rate of 5-10 a day.
    # A BAND, not a floor. Applying only a floor and sorting oldest-first was
    # measured against the live registry and overshot into the opposite failure:
    # it returned W G CLARK (1963, 11 principals), ABSHER (1966, $2M cover) and
    # TURNER CONSTRUCTION COMPANY (1977, $5M) — national commercial GCs with
    # marketing departments, as far outside the ICP as the day-old solos were.
    #
    # The ICP sits between: established enough to have revenue and a crew,
    # small enough that the owner still answers the phone and buys his own
    # marketing. 8,768 contractors qualify in the target cities, against an
    # outreach rate of 5-10 a day, so the band costs nothing in supply.
    _min_years = float(os.getenv("WA_LNI_MIN_LICENCE_YEARS", "3") or 3)
    _max_years = float(os.getenv("WA_LNI_MAX_LICENCE_YEARS", "25") or 25)
    _cutoff = (datetime.now() - timedelta(days=int(365.25 * _min_years))).strftime("%Y-%m-%d")
    _ceiling = (datetime.now() - timedelta(days=int(365.25 * _max_years))).strftime("%Y-%m-%d")
    where = (
        "contractorlicensestatus='ACTIVE'"
        " AND contractorlicensetypecodedesc='CONSTRUCTION CONTRACTOR'"
        " AND specialtycode1desc in('GENERAL','RESIDENTIAL')"
        f" AND upper(city) in({city_list})"
        " AND primaryprincipalname IS NOT NULL"
        " AND phonenumber IS NOT NULL"
        f" AND licenseeffectivedate < '{_cutoff}'"
        f" AND licenseeffectivedate > '{_ceiling}'"
        # Sole proprietors, stated by the registry itself. business_context.json
        # lists "No payroll (solo operator) - no urgency" as a kill signal, and
        # this is the one place it can be read for free with no extra API call.
        # It is NOT sufficient on its own — the three leads verified on
        # 2026-08-09 were all LLCs with a single principal — but it removes the
        # 9,325 self-declared individuals at zero cost.
        " AND businesstypecodedesc != 'Individual'"
    )
    # Over-fetch: only ~28% of rows survive the ICP name filter, so asking for
    # `count` rows would reliably under-deliver. 6x plus headroom, capped at the
    # Socrata page limit.
    fetch = min(max(count * 6, 200), 1000)
    leads: list = []
    seen_phones: set = set()
    try:
        client = await _get_http_client()
        resp = await client.get(_WA_LNI_DATASET, params={
            "$where": where,
            "$select": ("businessname,primaryprincipalname,phonenumber,address1,"
                        "city,state,zip,contractorlicensenumber,"
                        "licenseeffectivedate,businesstypecodedesc"),
            "$limit": str(fetch),
            # OLDEST licences first (inverted 2026-08-09). Longevity is the
            # cheapest free proxy for "has survived, has a book of business,
            # can plausibly afford the retainer" — a contractor still active
            # after a decade is a different prospect from one licensed last
            # week. Still deterministic, so repeated runs return a stable
            # slice, which was the other property the old ordering provided.
            "$order": "licenseeffectivedate ASC",
        }, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.warning(f"[WA_LNI] status {resp.status_code} — no leads this run")
            return []
        rows = resp.json() or []
    except Exception as e:
        logger.error(f"[WA_LNI] fetch failed: {e}")
        return []

    skipped_icp = 0
    for row in rows:
        if len(leads) >= count:
            break
        business = (row.get("businessname") or "").strip()
        if icp_business_name_reason(business):
            skipped_icp += 1
            continue
        phone = _normalize_phone_to_e164(row.get("phonenumber") or "")
        if not phone or phone in seen_phones:
            continue          # no dialable number, or a shared/duplicate line
        owner = _person_from_principal(row.get("primaryprincipalname") or "")
        if not owner or not _is_plausible_name(owner):
            continue          # never store a principal we can't parse cleanly
        seen_phones.add(phone)
        addr = " ".join(p for p in (
            (row.get("address1") or "").strip(),
            (row.get("city") or "").strip(),
            (row.get("state") or "WA").strip(),
            (row.get("zip") or "").strip(),
        ) if p)
        leads.append({
            "business": business,
            "owner_name": owner,
            "owner_title": "Licence Principal",
            "owner_source": "wa_lni",
            "owner_confidence": 90,
            "phone": phone,
            "phone_source": "wa_lni",
            # A state licence register is an authoritative published business
            # line, which is exactly what TCPA permits calling.
            "phone_verified": True,
            "address": addr,
            "city": (row.get("city") or "").strip(),   # see the OR source below
            "state": "WA",
            "url": "",
            "website": "",
            "email": "",
            "source": "wa_lni_licences",
            "notes": (f"WA L&I licence {row.get('contractorlicensenumber') or '?'}"
                      f" · {row.get('businesstypecodedesc') or '?'}"
                      f" · effective {(row.get('licenseeffectivedate') or '')[:10]}"),
        })

    logger.info(f"[WA_LNI] {len(leads)} in-ICP leads from {len(rows)} licence rows "
                f"({skipped_icp} failed the ICP name filter)")
    return leads


# Registered at import time — see LICENCE_REGISTRIES above. This line, not an
# `if state == "WA"` branch in find_leads_v3, is what makes WA a registry state.
register_licence_registry("WA", _source_wa_lni_licences)


# ── OREGON CCB — the second licence registry (ADR-0014 seam 3) ──────────────
# https://data.oregon.gov/resource/g77e-6bhs.json  ("CCB Active Licenses")
# Free, keyless Socrata, same class as WA L&I. Measured live 2026-08-05:
#
#   55,931 rows total · phone_number 100% fill · rmi_name 97.3% fill
#
# Field mapping vs WA (the publisher's own column descriptions, not inferred):
#   full_name    "Full, legal name of the license holder which must match the
#                 business filing at the Oregon Secretary of State"  -> business
#   rmi_name     "The name of the Responsible Managing Individual (RMI)" -> owner
#   phone_number "Work phone number of the license holder"           -> phone
#   exempt_text  "Whether this license holder is required to carry Workmans
#                 Compensation Insurance"                            -> see below
#
# THREE things this source must get right, each verified against real rows:
#
# 1. OUT-OF-STATE ROWS. The dataset is "contractors who can legally work in
#    Oregon", not "Oregon contractors". 8,090 of 55,931 (14.5%) sit in another
#    state — 4,582 in WA alone. Without `state='OR'` an Oregon hunt returns
#    Washington and Nevada businesses. Hence the explicit filter.
#
# 2. THE ENDORSEMENT IS A LICENCE CLASS, NOT A TRADE CATEGORY. It is tempting
#    to trust `license_type='RGC'` (Residential General Contractor) the way the
#    Yelp source trusts a Yelp category, and use the narrow name filter. That is
#    wrong. Measured over 1,200 real RGC rows in the Portland metro:
#
#      off_icp_trade_in_name (narrow) accepts 80.7%  <- fires on nearly
#                                                       everything = noise
#      icp_business_name_reason (strict) accepts 35.7%
#
#    The 45-point gap is real off-ICP work that RGC happily covers: SHAMBURG
#    HEATING, SEWER RENEWAL SPECIALISTS, KRAFT SCREENS & WINDOW WASHING, AQUA
#    TECH BACKFLOW, PROPERTY MANAGEMENT NORTH WEST. So OR uses the STRICT
#    filter, exactly like WA — the narrow one is only correct where a source
#    publishes a real trade category.
#
# 3. PLACEHOLDER RMI VALUES. 116 rows carry a sentinel instead of a person
#    ('RD - NO RMI RQRD', "RMI NOT RQ'D", 'NO RMI ON FILE'). These parse to
#    plausible-looking names ('Rd Rqrd', 'No Rmi') and would put a fabricated
#    person into a call script. Filtered below.
_OR_CCB_DATASET = "https://data.oregon.gov/resource/g77e-6bhs.json"
_OR_CCB_ENV_FLAG = "OR_CCB_DISCOVERY_ENABLED"

# Portland metro. `county_name` is 100% filled and spelled consistently, so OR
# needs no equivalent of WA's uppercase city list.
_OR_METRO_COUNTIES = ("Multnomah", "Washington", "Clackamas")

# Residential General Contractor. Deliberately excludes RSC (Residential
# Specialty — the trades), RLC (Limited, a volume-capped licence) and both
# Commercial levels: a commercial GC's customer is a developer or a business,
# and Meta ads cannot reach those the way they reach a homeowner.
_OR_CCB_LICENSE_TYPE = "RGC"

# A standalone "RMI" token never appears in a real person's name — verified
# across all 50,000 non-null rmi_name values, where it matched the 116 sentinel
# rows and nothing else (CARMI, TORMIS, MCDIARMID etc. are single tokens).
_OR_RMI_PLACEHOLDER_RE = re.compile(r"(?i)\bRMI\b")


async def _source_or_ccb_licences(count: int,
                                  counties: tuple = _OR_METRO_COUNTIES,
                                  require_employees: bool = True) -> list:
    """Discover Oregon remodelers from the CCB licence registry. Free, no key.

    Emits the same lead shape as the WA source — business, legally-named
    principal and a dialable phone, with NO url/website (licence data carries
    neither; domain resolution is ADR-0014 seam 2).

    `require_employees` filters to `exempt_text='Nonexempt'`, i.e. licence
    holders REQUIRED to carry workers' comp — which in Oregon means they have
    employees. ADR-0014 recorded "no employee count, so the 6-10-person ICP
    cannot be filtered directly... needs a proxy, and that proxy is
    unvalidated". This is that proxy, and unlike a guess from bond size it
    comes from the publisher's own definition of the column. It is a SIZE
    signal only — deliberately not an affordability one, per the 2026-08-05
    correction that BusinessType is a tax status and says nothing about
    revenue. Measured live in the Portland metro: 9,867 RGC rows with owner +
    phone, of which 3,943 are Nonexempt.

    Kill switch: OR_CCB_DISCOVERY_ENABLED=0.
    """
    if os.getenv(_OR_CCB_ENV_FLAG, "1") != "1":
        logger.info("[OR_CCB] discovery disabled by env flag")
        return []
    from app.skills.owner_finder import _person_from_principal, _is_plausible_name

    county_list = ",".join("'%s'" % c.replace("'", "''") for c in counties)
    where = (
        f"license_type='{_OR_CCB_LICENSE_TYPE}'"
        " AND state='OR'"                      # see note 1 — 14.5% are not
        f" AND county_name in({county_list})"
        " AND rmi_name IS NOT NULL"
        " AND phone_number IS NOT NULL"
    )
    if require_employees:
        where += " AND exempt_text='Nonexempt'"
    # Over-fetch: only ~36% survive the ICP name filter (measured, note 2), so
    # asking for `count` rows would reliably under-deliver.
    fetch = min(max(count * 6, 200), 1000)
    leads: list = []
    seen_phones: set = set()
    try:
        client = await _get_http_client()
        resp = await client.get(_OR_CCB_DATASET, params={
            "$where": where,
            "$select": ("full_name,rmi_name,phone_number,address,city,state,"
                        "zip_code,county_name,license_number,orig_regis_date,"
                        "endorsement_text,exempt_text"),
            "$limit": str(fetch),
            # Newest licences first — same rationale as WA: a recently-licensed
            # contractor is likelier to still be building a client base, and it
            # makes repeated runs return a stable, non-arbitrary slice.
            "$order": "orig_regis_date DESC",
        }, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            logger.warning(f"[OR_CCB] status {resp.status_code} — no leads this run")
            return []
        rows = resp.json() or []
    except Exception as e:
        logger.error(f"[OR_CCB] fetch failed: {e}")
        return []

    skipped_icp = 0
    skipped_placeholder = 0
    for row in rows:
        if len(leads) >= count:
            break
        business = (row.get("full_name") or "").strip()
        if icp_business_name_reason(business):
            skipped_icp += 1
            continue
        raw_rmi = (row.get("rmi_name") or "").strip()
        if _OR_RMI_PLACEHOLDER_RE.search(raw_rmi):
            skipped_placeholder += 1
            continue          # 'RD - NO RMI RQRD' is not a person — see note 3
        phone = _normalize_phone_to_e164(row.get("phone_number") or "")
        if not phone or phone in seen_phones:
            continue          # no dialable number, or a shared/duplicate line
        owner = _person_from_principal(raw_rmi)
        if not owner or not _is_plausible_name(owner):
            continue          # never store a principal we can't parse cleanly
        seen_phones.add(phone)
        addr = " ".join(p for p in (
            (row.get("address") or "").strip(),
            (row.get("city") or "").strip(),
            (row.get("state") or "OR").strip(),
            (row.get("zip_code") or "").strip(),
        ) if p)
        leads.append({
            "business": business,
            "owner_name": owner,
            # The RMI is the licence's legally responsible individual — the
            # decision maker, and the OR analogue of WA's licence principal.
            "owner_title": "Responsible Managing Individual",
            "owner_source": "or_ccb",
            "owner_confidence": 90,
            "phone": phone,
            "phone_source": "or_ccb",
            # A state licence register is an authoritative published business
            # line, which is exactly what TCPA permits calling.
            "phone_verified": True,
            "address": addr,
            # City kept as its own field, not only inside the joined address:
            # ADR-0014 seam 2 needs it to confirm a candidate website really
            # belongs to THIS business, and re-deriving it by slicing `address`
            # produced the token "CITY" from "OREGON CITY" during the
            # 2026-08-05 probe — which then matched a Pennsylvania homepage.
            "city": (row.get("city") or "").strip(),
            "state": "OR",
            "url": "",
            "website": "",
            "email": "",
            "source": "or_ccb_licences",
            "notes": (f"OR CCB licence {row.get('license_number') or '?'}"
                      f" · {row.get('endorsement_text') or '?'}"
                      f" · {row.get('exempt_text') or '?'}"
                      f" · {row.get('county_name') or '?'} County"
                      f" · registered {(row.get('orig_regis_date') or '')[:10]}"),
        })

    logger.info(f"[OR_CCB] {len(leads)} in-ICP leads from {len(rows)} licence rows "
                f"({skipped_icp} failed the ICP name filter, "
                f"{skipped_placeholder} had a placeholder RMI)")
    return leads


register_licence_registry("OR", _source_or_ccb_licences)


# ── Yelp Fusion as a WEST-COAST discovery source (2026-07-31) ───────────────
# ADR-0014 listed Yelp as a dead end ("free tier ambiguous, needs approval").
# That was wrong, and the consequence was worse than the error: the ADR then
# sequenced discovery by WHICH STATE HAS A FREE REGISTRY API — WA first, CA
# last — which put the #1 ICP geography (ADR-0012: California) at the back of
# the queue for a purely technical reason. Tooling drove targeting.
#
# Yelp works identically in every metro. Measured live 2026-07-31:
#   Los Angeles 20,000 · Portland 3,600 · Seattle 3,300 · San Diego 2,400
#
# What Yelp gives that the licence registries do NOT:
#   · `review_count` + `rating` — a real business-SIZE proxy. ADR-0014 flagged
#     "no employee count, so the 6-10-person ICP cannot be filtered; the
#     datasets are full of one-person handymen" and said any proxy was
#     unvalidated. Review count is better than bond size or licence age, and free.
#   · explicit CATEGORY labels, so a landscaper is excluded by data rather than
#     by guessing from its name.
#
# What Yelp does NOT give: owner name, website, or email. The owner name is
# resolved below via owner_finder._registry_lookup (WA/OR live today; CA needs
# CALICO or seam-2 scraping). Email stays unsolved and is NEVER guessed.
_YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
_YELP_PAGE_SIZE = 50            # Fusion hard maximum per request
_YELP_MAX_OFFSET = 240          # Fusion rejects offset+limit > 1000; stay well under

# ICP thresholds (ADR-0012). Deliberately moderate — these gate business SIZE
# and delivery quality, not fit; the category and name filters handle fit.
_YELP_MIN_REVIEWS = 15   # sustained volume => a crew on payroll, not a side job
_YELP_MIN_RATING = 4.0   # below this he has a delivery problem, and ads amplify it

# Yelp category ALIASES that are not the ADR-0012 ICP. Checked against every
# category on the listing, because Yelp returns them unordered and a business
# tagged both "contractors" and "handyman" is a handyman.
_YELP_OFF_ICP_CATEGORIES = frozenset({
    "handyman", "landscaping", "landscapearchitects", "gardeners", "lawnservices",
    "tiling", "flooring", "carpetinstallation", "countertopinstall", "drywall",
    "roofing", "gutterservices", "siding", "vinylsiding", "painters",
    "masonry", "concrete", "fencesgates", "decksrailing", "excavationservices",
    "plumbing", "electricians", "hvac", "windowsinstallation", "glassandmirrors",
    "solarinstallation", "movers", "junkremovalandhauling", "homecleaning",
    "officecleaning", "pressurewashers", "windowwashing", "treeservices",
    "poolservices", "damagerestoration", "environmentalabatement", "septicservices",
    "garagedoorservices", "locksmiths", "pestcontrol", "chimneysweeps",
})
# At least one of these must be present — otherwise it is not a builder at all.
_YELP_IN_ICP_CATEGORIES = frozenset({
    "contractors", "generalcontractors", "homedevelopers", "buildingsupplies",
    "kitchenandbath", "interiordesign", "architects",
})


async def _source_yelp_businesses(query: str, count: int, location: str,
                                  resolve_owner: bool = True) -> list:
    """Discover ICP-fit remodelers/builders from Yelp Fusion for ONE metro.

    Emits the existing lead shape with a real business name, an E.164 phone and
    a full address — but NO website and NO email (Yelp supplies neither, and an
    email is never guessed). The owner name is resolved from the state licence
    registry when `resolve_owner` is set and the state is WA/CA/OR; without a
    name a lead cannot clear `outreach_ready` on any channel, so this step is
    what makes a Yelp row actually contactable rather than merely discovered.

    Requires YELP_API_KEY (Yelp Fusion, free developer tier). Composio's Yelp
    connector is NOT a substitute — that credential lives in the operator's MCP
    session, not in Nova's runtime on Render.

    Kill switch: YELP_DISCOVERY_ENABLED=0.
    """
    api_key = os.getenv("YELP_API_KEY")
    if not api_key:
        logger.info("[YELP] YELP_API_KEY not set — Yelp discovery skipped.")
        return []
    if os.getenv("YELP_DISCOVERY_ENABLED", "1") != "1":
        logger.info("[YELP] discovery disabled by env flag")
        return []
    if count <= 0 or not (location or "").strip():
        return []

    leads: list = []
    seen_phones: set = set()
    skipped = {"category": 0, "name": 0, "rating": 0, "reviews": 0, "phone": 0}
    offset = 0
    try:
        client = await _get_http_client()
        while len(leads) < count and offset <= _YELP_MAX_OFFSET:
            resp = await client.get(
                _YELP_SEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}",
                         "Accept": "application/json"},
                params={"term": query or "general contractor remodeling",
                        "location": location,
                        "limit": _YELP_PAGE_SIZE,
                        "offset": offset,
                        "sort_by": "review_count"},
            )
            if resp.status_code == 429:
                logger.warning("[YELP] rate limited (429) — stopping this run.")
                break
            if resp.status_code != 200:
                logger.warning(f"[YELP] status {resp.status_code} for {location!r} "
                               f"— stopping (no leads from this source).")
                break
            businesses = (resp.json() or {}).get("businesses") or []
            if not businesses:
                break

            for b in businesses:
                if len(leads) >= count:
                    break
                lead = _yelp_row_to_lead(b, skipped, seen_phones)
                if lead:
                    leads.append(lead)

            if len(businesses) < _YELP_PAGE_SIZE:
                break       # last page — further requests would be wasted
            offset += _YELP_PAGE_SIZE
    except Exception as e:
        logger.error(f"[YELP] search failed for {location!r}: {e}")
        return leads        # keep whatever was already parsed; never raise

    if resolve_owner and leads:
        await _yelp_resolve_owners(leads)

    logger.info(f"[YELP] {len(leads)} in-ICP leads for {location!r} "
                f"(skipped — category {skipped['category']}, name {skipped['name']}, "
                f"rating {skipped['rating']}, reviews {skipped['reviews']}, "
                f"phone {skipped['phone']})")
    return leads


def _yelp_row_to_lead(b: dict, skipped: dict, seen_phones: set):
    """One Yelp business -> a lead dict, or None if it fails an ICP gate.

    Order matters only for the skip counters, which exist so a run that returns
    nothing can be diagnosed from the log rather than guessed at.
    """
    if not isinstance(b, dict) or b.get("is_closed"):
        return None
    business = (b.get("name") or "").strip()
    if not business:
        return None

    aliases = {(c or {}).get("alias", "") for c in (b.get("categories") or [])
               if isinstance(c, dict)}
    if aliases & _YELP_OFF_ICP_CATEGORIES:
        skipped["category"] += 1
        return None
    if not (aliases & _YELP_IN_ICP_CATEGORIES):
        skipped["category"] += 1
        return None
    # Name check as a second opinion — Yelp's categories are self-declared, so
    # "Bob's Handyman LLC" can still be listed purely as a general contractor.
    # NARROW check only: the category already established fit, so requiring a
    # construction keyword here would reject real builders named after their
    # founder (live: "Neil Kelly", a Portland design-build firm).
    if off_icp_trade_in_name(business):
        skipped["name"] += 1
        return None

    try:
        rating = float(b.get("rating") or 0)
        reviews = int(b.get("review_count") or 0)
    except (TypeError, ValueError):
        rating, reviews = 0.0, 0
    if rating < _YELP_MIN_RATING:
        skipped["rating"] += 1
        return None
    if reviews < _YELP_MIN_REVIEWS:
        skipped["reviews"] += 1
        return None

    phone = _normalize_phone_to_e164(b.get("phone") or b.get("display_phone") or "")
    if not phone or phone in seen_phones:
        skipped["phone"] += 1
        return None      # unreachable, or a shared/duplicate line
    seen_phones.add(phone)

    loc = b.get("location") or {}
    state = (loc.get("state") or "").strip().upper()
    address = " ".join(p for p in (
        (loc.get("address1") or "").strip(), (loc.get("city") or "").strip(),
        state, (loc.get("zip_code") or "").strip()) if p)

    return {
        "business": business,
        "owner_name": "",          # Yelp has none; resolved from the registry below
        "phone": phone,
        "phone_source": "yelp",
        "phone_verified": True,    # a claimed listing's published business line
        "address": address,
        "state": state if state in _US_STATE_CODES else "",
        "url": "", "website": "", "email": "",
        "source": "yelp",
        "notes": (f"Yelp {rating}★ · {reviews} reviews · "
                  f"{', '.join(sorted(aliases)) or 'uncategorised'}"),
    }


async def _yelp_resolve_owners(leads: list) -> None:
    """Fill owner_name from the state licence registry, in place.

    Yelp gives no decision-maker, and `outreach_ready` requires a name on EVERY
    channel — so without this a Yelp lead is discovered but not contactable.
    WA and OR resolve today; CA needs CALICO (pending) or seam-2 scraping.

    Failures are per-lead and non-fatal: a lead with no owner is still stored,
    it simply is not outreach-ready yet. A wrong name would be far worse than a
    missing one (ADR-0008), which is why the registry lookups match strictly.
    """
    from app.core.hardening import concurrency_limit
    sem = asyncio.Semaphore(concurrency_limit("lead_enrich"))

    async def _one(lead):
        state = lead.get("state") or ""
        if not state:
            return
        async with sem:
            try:
                from app.skills.owner_finder import _registry_lookup
                hit = await _registry_lookup(lead.get("business", ""), state)
            except Exception as e:
                logger.debug(f"[YELP] owner lookup failed for "
                             f"{lead.get('business','?')}: {e}")
                return
        if hit and hit.get("owner"):
            lead["owner_name"] = hit["owner"]
            lead["owner_title"] = hit.get("title") or "Licence Principal"
            lead["owner_source"] = hit.get("source") or "registry"
            lead["owner_confidence"] = int(float(hit.get("confidence") or 0) * 100)

    await asyncio.gather(*(_one(l) for l in leads), return_exceptions=True)
    resolved = sum(1 for l in leads if l.get("owner_name"))
    logger.info(f"[YELP] owner resolved for {resolved}/{len(leads)} leads")


# Yelp needs a "City, ST" string, but the hunt query is free text
# ("luxury home remodeling california"). Metro names are checked first because
# they are more specific; a bare state falls back to its largest ICP metro.
_YELP_METROS = {
    "los angeles": "Los Angeles, CA", "san diego": "San Diego, CA",
    "san francisco": "San Francisco, CA", "orange county": "Irvine, CA",
    "sacramento": "Sacramento, CA", "san jose": "San Jose, CA",
    "seattle": "Seattle, WA", "bellevue": "Bellevue, WA",
    "tacoma": "Tacoma, WA", "portland": "Portland, OR", "eugene": "Eugene, OR",
}
# ADR-0012 ranks California first, so a bare "california" goes to LA — the
# largest ICP metro on the coast (20,000 contractors vs Seattle's 3,300).
_YELP_STATE_DEFAULT_METRO = {
    "california": "Los Angeles, CA", "washington": "Seattle, WA",
    "oregon": "Portland, OR",
}


def _infer_yelp_location(query: str) -> str:
    """'City, ST' for Yelp, or '' when the query names no West Coast geography.

    Returning '' is meaningful: Yelp requires a location, so a query we cannot
    place must skip the source rather than guess a metro and quietly discover
    leads in the wrong state.
    """
    q = (query or "").lower()
    for metro, formatted in _YELP_METROS.items():
        if metro in q:
            return formatted
    for state, formatted in _YELP_STATE_DEFAULT_METRO.items():
        if state in q:
            return formatted
    return ""


# West Coast ICP state names as they appear in the free-text hunt query
# (e.g. "exotic car dealer california").
#
# ⚠️ This is a LAST-RESORT fallback, not the jurisdiction source. Callers should
# pass `state=` to find_leads_v3 explicitly. Deciding which legal registry to
# query by substring-matching a *search string* is wrong in three ways, all of
# them observed in production:
#   1. It only knows three words, so every other state silently resolves to "".
#   2. A niche that happens to omit the geography ("custom home builder") gets
#      no jurisdiction at all, even when the hunt lane knew it perfectly well.
#   3. A false positive is possible in principle ("California Closets" is a
#      national franchise, not a Californian one).
# The failure is silent and expensive: state="" skips every licence registry
# and drops through to the legacy scrapers, which the code below documents as
# producing leads that can never be called.
_QUERY_STATE_HINTS = {"california": "CA", "washington": "WA", "oregon": "OR"}


def _infer_state_from_query(query: str) -> str:
    """Best-effort jurisdiction from a free-text query. Prefer an explicit state."""
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


async def _resolve_licence_websites(leads: list) -> None:
    """Fill in `website`/`url` for licence leads, in place. Never raises.

    Measured 10% success over real OR CCB leads — most small contractors have
    no site, and acceptance requires the licence phone printed on the page
    (website_resolver). A miss leaves the lead exactly as it was: still
    callable, just not yet enrichable.
    """
    if not leads:
        return
    try:
        from app.skills.website_resolver import resolve_website
    except Exception as e:                       # pragma: no cover - import guard
        logger.debug(f"[V3] website resolver unavailable: {e}")
        return

    from app.core.hardening import concurrency_limit
    semaphore = asyncio.Semaphore(concurrency_limit("lead_enrich"))

    async def _one(lead):
        async with semaphore:
            try:
                hit = await resolve_website(
                    lead.get("business", ""), phone=lead.get("phone", ""),
                    city=lead.get("city", ""), state=lead.get("state", ""))
            except Exception as e:
                logger.debug(f"[V3] website resolution failed for "
                             f"{lead.get('business')!r}: {e}")
                return
            if hit.get("website"):
                lead["website"] = hit["website"]
                # `url` is what enrich_lead_lite gates on, so it must be set
                # too — setting only `website` leaves the lead unenrichable.
                lead["url"] = hit["website"]
                lead["website_source"] = hit.get("source", "")
                lead["website_confidence"] = hit.get("confidence", 0.0)

    await asyncio.gather(*[_one(l) for l in leads], return_exceptions=True)
    found = sum(1 for l in leads if l.get("website"))
    logger.info(f"[V3] website resolution: {found}/{len(leads)} licence leads "
                f"now have a verified domain")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

async def find_leads_v3(count: int = 5, query: str = "business leads",
                        state: str = "") -> dict:
    """
    Main entry point with 4-strategy enrichment chain.
    Returns clean output: owner_name, email, phone only.

    `state` is the JURISDICTION — a two-letter code deciding which licence
    registry runs. Pass it explicitly; it is a property of the hunt, not of the
    words in `query`. When omitted it falls back to substring-matching the
    query, which is what this parameter exists to stop being the only option
    (see _infer_state_from_query for why that is a bad source of truth).
    """
    count = int(count)
    query = (query or "business leads").strip()
    explicit_state = (state or "").strip().upper()
    if explicit_state:
        state = explicit_state
        state_source = "explicit"
    else:
        state = _infer_state_from_query(query)
        state_source = "inferred-from-query" if state else "unknown"
    logger.info(f"[LEAD GEN V3] Searching for {count} leads: '{query}' "
                f"(state={state or '—'} via {state_source})")
    
    all_leads = []
    # Licence-registry leads travel a separate path: they carry owner + phone
    # from a legal record but NO url, so they can neither be deduped by domain
    # nor enriched by _scrape_website. Kept apart rather than special-cased
    # inside the web flow.
    licence_leads = []

    # PRIMARY: this jurisdiction's licence registry (ADR-0014). Free, no key, no
    # quota, and it supplies the decision maker directly — which is why the ADR
    # demotes search to enrichment. Runs first so a spent SerpAPI quota (the
    # current state: 250/250) no longer means zero discovery.
    #
    # Which registry runs is now a table lookup on the jurisdiction, so adding a
    # state is data (register_licence_registry) rather than another branch here.
    registry_source = licence_registry_for(state)
    if registry_source is not None:
        try:
            licence_leads = await registry_source(count)
        except Exception as e:
            logger.warning(f"[V3] {state} licence registry discovery failed: {e}")
    elif state:
        # Say it out loud. This is the California case: the #1 ICP geography has
        # no free registry API, so the hunt drops to search + scrapers and the
        # leads may not be callable. Previously silent, which is how "California
        # falls through to a scraper" survived undiagnosed.
        logger.info(f"[V3] no licence registry for state={state} — "
                    f"falling back to search discovery "
                    f"(registered: {sorted(LICENCE_REGISTRIES) or 'none'})")
    else:
        logger.warning(f"[V3] NO JURISDICTION resolved for query {query!r} — "
                       f"every licence registry is skipped and discovery falls to "
                       f"search. Pass state= explicitly to fix this.")

    # YELP — the whole West Coast, not just WA. ADR-0014 sequenced discovery by
    # which state had a free registry API, which put California (the #1 ICP
    # geography) last for a purely technical reason. Yelp works in every metro,
    # adds review_count/rating as a business-SIZE proxy the registries lack, and
    # resolves the owner name from the state registry on the way out.
    # Env-gated on YELP_API_KEY, so it no-ops cleanly until a key is set.
    if len(licence_leads) < count:
        yelp_location = _infer_yelp_location(query)
        if yelp_location:
            try:
                licence_leads.extend(await _source_yelp_businesses(
                    query, count - len(licence_leads), yelp_location))
            except Exception as e:
                logger.warning(f"[V3] Yelp discovery failed: {e}")

    # SerpAPI Google Maps — reliable, structured, but quota-bound. Skipped when
    # the licence source already filled the request.
    if len(licence_leads) < count:
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
    # The legacy sources are strictly worse than a licence lead (URL only: no
    # name, no phone, no address), so they stay silent whenever the registry
    # produced anything at all.
    if not all_leads and not licence_leads:
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
    
    # ADR-0014 seam 2: resolve a website for the licence leads about to be
    # emitted. Registry rows carry no domain, and enrich_lead_lite returns
    # immediately on a lead with no url (light_enrich.py) — so without this
    # step a registry lead can never reach ad-signal detection (the ADR-0012
    # "already paying for leads" qualifier), email discovery, or a social
    # handle. Only the leads actually being kept are resolved, so the cost is
    # bounded by `count`, not by the size of the fetched registry page.
    await _resolve_licence_websites(licence_leads[:count])

    # Licence leads need no enrichment — owner and phone already come from a
    # legal record — so they are emitted directly and take precedence. A lead
    # Retell can dial today beats a URL-only row that may never be callable.
    licence_out = []
    for lead in licence_leads[:count]:
        licence_out.append({
            "business": lead.get("business", ""),
            "owner_name": lead.get("owner_name", ""),
            "owner_title": lead.get("owner_title", ""),
            "email": "",            # licence data carries none; never guessed
            "phone": lead.get("phone", ""),
            # Filled by _resolve_licence_websites above when — and only when —
            # the licence phone was found printed on the candidate page.
            # Empty is the common, correct outcome (~90%): most small
            # contractors have no site, and a guess would be fabricated data.
            "website": lead.get("website", ""),
            "url": lead.get("url", ""),
            "score": 0,             # recomputed server-side by the storage gate
            "status": "New",
            # Provenance comes from the emitting registry, never a hardcoded
            # default — a WA-shaped fallback here would mislabel every OR/CA
            # lead's source and state the moment a second registry registered.
            "owner_source": lead.get("owner_source", ""),
            "owner_confidence": lead.get("owner_confidence", 0),
            "email_source": "",
            "email_status": "",
            "phone_source": lead.get("phone_source", ""),
            "phone_verified": bool(lead.get("phone_verified", False)),
            "ad_signals": "",       # needs a domain, so it cannot run yet
            "state": lead.get("state", "") or state,
            "notes": lead.get("notes", ""),
        })

    # Take top N, minus the slots the licence leads already filled
    final = enriched_leads[:max(0, count - len(licence_out))]

    # Build clean output — include ALL fields for sheets pipeline
    clean_output = list(licence_out)
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
            "owner_confidence": lead.get("owner_confidence", 0),
            "notes": lead.get("notes", ""),
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