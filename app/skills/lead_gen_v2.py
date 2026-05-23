import os
import logging
import asyncio
import re
import json
import httpx
from typing import Optional
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD GEN V2 — Improved Lead Generation Skill
# ═══════════════════════════════════════════════════════════════════════════════
# Sources: Google Maps (HTTPX + regex), DuckDuckGo, Yelp slug parsing
# Enrichment: owner name + email extraction from business websites
# Drop-in replacement for lead_finder.find_leads()

BANNED_DOMAINS = [
    "wikipedia.org", "reddit.com", "youtube.com", "pinterest.com",
    "quora.com", "medium.com", "twitter.com", "tiktok.com",
    "dictionary.com", "merriam-webster.com", "thefreedictionary.com",
    "britannica.com", "facebook.com", "instagram.com", "yelp.com/search",
    "pornhub.com", "xvideos.com", "xnxx.com",
    "baidu.com", "iciba.com", "dict.cn", "youdao.com", "zdic.net",
    "wordreference.com", "thesaurus.com", "glosbe.com", "linguee.com",
    "tripadvisor.com", "zillow.com", "realtor.com",
]

JUNK_KEYWORDS = [
    r"\bdefinition\b", r"\bmeaning\b", r"\bsynonyms\b", r"\bwiki\b",
    r"\bporn\b", r"\bsex\b", r"\badult\b", r"\bxxx\b", r"\bnaked\b",
    r"\bescort\b", r"\bdictionary\b", r"\blist of\b", r"\btypes of\b",
]

JUNK_COMPILED = [re.compile(p, re.IGNORECASE) for p in JUNK_KEYWORDS]

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
    re.compile(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+is\s+(?:the|our)\s+(?:owner|ceo|president|founder)', re.IGNORECASE),
]
ABOUT_PAGES = ["/about", "/team", "/contact", "/about-us", "/about-us/", "/our-team", "/our-story"]
SUPPORTED_TLDS = re.compile(r'\.(com|net|org|biz|co|info|us|io|ly|me|ai)$')


def _normalize_url(url: str) -> str:
    """Normalize a URL — strip tracking params, lowercase host."""
    try:
        from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        query = parse_qs(parsed.query)
        query.pop("utm_source", None)
        query.pop("utm_medium", None)
        query.pop("utm_campaign", None)
        query.pop("gclid", None)
        query.pop("fbclid", None)
        cleaned = parsed._replace(
            query=urlencode(query, doseq=True),
            fragment=""
        )
        return urlunparse(cleaned)
    except Exception:
        return url


def _domain(url: str) -> str:
    """Extract root domain from URL."""
    try:
        netloc = httpx.URL(url).host or ""
        parts = netloc.replace("www.", "").split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else netloc
    except Exception:
        return ""


def _is_banned(url: str) -> bool:
    """Return True if URL points to a banned/junk domain."""
    try:
        host = httpx.URL(url).host or ""
    except Exception:
        return False
    return any(d in host for d in BANNED_DOMAINS)


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 0: Google Maps — HTTPX scrape of mobile Maps page (no API key needed)
# ═══════════════════════════════════════════════════════════════════════════════

async def _source_google_maps(query: str, count: int) -> list:
    """Scrape Google Maps mobile search page using httpx + regex."""
    leads = []
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        search_url = f"https://www.google.com/maps/search/{httpx.utils.quote(query)}"

        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=20.0
        ) as client:
            resp = await client.get(search_url)
            if resp.status_code != 200:
                logger.warning(f"[GMAPS] HTTP {resp.status_code}")
                return leads

            # Google Maps embeds data in window.APP_INITIALIZATION_STATE or
            # as NRE-style JSON fragments in the HTML
            html = resp.text

            # Try to find the big JSON array embedded in the page
            # Pattern: window.APP_INITIALIZATION_STATE = [...]
            json_match = re.search(
                r'window\.APP_INITIALIZATION_STATE\s*=\s*(\[.*?\]);',
                html, re.DOTALL
            )
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    leads = _parse_maps_json(data, count)
                    logger.info(f"[GMAPS] Parsed {len(leads)} leads from APP_INITIALIZATION_STATE")
                except (json.JSONDecodeError, Exception) as e:
                    logger.warning(f"[GMAPS] JSON parse error: {e}")

            # Fallback: try regex extraction of NRE blocks from raw HTML
            if not leads:
                leads = _parse_maps_regex(html, count)
                logger.info(f"[GMAPS] Regex fallback found {len(leads)} leads")

    except Exception as e:
        logger.error(f"[GMAPS] Error: {e}")
    return leads[:count]


