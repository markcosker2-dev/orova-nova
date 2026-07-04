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
    if not text or len(text) < 4 or len(text) > 50:
        return False
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Za-z\'\-]+$", p) for p in parts):
        return False
    if not parts[0][0].isupper():
        return False
    if text in FALSE_POSITIVE_NAMES:
        return False
    return True

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
    result = {"owner_name": "", "email": "", "phone": ""}
    
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

                # Extract ALL phones using enhanced extraction (tel: links, data attrs, extended regex)
                phones = _extract_phones_from_html(text)
                for p in phones:
                    if p not in all_phones:
                        all_phones.append(p)

                # Extract ALL emails (not just first)
                emails = EMAIL_RE.findall(text)
                noise_domains = ["example.com", "domain.com", "test.com", "wix.com", "squarespace.com",
                                 "sentry.io", "webpack", "wixpress.com", "yourdomain.com"]
                for e in emails:
                    domain_part = e.split("@")[-1].lower()
                    if domain_part not in noise_domains and e.lower() not in all_emails:
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
            if not result["email"] and ai_data.get("email"):
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
                                result["owner_name"] = str(field[3]).strip()
                            elif len(field) >= 4 and field[0] == "email":
                                result["email"] = str(field[3]).strip()
                            elif len(field) >= 4 and field[0] == "tel":
                                result["phone"] = str(field[3]).strip()
                
                # Also check administrative/technical contacts
                if "administrative" in roles and not result["owner_name"]:
                    if len(vcard) >= 2 and isinstance(vcard[1], list):
                        for field in vcard[1]:
                            if len(field) >= 4 and field[0] == "fn":
                                result["owner_name"] = str(field[3]).strip()
            
            # Fallback: check top-level name/handle fields
            if not result["owner_name"]:
                ldh_name = data.get("ldhName", "")
                # Some registries put org name in events or notices
                for notice in data.get("notices", []):
                    desc = " ".join(notice.get("description", []))
                    if desc and len(desc) < 200 and not result["owner_name"]:
                        # Only use short descriptions that look like names/orgs
                        if any(c.isupper() for c in desc[:10]):
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
                if data.get("registrant"):
                    result["owner_name"] = data["registrant"]
                if data.get("email"):
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
                email_match = EMAIL_RE.search(text)
                if email_match:
                    result["email"] = email_match.group(0)
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
        noise = {"bbb.org", "example.com", "domain.com"}
        for e in emails:
            domain_part = e.split("@")[-1].lower()
            if domain_part not in noise:
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
                noise = {"example.com", "domain.com", "test.com"}
                for e in emails:
                    domain_part = e.split("@")[-1].lower()
                    if domain_part not in noise:
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

def _prioritize_email(emails: list) -> str:
    """Pick the best email: personal address first, then the most useful generic
    inbox. Junk (noreply etc.) is dropped entirely."""
    cleaned = [e for e in emails if e and e.split("@", 1)[0].lower() not in _JUNK_LOCALPARTS]
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
    try:
        from app.skills.owner_finder import resolve_owner
        hit = await resolve_owner(business_name, state=state, domain=domain, score=score)
        if hit.get("owner"):
            registry_owner = hit["owner"]
            registry_title = hit.get("title", "")
    except Exception as e:
        logger.debug(f"[ENRICH] owner_finder registry lookup failed for {business_name}: {e}")

    results = []

    # Run all strategies concurrently
    tasks = [
        _scrape_website(url),
        _whois_lookup(domain),
        _state_registry_lookup(business_name),
        _ddg_owner_verification(url, domain),
        _bbb_lookup(business_name, domain),
        _google_business_lookup(business_name, domain),
    ]

    strategy_results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, res in enumerate(strategy_results):
        if isinstance(res, dict):
            results.append(res)

    # Merge results with priority
    final = {"owner_name": registry_owner, "owner_title": registry_title, "email": "", "phone": ""}

    # Priority 1: Website scraping (most reliable for contact info)
    for res in results:
        if res.get("email") and not final["email"]:
            final["email"] = res["email"]
        if res.get("phone") and not final["phone"]:
            final["phone"] = res["phone"]
        if res.get("owner_name") and not final["owner_name"]:
            final["owner_name"] = res["owner_name"]

    # Priority 2: WHOIS (good for owner name)
    for res in results:
        if res.get("owner_name") and not final["owner_name"]:
            final["owner_name"] = res["owner_name"]

    # Priority 3: State registry
    for res in results:
        if res.get("owner_name") and not final["owner_name"]:
            final["owner_name"] = res["owner_name"]
        if res.get("email") and not final["email"]:
            final["email"] = res["email"]

    # Priority 4: DDG verification
    for res in results:
        if res.get("owner_name") and not final["owner_name"]:
            final["owner_name"] = res["owner_name"]

    # Validate final phone
    final["phone"] = _normalize_phone_to_e164(final["phone"])

    # Fallback: Email guess if we have owner name + domain but no email
    if not final["email"] and final["owner_name"] and domain:
        final["email"] = _guess_email(final["owner_name"], domain)

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
    
    # Get leads from sources
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
    semaphore = asyncio.Semaphore(5)
    
    async def _enrich(lead):
        async with semaphore:
            result = await enrich_lead_4step(lead.get("url", ""), lead.get("business", ""), state=state)
            result["business"] = lead.get("business", "") or extract_domain(lead.get("url", "")) or "Unknown"
            result["phone"] = lead.get("phone", "") or result.get("phone", "")
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