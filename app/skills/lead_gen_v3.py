import os
import logging
import asyncio
import re
import json
import httpx
from urllib.parse import quote
from typing import Optional
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

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
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    else:
        return f"+{digits}"


# Regex patterns
PHONE_RE = re.compile(r'\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}')
EMAIL_RE = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)
OWNER_PATTERNS = [
    re.compile(r'(?:owner|ceo|president|founder|director)\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', re.IGNORECASE),
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),?\s+(?:owner|ceo|president|founder|director)', re.IGNORECASE),
    re.compile(r'(?:founded by|started by|owned by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', re.IGNORECASE),
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*-\s*(?:owner|ceo|president)', re.IGNORECASE),
    re.compile(r'meet\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', re.IGNORECASE),
]

ABOUT_PAGES = ["/about", "/team", "/contact", "/about-us", "/our-team", "/our-story"]
CONTACT_PAGES = ["/contact", "/contact-us", "/contactus", "/connect"]


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

async def _scrape_website(url: str) -> dict:
    """Scrape website for owner name, email, and phone."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not url:
        return result
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        base_url = url.rstrip("/")
        host = httpx.URL(url).host or ""
        
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12.0) as client:
            pages_to_check = [base_url]
            for path in CONTACT_PAGES + ABOUT_PAGES:
                pages_to_check.append(f"https://{host}{path}")
            
            for page_url in pages_to_check[:4]:
                try:
                    resp = await client.get(page_url, timeout=8.0)
                    if resp.status_code != 200:
                        continue
                    
                    text = resp.text
                    
                    # Extract phone
                    if not result["phone"]:
                        phone_match = PHONE_RE.search(text)
                        if phone_match:
                            result["phone"] = _normalize_phone_to_e164(phone_match.group(0))
                    
                    # Extract emails
                    if not result["email"]:
                        emails = EMAIL_RE.findall(text)
                        noise_domains = ["example.com", "domain.com", "test.com", "wix.com", "squarespace.com"]
                        for email in emails:
                            domain = email.split("@")[-1].lower()
                            if domain not in noise_domains:
                                result["email"] = email
                                break
                    
                    # Extract owner name
                    if not result["owner_name"]:
                        clean = re.sub(r'<[^>]+>', ' ', text)
                        clean = re.sub(r'\s+', ' ', clean)
                        for pattern in OWNER_PATTERNS:
                            match = pattern.search(clean)
                            if match:
                                name = match.group(1).strip()
                                if _is_plausible_name(name):
                                    result["owner_name"] = name
                                    break
                    
                    if result["owner_name"] and result["email"] and result["phone"]:
                        break
                        
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[SCRAPE] Error for {url}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# STRATEGY 2: WHOIS Enrichment
# ═══════════════════════════════════════════════════════════════════════════════

async def _whois_lookup(domain: str) -> dict:
    """Perform WHOIS lookup to get registrant info."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not domain:
        return result
    
    try:
        whois_api = f"https://whois.domain.tools/{domain}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; KiloBot/1.0)",
            "Accept": "application/json"
        }
        
        async with httpx.AsyncClient(headers=headers, timeout=8.0) as client:
            try:
                resp = await client.get(whois_api)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    if data.get("registrant"):
                        result["owner_name"] = data["registrant"]
                    elif data.get("registrant_name"):
                        result["owner_name"] = data["registrant_name"]
                    
                    if data.get("registrant_email"):
                        result["email"] = data["registrant_email"]
                    
                    if data.get("registrant_phone"):
                        result["phone"] = data["registrant_phone"]
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[WHOIS] Error for {domain}: {e}")
    
    # Fallback: try alternate WHOIS service
    if not result["owner_name"]:
        try:
            alt_url = f"https://api.whois.vu/?q={domain}"
            async with httpx.AsyncClient(timeout=5.0) as client:
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
}

async def _state_registry_lookup(business_name: str, state: str = "") -> dict:
    """Look up business in state registry for owner info."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not business_name:
        return result
    
    # Extract state from business name if not provided
    if not state:
        state_match = re.search(r'\b(CA|TX|FL|NY|WA|CO|AZ|GA|NC|IL)\b', business_name.upper())
        state = state_match.group(1) if state_match else ""
    
    if state not in STATE_REGISTRY_URLS:
        return result
    
    try:
        registry_url = STATE_REGISTRY_URLS[state]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; KiloBot/1.0)",
        }
        
        params = {"q": business_name}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
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
    """Use DuckDuckGo to verify owner name via site search."""
    result = {"owner_name": "", "email": "", "phone": ""}
    
    if not domain:
        return result
    
    try:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    f'site:{domain} "Owner" OR "CEO" OR "Founder"',
                    max_results=5,
                    safesearch="strict"
                ))
        
        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        
        for res in results:
            combined = (res.get("title", "") + " " + res.get("body", "")).lower()
            if domain in combined and domain not in ["linkedin.com", "facebook.com"]:
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
    except Exception as e:
        logger.debug(f"[DDG-VERIFY] Error for {domain}: {e}")
    
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT CHAIN - Combines all 4 strategies with prioritization
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_PRIORITY = [
    "info@", "contact@", "hello@", "sales@", "support@",
    "admin@", "office@", "manager@", "owner@"
]

def _prioritize_email(emails: list) -> str:
    """Prioritize emails by role importance."""
    if not emails:
        return ""
    if len(emails) == 1:
        return emails[0]
    
    # Sort by priority
    def email_score(email):
        for i, prefix in enumerate(EMAIL_PRIORITY):
            if email.lower().startswith(prefix):
                return i
        return len(EMAIL_PRIORITY)
    
    sorted_emails = sorted(emails, key=email_score)
    return sorted_emails[0]


async def enrich_lead_4step(url: str, business_name: str = "") -> dict:
    """
    Run 4-strategy enrichment chain and merge results.
    Returns clean output with owner_name, email, phone only.
    """
    domain = extract_domain(url) if url else ""
    results = []
    
    # Run all strategies concurrently
    tasks = [
        _scrape_website(url),
        _whois_lookup(domain),
        _state_registry_lookup(business_name),
        _ddg_owner_verification(url, domain)
    ]
    
    strategy_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, res in enumerate(strategy_results):
        if isinstance(res, dict):
            results.append(res)
    
    # Merge results with priority
    final = {"owner_name": "", "email": "", "phone": ""}
    
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
    
    return final


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
        
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(search_url)
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
            result = await enrich_lead_4step(lead.get("url", ""), lead.get("business", ""))
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
    
    # Build clean output
    clean_output = []
    for lead in final:
        clean_output.append({
            "owner_name": lead.get("owner_name", ""),
            "email": lead.get("email", ""),
            "phone": lead.get("phone", ""),
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