def _parse_maps_json(data, count: int) -> list:
    """Parse Google Maps APP_INITIALIZATION_STATE JSON array."""
    leads = []
    try:
        # The nested structure is deeply nested; dive into index 0 then index 0
        if not isinstance(data, list) or len(data) < 2:
            return leads
        section = data[3] if len(data) > 3 else data[0]
        if not isinstance(section, list):
            return leads
        # Business entries
        for item in section:
            if not isinstance(item, list) or len(item) < 5:
                continue
            try:
                lead = _extract_maps_item(item)
                if lead and lead.get("business"):
                    leads.append(lead)
                    if len(leads) >= count:
                        break
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[GMAPS JSON] parse error: {e}")
    return leads


def _extract_maps_item(item) -> dict:
    """Extract lead fields from a single Maps JSON list item."""
    business = ""
    phone = ""
    website = ""
    rating = 0.0
    review_count_text = ""

    # Layout varies — walk fields defensively
    # Typical: [None, None, "Name", "Category", "Address", "Phone", "", "", "Website", None, None, ...]
    i = 0
    while i < len(item):
        val = item[i]
        if isinstance(val, str):
            if not business and i >= 2 and not val.startswith("http"):
                # Could be the business name — check next field is a category
                if i + 1 < len(item) and isinstance(item[i + 1], str):
                    business = val
            if PHONE_RE.match(val):
                phone = val
            if val.startswith("http"):
                if "google.com" not in val and "maps.google" not in val:
                    website = val
            if re.match(r'^\d\.\d$', val):
                rating = float(val)
        elif isinstance(val, list):
            # Rating array: [null,"4.5",["123 reviews"],...]
            if len(val) >= 2 and isinstance(val[1], str) and re.match(r'^\d\.\d$', val[1]):
                rating = float(val[1])
            if len(val) >= 3 and isinstance(val[2], list) and val[2]:
                review_count_text = str(val[2][0]) if val[2][0] else ""
        i += 1

    if not business:
        return {}

    vertical = "Unknown"
    return {
        "business": business,
        "url": website or "",
        "phone": phone,
        "email": "",
        "owner": "",
        "snippet": f"Rating: {rating} ({review_count_text})",
        "score": 0,
        "status": "new",
        "vertical": vertical,
        "source_type": "Google Maps",
    }


def _parse_maps_regex(html: str, count: int) -> list:
    """Low-level HTML regex fallback — extract NRE-JSON blocks from Maps page."""
    leads = []
    # Google encodes data as JavaScript arrays like [null,null,"Name","Category",...]
    # We look for sequences with phone-like patterns
    blocks = re.findall(r'\[null,null,"([^"]+)","([^"]*?)","([^"]*?)","(\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4})"', html)
    seen = set()
    for biz_name, category, address, phone in blocks:
        if biz_name in seen or len(leads) >= count:
            continue
        seen.add(biz_name)
        leads.append({
            "business": biz_name,
            "url": "",
            "phone": phone,
            "email": "",
            "owner": "",
            "snippet": f"Category: {category} | Address: {address}",
            "score": 0,
            "status": "new",
            "vertical": category or "Unknown",
            "source_type": "Google Maps",
        })
    return leads


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 1: DuckDuckGo business search
# ═══════════════════════════════════════════════════════════════════════════════

async def _source_duckduckgo(query: str, count: int) -> list:
    """Use DDGS to find business websites for a query."""
    leads = []
    try:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    query,
                    max_results=count,
                    safesearch="strict",
                    region="us-en"
                ))

        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        for res in results:
            url = res.get("href", res.get("link", ""))
            title = res.get("title", "")
            if not url or not url.startswith("http"):
                continue
            if _is_banned(url):
                continue
            leads.append({
                "business": "",
                "url": url,
                "phone": "",
                "email": "",
                "owner": "",
                "snippet": res.get("body", res.get("snippet", "")),
                "score": 0,
                "status": "new",
                "vertical": query.split()[0].title() if query else "Unknown",
                "source_type": "DuckDuckGo",
                "_title": title,
            })
    except Exception as e:
        logger.error(f"[DDG] Error: {e}")
    return leads


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE 2: Yelp slug parsing
# ═══════════════════════════════════════════════════════════════════════════════

async def _source_yelp(query: str, count: int) -> list:
    """DuckDuckGo search for yelp.com/biz/ URLs, parse slug to get business name."""
    leads = []
    try:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(
                    f"{query} site:yelp.com",
                    max_results=count * 3,
                    safesearch="strict",
                    region="us-en"
                ))

        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        seen = set()
        for res in results:
            url = res.get("href", res.get("link", ""))
            if not url:
                continue
            # Match yelp.com/biz/URL-safe-slug
            biz_match = re.search(r'yelp\.com/biz/([a-zA-Z0-9\-%]+)', url)
            if not biz_match:
                continue
            slug = biz_match.group(1)
            if slug in seen:
                continue
            seen.add(slug)
            biz_name = slug.replace("-", " ").replace("%20", " ").title()
            biz_name = re.sub(r'\s+\d+$', '', biz_name)

            # Try to extract phone from snippet
            snippet = res.get("body", res.get("snippet", ""))
            phone_m = PHONE_RE.search(snippet)
            phone = phone_m.group(0) if phone_m else ""

            leads.append({
                "business": biz_name,
                "url": url,
                "phone": phone,
                "email": "",
                "owner": "",
                "snippet": snippet,
                "score": 0,
                "status": "new",
                "vertical": query.split()[0].title() if query else "Unknown",
                "source_type": "Yelp",
            })
            if len(leads) >= count:
                break
    except Exception as e:
        logger.error(f"[YELP] Error: {e}")
    return leads


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS: owner search, email extraction, scoring
# ═══════════════════════════════════════════════════════════════════════════════

async def search_owner_from_website(url: str) -> str:
    """
    Try to find the business owner name from:
    1. About/Team/Contact pages via httpx
    2. DDG site-search for owner mentions
    Returns owner name string or empty string.
    """
    if not url:
        return ""
    try:
        base_url = url.rstrip("/")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }

        # ── Strategy 1: Scan About/Team/Contact pages ──────────────
        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=12.0
        ) as client:
            for path in ABOUT_PAGES:
                check_url = base_url if path == "/" else base_url.rstrip("/") + path
                try:
                    resp = await client.get(check_url, timeout=8.0)
                    if resp.status_code == 200:
                        owner = _find_owner_in_text(resp.text)
                        if owner:
                            logger.info(f"[OWNER] Found '{owner}' on {check_url}")
                            return owner
                except Exception:
                    continue

        # ── Strategy 2: Homepage scan ──────────────────────────────
        try:
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=12.0
            ) as client:
                resp = await client.get(base_url, timeout=8.0)
                if resp.status_code == 200:
                    owner = _find_owner_in_text(resp.text)
                    if owner:
                        logger.info(f"[OWNER] Found '{owner}' on homepage {base_url}")
                        return owner
        except Exception:
            pass

        # ── Strategy 3: DDG site-search ───────────────────────────
        owner = await _ddg_owner_search(base_url)
        if owner:
            return owner

    except Exception as e:
        logger.warning(f"[OWNER] Error for {url}: {e}")
    return ""


def _find_owner_in_text(text: str) -> str:
    """Run all OWNER_PATTERNS against text; return first match or empty string."""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean)
    for pat in OWNER_PATTERNS:
        m = pat.search(clean)
        if m:
            candidate = m.group(1).strip()
            if _is_plausible_name(candidate):
                return candidate
    return ""


async def _ddg_owner_search(url: str) -> str:
    """Use DDG to search for owner/CEO mentions on a given website."""
    try:
        domain = httpx.URL(url).host or ""
        query = f'site:{domain} "Owner" OR "CEO" OR "Founder"'
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=3, safesearch="strict"))
        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        for res in results:
            combined = (res.get("title", "") + " " + res.get("body", "")).lower()
            if domain not in combined:
                continue
            snippet = res.get("body", res.get("snippet", ""))
            owner = _find_owner_in_text(snippet + " " + res.get("title", ""))
            if owner:
                return owner
    except Exception as e:
        logger.debug(f"[OWNER DDG] {e}")
    return ""


async def extract_emails_from_page(url: str, base_url: str = "") -> list:
    """
    Extract email addresses from a website's main page and contact/about pages.
    Returns a deduplicated list of unique email strings.
    """
    emails: set = set()
    if not url:
        return []
    base_url = base_url or url
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
    }

    async def _fetch_emails(target_url: str) -> list:
        try:
            async with httpx.AsyncClient(
                headers=headers, follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(target_url, timeout=8.0)
                if resp.status_code == 200:
                    found = EMAIL_RE.findall(resp.text)
                    return found
        except Exception:
            pass
        return []

    # Homepage
    found = await _fetch_emails(url)
    emails.update(found)

    # Common contact pages
    if not emails:
        try:
            host = httpx.URL(url).host or ""
        except Exception:
            host = ""
        for path in ["/contact", "/contact-us", "/about", "/about-us"]:
            if host:
                check = f"https://{host}{path}"
                found = await _fetch_emails(check)
                emails.update(found)
                if emails:
                    break

    # Deduplicates and filter known-noise patterns
    noise = {"example.com", "domain.com", "email.com", "test.com", "wix.com"}
    cleaned = {e for e in emails if e.split("@")[-1].lower() not in noise}
    return sorted(cleaned)


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def score_lead(lead: dict) -> dict:
    """
    Score a lead dict in-place based on field completeness.

    Base: 50
    +15: has phone
    +15: has owner name
    +10: has email
    +15: has rating >= 4.0
    Total: up to 105  → clamp to 100
    """
    score = 50
    if lead.get("phone"):
        score += 15
    if lead.get("owner"):
        score += 15
    if lead.get("email"):
        score += 10
    # Rating bonus
    snippet = lead.get("snippet", "")
    rating_m = re.search(r'(\d\.\d)', snippet)
    if rating_m and float(rating_m.group(1)) >= 4.0:
        score += 15
    lead["score"] = min(score, 100)
    return lead


def _determine_status(score: int) -> str:
    if score >= 80:
        return "hot"
    if score >= 55:
        return "warm"
    return "cold"


def _detect_vertical(query: str, snippet: str = "") -> str:
    """Very lightweight vertical labeler."""
    combined = (query + " " + snippet).lower()
    mapping = {
        "contractor": "Contractor",
        "roofing": "Roofing",
        "plumbing": "Plumbing",
        "electrician": "Electrical",
        "hvac": "HVAC",
        "cleaning": "Cleaning",
        "landscaping": "Landscaping",
        "real estate": "Real Estate",
        "restaurant": "Restaurant",
        "cafe": "Restaurant",
        "salon": "Beauty",
        "spa": "Beauty",
        "gym": "Fitness",
        "fitness": "Fitness",
        "lawyer": "Legal",
        "attorney": "Legal",
        "dentist": "Dental",
        "dental": "Dental",
        "auto": "Automotive",
        "car": "Automotive",
        "insurance": "Insurance",
        "marketing": "Marketing",
    }
    for keyword, label in mapping.items():
        if keyword in combined:
            return label
    return "General Business"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

async def _enrich_leads(leads: list, query: str, max_workers: int = 5) -> list:
    """
    Enrich each lead with phone, owner name, email and score.
    Runs owner-search and email-extraction concurrently.
    """
    enriched = []
    semaphore = asyncio.Semaphore(max_workers)

    async def _do_enrich(lead: dict) -> dict:
        async with semaphore:
            url = lead.get("url", "")

            # Owner name
            if not lead.get("owner"):
                owner = await search_owner_from_website(url)
                lead["owner"] = owner or ""

            # Email
            if url and not lead.get("email"):
                emails = await extract_emails_from_page(url)
                lead["email"] = emails[0] if emails else ""

            # Phone from URL/snippet
            if not lead.get("phone"):
                combined_text = (
                    lead.get("snippet", "") + " " + lead.get("body", "")
                )
                phone_m = PHONE_RE.search(combined_text)
                if phone_m:
                    lead["phone"] = phone_m.group(0)

            # Inline business name
            if not lead.get("business"):
                lead["business"] = lead.get("_title", "") or _domain(url) or "Unknown"

            # Score
            score_lead(lead)
            lead["status"] = _determine_status(lead["score"])
            lead["vertical"] = _detect_vertical(query, lead.get("snippet", ""))

            # Clean raw fields
            lead.pop("_title", None)
            lead.pop("body", None)
            return lead

    tasks = [_do_enrich(lead) for lead in leads]
    enriched = await asyncio.gather(*tasks, return_exceptions=False)
    return enriched


def _normalize_raw_lead(raw: dict) -> dict:
    """Normalize a raw lead dict to the canonical schema."""
    return {
        "business": raw.get("business", raw.get("title", "")),
        "url": raw.get("url", ""),
        "phone": raw.get("phone", ""),
        "email": raw.get("email", ""),
        "owner": raw.get("owner", ""),
        "snippet": raw.get("snippet", ""),
        "score": 0,
        "status": "new",
        "vertical": "Unknown",
        "source_type": raw.get("source_type", "Unknown"),
    }


async def find_leads_v2(count: int = 5, query: str = "business leads") -> dict:
    """
    Main entry point — same interface as find_leads_v2().
    Returns {"text": str, "leads": list[dict]}.

    Sources: Google Maps (HTTPX), DuckDuckGo, Yelp slug parse.
    Enrichment: owner name + email via website scraping.
    """
    count = int(count)
    query = (query or "business leads").strip()
    logger.info(f"[LEAD GEN V2] Searching for {count} leads: '{query}'")
    all_leads: list[dict] = []

    # ── Source 0: Google Maps (HTTPX mobile page) ─────────────────────────
    try:
        maps_leads = await _source_google_maps(query, count * 3)
        all_leads.extend(maps_leads)
        logger.info(f"[V2] Google Maps → {len(maps_leads)} raw leads")
    except Exception as e:
        logger.warning(f"[V2] Google Maps failed: {e}")

    # ── Source 1: DuckDuckGo ───────────────────────────────────────────────
    try:
        ddg_leads = await _source_duckduckgo(query, max(count * 4, 20))
        all_leads.extend(ddg_leads)
        logger.info(f"[V2] DuckDuckGo → {len(ddg_leads)} raw leads")
    except Exception as e:
        logger.warning(f"[V2] DuckDuckGo failed: {e}")

    # ── Source 2: Yelp ─────────────────────────────────────────────────────
    try:
        yelp_leads = await _source_yelp(query, count * 3)
        all_leads.extend(yelp_leads)
        logger.info(f"[V2] Yelp → {len(yelp_leads)} raw leads")
    except Exception as e:
        logger.warning(f"[V2] Yelp failed: {e}")

    # ── Normalize + dedup ───────────────────────────────────────────────────
    normalized = [_normalize_raw_lead(l) for l in all_leads]

    deduped = []
    seen_domains: set = set()
    seen_names: set = set()

    for lead in normalized:
        url = lead.get("url", "")
        biz = lead.get("business", "")

        if not url or not url.startswith("http"):
            continue
        if _is_banned(url):
            continue

        domain = _domain(url)
        if domain and domain in seen_domains:
            continue

        name_key = biz.lower().strip()
        if name_key and name_key in seen_names:
            continue

        if domain:
            seen_domains.add(domain)
        if name_key:
            seen_names.add(name_key)

        deduped.append(lead)

    logger.info(f"[V2] After dedup: {len(deduped)} leads")

    # ── Enrich (owner + email + score) ────────────────────────────────────
    enriched = await _enrich_leads(deduped[:count * 3], query, max_workers=min(8, count + 2))

    # ── Sort by score desc, keep top N ─────────────────────────────────────
    enriched.sort(key=lambda l: l.get("score", 0), reverse=True)
    final = enriched[:count]

    # ── Build result text ──────────────────────────────────────────────────
    if not final:
        return {
            "text": (
                "No business leads found for that query. "
                "Try: 'roofing contractors Miami' or 'dentist Austin'."
            ),
            "leads": [],
        }

    lines = [f"**Found {len(final)} Business Leads for '{query}':**\n"]
    for i, l in enumerate(final, 1):
        badge = {"hot": "🔥", "warm": "🌤️", "cold": "❄️", "new": "🆕"}.get(l.get("status", ""), "")
        lines.append(
            f"{i}. {badge} **{l['business']}** "
            f"(Score: {l['score']}/100, {l['status'].upper()})\n"
            f"   🔗 {l['url']}\n"
            + (f"   📞 {l['phone']}\n" if l.get('phone') else "")
            + (f"   ✉️ {l['email']}\n" if l.get('email') else "")
            + (f"   👤 Owner: {l['owner']}\n" if l.get('owner') else "")
            + f"   🏷️ {l.get('vertical', 'Unknown')} | Via: {l.get('source_type', 'Unknown')}\n"
        )
    unique_sources = len({l.get("source_type") for l in final})
    lines.append(f"\n_Queried {len(all_leads)} raw leads from {unique_sources} sources._")

    return {
        "text": "\n".join(lines),
        "leads": final,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI TEST BLOCK
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def _run_test():
        test_query = sys.argv[1] if len(sys.argv) > 1 else "roofing contractors Austin"
        test_count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        result = await find_leads_v2(count=test_count, query=test_query)
        text = result.get("text", "No results")
        leads = result.get("leads", [])
        print("\n" + "=" * 60)
        print(text)
        print("=" * 60)
        print(f"\nLead count: {len(leads)}")
        for lead in leads:
            print(
                f"  [{lead.get('score', 0):3d}] {lead.get('status', ''):5s} | "
                f"{lead.get('business', '?')[:35]:35s} | "
                f"{lead.get('phone', '—'):14s} | "
                f"{lead.get('owner', '—')[:20]:20s} | "
                f"{lead.get('email', '—')[:25]:25s}"
            )

    asyncio.run(_run_test())
