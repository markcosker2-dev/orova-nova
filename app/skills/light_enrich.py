import os
import re
import json
import asyncio
import httpx
import logging
import urllib.parse
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from app.skills.notes_skill import log_skill_note

logger = logging.getLogger(__name__)

# ─── SINGLETONS, EXECUTORS AND HELPERS ────────────────────────────
_ai_client = None
_ai_client_lock = asyncio.Lock()

async def _get_ai_client_async():
    global _ai_client
    if _ai_client is None:
        async with _ai_client_lock:
            if _ai_client is None:
                from app.core.ai_client import UnifiedAIClient
                _ai_client = UnifiedAIClient()
    return _ai_client


_shared_client = None
_shared_client_lock = asyncio.Lock()

async def _get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        async with _shared_client_lock:
            if _shared_client is None:
                _shared_client = httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=8.0,
                    verify=True,
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                )
    return _shared_client


_firecrawl_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="firecrawl")
_crawl_semaphore = asyncio.Semaphore(10)
_NON_DIGIT_RE = re.compile(r'\D')


def _score_and_select_email(emails: list, domain: str) -> Optional[str]:
    if not emails:
        return None
    # 1. Prioritize domain matches
    domain_matches = [e for e in emails if e.lower().endswith(f"@{domain}")]
    if domain_matches:
        # Prioritize non-generic domain matches
        non_generic = [e for e in domain_matches if not any(g in e.lower() for g in ["info@", "contact@", "sales@", "hello@", "support@"])]
        if non_generic:
            return non_generic[0]
        return domain_matches[0]
    # 2. Then non-generic emails
    non_generic = [e for e in emails if not any(g in e.lower() for g in ["info@", "contact@", "sales@", "hello@", "support@"])]
    if non_generic:
        return non_generic[0]
    # 3. Fallback to the first one
    return emails[0]


def _normalize_phone_to_e164(phone: str) -> str:
    if not phone:
        return ""
    digits = _NON_DIGIT_RE.sub('', phone)
    if len(digits) < 10:
        return ""
    
    # Detect fake/placeholder numbers
    raw_number = digits[-10:]  # Get last 10 digits for validation
    
    # Check for repeated digits (e.g., 1111111111)
    if len(set(raw_number)) == 1:
        logger.warning(f"[PHONE] Rejecting fake number with repeated digits: '{phone}'")
        return ""
    
    # Check for sequential patterns (1234567890, 9876543210, 0123456789)
    sequential_patterns = ["1234567890", "9876543210", "0123456789", "2345678901", "0987654321"]
    if raw_number in sequential_patterns:
        logger.warning(f"[PHONE] Rejecting fake sequential number: '{phone}'")
        return ""
    
    # Check for numbers starting with 999 (like +19999999999)
    if raw_number.startswith("999"):
        logger.warning(f"[PHONE] Rejecting fake number starting with 999: '{phone}'")
        return ""
    
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    elif len(digits) > 10:
        return f"+{digits}"
    return ""

# ═══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT ENGINE V4 — Patched Core
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_REGEX = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
PHONE_REGEX = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

JUNK_EMAIL_PATTERNS = [
    'example', '.png', '.jpg', '.gif', '.svg', '.webp', '.css', '.js',
    'sentry', 'webpack', 'wixpress', 'noreply', 'no-reply', 'donotreply',
    'test@', 'email@', 'your@', 'name@', 'user@', 'admin@', 'support@',
    'privacy@', 'legal@', 'abuse@', 'postmaster@', 'mailer-daemon',
]

BLOCK_SIGNALS = [
    "cf-browser-verification",
    "challenge-form",
    "checking your browser",
    "enable javascript and cookies",
    "ddos-guard",
    "just a moment",
    "ray id",
    "captcha",
    "bot protection",
]

TITLE_KEYWORDS = [
    "owner", "founder", "co-founder", "ceo", "chief executive",
    "president", "principal", "operator", "managing director",
    "managing partner", "partner", "director",
]

OWNER_PATTERNS = [
    r'(?:owner|co[-\s]?owner|founder|co[-\s]?founder|ceo|chief\s+executive|president|principal|operator|partner)[:\s,\-–]+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,3})',
    r'([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,3})[,\s\-–]+(?:owner|co[-\s]?owner|founder|co[-\s]?founder|ceo|chief\s+executive|president|principal|operator)',
    r"I(?:'m| am)\s+([A-Za-z\'\-]+\s+[A-Za-z\'\-]+),?\s*(?:owner|founder|ceo|president|principal)",
    r'(?:founded|owned|run|operated|started|led)\s+by\s+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})',
    r'(?:meet|introducing)\s+([A-Za-z\'\-]+(?:\s+[A-Za-z\'\-]+){1,2})[,\s]+(?:our\s+)?(?:owner|founder|ceo|president)',
]

FALSE_POSITIVE_NAMES = frozenset({
    'About Us', 'Contact Us', 'Read More', 'Learn More', 'Our Team',
    'Get Started', 'Meet Our', 'Our Story', 'Click Here', 'Sign Up',
    'Log In', 'View More', 'See All', 'Find Out', 'Call Now',
    'Free Quote', 'Get Quote', 'Request Quote', 'Schedule Now',
    'Book Now', 'Learn More', 'See More',
})

LOCATION_BLACKLIST = frozenset({
    "Silver Lake", "Los Angeles", "New York", "Brooklyn", "Chicago", "San Francisco", "Seattle", "Portland", "Austin", "Denver", "Miami", "Boston", "Santa Monica", "Beverly Hills", "Hollywood", "Pasadena", "Long Beach", "Anaheim", "Irvine", "San Diego", "Oakland", "Berkeley", "Sacramento", "Fresno", "Kansas City", "Phoenix", "Las Vegas", "Atlanta", "Dallas", "Houston", "Nashville", "Phoenix", "Philadelphia", "Pittsburgh", "Cincinnati", "Columbus", "Charlotte", "Raleigh", "Orlando", "Tampa", "St. Louis", "Minneapolis", "Detroit", "Cleveland", "Indianapolis", "Jacksonville", "Memphis", "Baltimore", "Milwaukee", "Albuquerque", "Tucson", "Omaha", "Tulsa", "Arlington", "Tallahassee", "Baton Rouge", "Richmond", "Des Moines", "Little Rock", "Jackson", "Frankfort", "Montgomery", "Juneau", "Honolulu", "Anchorage",
})

MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.pdf', '.mp4', '.mov'}
CDN_PATTERNS = ['cloudinary', 'cloudfront', 'amazonaws', 'akamai', 'imgix', 'twimg', 'fbcdn', 'yelpcdn.com']


async def _fetch_page(url: str) -> Optional[Dict[str, str]]:
    """
    Fetch a page and return {"html": ..., "markdown": ...}.
    BUG FIX: Returns a dict so callers can choose html (for BeautifulSoup) or markdown (for regex).
    """
    UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    ]

    _client = await _get_shared_client()

    for ua in UA_POOL[:2]:
        try:
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
            resp = await _client.get(url, headers=headers)

            if resp.status_code not in (200, 203):
                logger.debug(f"[FETCH] HTTP {resp.status_code} for {url}")
                continue

            html = resp.text
            lower = html.lower()

            if _is_blocked(lower):
                logger.info(f"[FETCH] Bot-wall detected for {url}, trying next UA...")
                continue

            if len(html) < 500:
                logger.debug(f"[FETCH] Response too small ({len(html)} chars) for {url}")
                continue

            return {"html": html, "markdown": ""}

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"[FETCH] HTTPX error for {url}: {e}")
            continue

    logger.info(f"[FETCH] Falling back to Firecrawl for {url}")
    try:
        scrape_data = await asyncio.get_running_loop().run_in_executor(
            _firecrawl_executor, _firecrawl_scrape, url
        )
        markdown = scrape_data.get("markdown", "")
        html = scrape_data.get("html", "")

        if not markdown and not html:
            return None
        if _is_blocked((html or markdown).lower()):
            return None

        return {"html": html, "markdown": markdown}

    except Exception as e:
        logger.warning(f"[FETCH] Firecrawl fallback failed for {url}: {e}")

    return None


def _is_blocked(html_lower: str) -> bool:
    return any(sig in html_lower for sig in BLOCK_SIGNALS)


def _extract_emails(html: str) -> list:
    """Extract valid emails from HTML: checks JSON-LD, mailto links, raw text regex, and obfuscations."""
    if not html:
        return []

    found = set()
    soup = BeautifulSoup(html, "html.parser")

    # Single full-text extraction — reuse across all regex passes
    full_text = soup.get_text(separator=" ")
    entity_decoded_text = full_text.replace("&#64;", "@").replace("&#x40;", "@").replace("&commat;", "@")

    # 1. JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            _walk_json_for_emails(data, found)
        except Exception:
            pass

    # 2. mailto: href
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.lower().startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email:
                found.add(email.lower())

    # 3. HTML entity decode pass on the decoded text
    for e in re.findall(EMAIL_REGEX, entity_decoded_text):
        found.add(e.lower())

    # 4. data-* attributes
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if isinstance(val, str) and "email" in attr.lower():
                matches = re.findall(EMAIL_REGEX, val)
                for m in matches:
                    found.add(m.lower())

    # 6. Obfuscated text patterns
    obf_patterns = [
        r'([a-zA-Z0-9._%+\-]+)\s*[\[\(]?\s*(?:at|AT)\s*[\]\)]?\s*([a-zA-Z0-9.\-]+)\s*[\[\(]?\s*(?:dot|DOT)\s*[\]\)]?\s*([a-zA-Z]{2,})',
        r'([a-zA-Z0-9._%+\-]+)\s+at\s+([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    ]
    for pat in obf_patterns:
        for m in re.finditer(pat, full_text, re.IGNORECASE):
            groups = m.groups()
            if len(groups) == 3:
                found.add(f"{groups[0]}@{groups[1]}.{groups[2]}".lower())
            elif len(groups) == 2:
                candidate = f"{groups[0]}@{groups[1]}".lower()
                if re.match(EMAIL_REGEX, candidate):
                    found.add(candidate)

    # 7. Reversed span trick
    for tag in soup.find_all(["span", "div"], attrs={"class": re.compile(r'email|contact|mail', re.I)}):
        inner = tag.get_text(separator="")
        reversed_text = inner[::-1]
        for e in re.findall(EMAIL_REGEX, reversed_text):
            found.add(e.lower())

    clean = [
        e for e in found
        if not any(j in e for j in JUNK_EMAIL_PATTERNS)
        and re.match(r'^[^@]+@[^@]+\.[a-z]{2,}$', e)
        and len(e) < 80
    ]

    return clean


def _walk_json_for_emails(obj: Any, found: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("email", "contactemail", "e-mail"):
                if isinstance(v, str) and "@" in v:
                    found.add(v.lower())
            else:
                _walk_json_for_emails(v, found)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_emails(item, found)


def _extract_owner_name(html: str) -> Optional[str]:
    """Multi-strategy owner/founder name extraction including JSON-LD and fixed DOM adjacency."""
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")

    # 1. JSON-LD / Schema.org
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            name = _walk_json_for_person(data)
            if name and name not in FALSE_POSITIVE_NAMES:
                return name
        except Exception:
            pass

    # 2. Meta tags
    for attr_name in ("author", "article:author", "og:author"):
        tag = soup.find("meta", attrs={"name": attr_name}) or soup.find("meta", attrs={"property": attr_name})
        if tag and tag.get("content"):
            val = tag["content"].strip()
            if _is_plausible_name(val):
                return val

    # 3. DOM adjacency scan — FIXED (capped to prevent CPU blocking)
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "p", "span"], limit=300)
    for tag in heading_tags:
        direct_text = "".join(
            child for child in tag.children if isinstance(child, NavigableString)
        ).strip()

        if not _is_plausible_name(direct_text):
            continue

        context_parts = []
        sib = tag.find_next_sibling()
        if sib:
            context_parts.append(sib.get_text(separator=" ", strip=True).lower())
        parent_sib = tag.parent.find_next_sibling() if tag.parent else None
        if parent_sib:
            context_parts.append(parent_sib.get_text(separator=" ", strip=True).lower())
        nxt = tag.find_next()
        if nxt and nxt != sib:
            context_parts.append(nxt.get_text(separator=" ", strip=True).lower())

        combined_context = " ".join(context_parts)
        if any(kw in combined_context for kw in TITLE_KEYWORDS):
            name = direct_text.strip()
            if name not in FALSE_POSITIVE_NAMES and _is_plausible_name(name):
                logger.debug(f"[OWNER] DOM adjacency hit: {name}")
                return name
            # Skip false positives like "About Us" — keep scanning

        tag_lower = direct_text.lower()
        if any(kw in tag_lower for kw in TITLE_KEYWORDS):
            prev_sib = tag.find_previous_sibling()
            if prev_sib:
                prev_text = "".join(
                    c for c in prev_sib.children if isinstance(c, NavigableString)
                ).strip()
                if _is_plausible_name(prev_text) and prev_text not in FALSE_POSITIVE_NAMES:
                    logger.debug(f"[OWNER] Reverse DOM hit: {prev_text}")
                    return prev_text
        # END — do NOT fall through to Strategy 4 with garbage from TITLE_KEYWORD headings

    # 4. Full-text regex (case-insensitive)
    full_text = soup.get_text(separator=" ", strip=True)
    for pattern in OWNER_PATTERNS:
        for match in re.finditer(pattern, full_text, re.IGNORECASE):
            raw = match.group(1).strip()
            name = " ".join(w.capitalize() for w in raw.split())
            if _is_plausible_name(name) and name not in FALSE_POSITIVE_NAMES:
                logger.debug(f"[OWNER] Regex hit: {name}")
                return name

    # 5. About/Team section heuristic
    for section_id in ["about", "team", "our-team", "meet", "founder", "leadership"]:
        section = soup.find(id=re.compile(section_id, re.I)) or \
                  soup.find(class_=re.compile(section_id, re.I))
        if section:
            for heading in section.find_all(["h2", "h3", "h4", "strong", "b"]):
                text = heading.get_text(strip=True)
                if text not in FALSE_POSITIVE_NAMES and _is_plausible_name(text):
                    surrounding = heading.find_parent().get_text(separator=" ", strip=True).lower()
                    if any(kw in surrounding for kw in TITLE_KEYWORDS):
                        return text

    return None


def _walk_json_for_person(obj: Any) -> Optional[str]:
    if isinstance(obj, dict):
        schema_type = obj.get("@type", "")

        if schema_type in ("Person", "Employee"):
            job = obj.get("jobTitle", "").lower()
            name = obj.get("name", "")
            if any(kw in job for kw in TITLE_KEYWORDS) and _is_plausible_name(name):
                return name.strip()

        for key in ("founder", "employee", "author", "member", "contactPoint", "makesOffer"):
            val = obj.get(key)
            if val:
                result = _walk_json_for_person(val)
                if result:
                    return result

        for v in obj.values():
            if isinstance(v, (dict, list)):
                result = _walk_json_for_person(v)
                if result:
                    return result

    elif isinstance(obj, list):
        for item in obj:
            result = _walk_json_for_person(item)
            if result:
                return result

    return None


def _is_plausible_name(text: str) -> bool:
    if not text or len(text) < 4 or len(text) > 50:
        return False
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Za-z'\-]+$", p) for p in parts):
        return False
    if not parts[0][0].isupper():
        return False
    if text in FALSE_POSITIVE_NAMES:
        return False
    stop_words = {"and", "the", "for", "with", "from", "our", "your", "their"}
    if any(p.lower() in stop_words for p in parts):
        return False
    # Reject names that are purely location names
    if text in LOCATION_BLACKLIST:
        return False
    return True


async def _ddg_enrich_contact(biz_name: str, domain: str) -> Tuple[Optional[str], Optional[str]]:
    """Block-free snippet mining for owner name + email using Tavily (first choice) or Bing scraper, parsed via Gemini 2.0 LLM or regex fallback."""
    found_owner = None
    found_email = None

    queries = {
        "owner": [
            f'"{biz_name}" owner OR founder OR CEO',
            f'site:linkedin.com "{biz_name}" owner OR founder',
        ],
        "email": [
            f'"{biz_name}" "@{domain}"',
            f'"{biz_name}" contact email "{domain}"',
        ],
    }

    tavily_key = os.getenv("TAVILY_API_KEY")
    results = {"owner": [], "email": []}

    # 🚀 Try Tavily First (If Key Present)
    if tavily_key:
        logger.info(f"[ENRICH] Using Tavily for contact enrichment of {biz_name}...")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                owner_tasks = []
                email_tasks = []
                
                async def _fetch_tavily_owner(q):
                    payload = {"api_key": tavily_key, "query": q, "max_results": 3, "search_depth": "light"}
                    resp = await client.post("https://api.tavily.com/search", json=payload)
                    if resp.status_code == 200:
                        for res in resp.json().get("results", []):
                            results["owner"].append({
                                "title": res.get("title", ""),
                                "snippet": res.get("content", ""),
                            })
                            
                async def _fetch_tavily_email(q):
                    payload = {"api_key": tavily_key, "query": q, "max_results": 2, "search_depth": "light"}
                    resp = await client.post("https://api.tavily.com/search", json=payload)
                    if resp.status_code == 200:
                        for res in resp.json().get("results", []):
                            results["email"].append({
                                "title": res.get("title", ""),
                                "snippet": res.get("content", ""),
                            })
                            
                for q in queries["owner"][:2]:
                    owner_tasks.append(_fetch_tavily_owner(q))
                for q in queries["email"][:2]:
                    email_tasks.append(_fetch_tavily_email(q))
                    
                await asyncio.gather(*(owner_tasks + email_tasks), return_exceptions=True)
        except Exception as e:
            logger.warning(f"[ENRICH] Tavily contact search failed: {e}")

    # 🌐 Fallback to Direct Bing & DuckDuckGo Scrapers (100% Free, Block-proof)
    if not results["owner"] and not results["email"]:
        logger.info(f"[ENRICH] Using free block-proof search scrapers for {biz_name}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        async def _fetch_ddg_and_bing(client, query, category):
            # DDG Search
            try:
                ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
                resp = await client.get(ddg_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.select("div.result, div.web-result")
                    for item in items:
                        a_tag = item.select_one("a.result__a, a.result__url")
                        snippet_tag = item.select_one("a.result__snippet, div.result__snippet")
                        if a_tag:
                            results[category].append({
                                "title": a_tag.get_text(strip=True),
                                "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                            })
            except Exception as e:
                logger.debug(f"[ENRICH] DDG {category} search error: {e}")

            # Bing Search
            try:
                search_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.select("li.b_algo")
                    for item in items:
                        title_el = item.select_one("h2 a")
                        snippet_el = item.select_one("div.b_caption p, p")
                        results[category].append({
                            "title": title_el.get_text(strip=True) if title_el else "",
                            "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                        })
            except Exception as e:
                logger.debug(f"[ENRICH] Bing {category} search error: {e}")

        try:
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=5.0) as client:
                tasks = []
                for q in queries["owner"][:2]:
                    tasks.append(_fetch_ddg_and_bing(client, q, "owner"))
                for q in queries["email"][:2]:
                    tasks.append(_fetch_ddg_and_bing(client, q, "email"))
                
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"[ENRICH] Direct search scrapers failed: {e}")

    # 🤖 1. HAWK AI LLM Extraction (Super Accurate, Free Gemini-2.0-flash-lite)
    if results["owner"] or results["email"]:
        logger.info(f"[ENRICH] Running Hawk AI LLM parsing on search snippets for {biz_name}...")
        combined_snippets = []
        for i, r in enumerate(results["owner"] + results["email"], 1):
            combined_snippets.append(
                f"Result {i}:\nTitle: {r.get('title')}\nSnippet: {r.get('snippet')}\n"
            )
        
        snippets_text = "\n".join(combined_snippets)
        
        system_prompt = (
            "You are 'Hawk', the B2B lead enrichment subagent.\n"
            "Your task is to analyze the provided search engine results for a local business and extract:\n"
            "1. The full name of the owner, founder, CEO, president, or top executive (2-3 words, properly capitalized, e.g., 'John Doe'). Avoid false positives.\n"
            "2. The primary corporate or personal B2B contact email address.\n\n"
            "Return the result ONLY as a valid, flat JSON object with these EXACT keys: 'owner', 'email'. "
            "Do not include any other text, reasoning, markdown codeblocks, or extra keys. "
            "If a field is not found, set its value to null."
        )
        
        user_prompt = f"Business Name: {biz_name}\nDomain: {domain}\n\nSearch Results:\n{snippets_text}"
        
        try:
            ai = await _get_ai_client_async()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = await ai.chat(messages, role="hawk", temperature=0.1, max_tokens=150)
            content = response.content or ""
            
            # Robust JSON extraction from brackets
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                json_str = content[start_idx:end_idx+1]
                try:
                    # Clean potential trailing commas
                    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                    data = json.loads(json_str)
                except Exception:
                    data = {}
            else:
                data = {}
            
            extracted_owner = data.get("owner")
            extracted_email = data.get("email")
            
            if extracted_owner and len(extracted_owner) > 3 and _is_plausible_name(extracted_owner):
                found_owner = extracted_owner
                logger.info(f"[HAWK AI ENRICH] Owner extracted via LLM: {found_owner}")
                
            if extracted_email and "@" in extracted_email:
                if not any(j in extracted_email.lower() for j in JUNK_EMAIL_PATTERNS):
                    found_email = extracted_email
                    logger.info(f"[HAWK AI ENRICH] Email extracted via LLM: {found_email}")
                    
        except Exception as e:
            logger.warning(f"[HAWK AI ENRICH] LLM snippet parsing failed: {e}")

    # 📝 2. Legacy Regex Fallback (Only if LLM didn't extract one of the fields)
    if not found_owner:
        for r in results["owner"]:
            text_to_check = " ".join(filter(None, [r.get("title", ""), r.get("snippet", "")]))

            for pattern in OWNER_PATTERNS:
                m = re.search(pattern, text_to_check, re.IGNORECASE)
                if m:
                    raw = m.group(1).strip()
                    name = " ".join(w.capitalize() for w in raw.split())
                    if _is_plausible_name(name) and name not in FALSE_POSITIVE_NAMES:
                        found_owner = name
                        logger.info(f"[ENRICH Fallback] Owner via regex: {found_owner}")
                        break

            if not found_owner:
                title_field = r.get("title", "")
                for sep in ["|", "–", "-", "·"]:
                    if sep in title_field:
                        parts = [p.strip() for p in title_field.split(sep)]
                        for i, part in enumerate(parts):
                            if any(kw in part.lower() for kw in TITLE_KEYWORDS):
                                for j in [i - 1, i + 1]:
                                    if 0 <= j < len(parts):
                                        candidate = parts[j]
                                        if _is_plausible_name(candidate):
                                            found_owner = candidate
                                            logger.info(f"[ENRICH Fallback] Owner via title split: {found_owner}")
                                            break
                            if found_owner:
                                break
                    if found_owner:
                        break

            if found_owner:
                break

    if not found_email:
        for r in results["email"]:
            text_to_check = " ".join(filter(None, [r.get("title", ""), r.get("snippet", "")]))
            emails = [e for e in re.findall(EMAIL_REGEX, text_to_check)
                      if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)]

            domain_match = next((e for e in emails if domain in e.lower()), None)
            if domain_match:
                found_email = domain_match
                logger.info(f"[ENRICH Fallback] Validated email: {found_email}")
                break
            elif emails:
                found_email = emails[0]
                logger.info(f"[ENRICH Fallback] Fallback email: {found_email}")
                break

    return found_owner, found_email


async def _ai_extract_contacts(text: str, biz_name: str) -> Dict[str, Optional[str]]:
    """
    Leverages our 100% free UnifiedAIClient (Gemini/Groq) to intelligently read crawled page text
    and extract: owner/CEO/founder name, corporate email, and phone number.
    Returns: {"owner": ..., "email": ..., "phone": ...}
    """
    if not text or len(text) < 100:
        return {}

    # Strip HTML tags if any to reduce token usage and save bandwidth
    soup = BeautifulSoup(text, "html.parser")
    clean_text = soup.get_text(separator=" ", strip=True)

    # Truncate text to 8000 characters to keep it snappy and light on tokens
    clean_text = clean_text[:8000]

    system_prompt = (
        "You are 'Hawk', the B2B Lead Hunter subagent. "
        "Your task is to analyze the text of a local business website and extract the contact information of the key decision-makers.\n"
        "Specifically, identify:\n"
        "1. The business owner, CEO, founder, president, or managing director's full name (2-3 words, properly capitalized, e.g., 'John Doe'). Avoid false positives like generic roles.\n"
        "2. The primary corporate or contact email address.\n"
        "3. The primary business phone number.\n\n"
        "Return the result ONLY as a valid, flat JSON object with these EXACT keys: 'owner', 'email', 'phone'. "
        "Do not include any other text, reasoning, markdown codeblocks, or extra keys. "
        "If a field is not found, set its value to null."
    )

    user_prompt = f"Business Name: {biz_name}\n\nWebsite Content:\n{clean_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        ai = await _get_ai_client_async()
        response = await ai.chat(messages, role="hawk", temperature=0.1, max_tokens=200)
        content = response.content or ""
        
        # Robust JSON extraction from brackets
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1:
            json_str = content[start_idx:end_idx+1]
            try:
                # Clean potential trailing commas
                json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
                data = json.loads(json_str)
            except Exception:
                data = {}
        else:
            data = {}

        return {
            "owner": data.get("owner") if data.get("owner") and len(data.get("owner")) > 3 else None,
            "email": data.get("email") if data.get("email") and "@" in data.get("email") else None,
            "phone": data.get("phone") if data.get("phone") else None
        }
    except Exception as e:
        logger.warning(f"[HAWK AI] LLM extraction failed: {e}")
        return {}


ENRICH_TOTAL_TIMEOUT = 25.0  # Hard ceiling below Render's 30s kill

async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead
    try:
        return await asyncio.wait_for(_enrich_lead_lite_inner(lead), timeout=ENRICH_TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"[ENRICH] Hard timeout hit for {lead.get('business')}. Returning partial data.")
        return lead

async def _enrich_lead_lite_inner(lead: Dict[str, Any]) -> Dict[str, Any]:
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    biz_name = lead.get("business", "Unknown")
    domain = _get_domain(lead.get("website") or lead.get("url") or "")
    logger.info(f"[ENRICH] ═══ Starting enrichment for: {biz_name} ═══")

    real_website = lead.get("website") or None

    # ─── STEP 1: Yelp Page Scrape ─────────────────────────────
    if "yelp.com/biz/" in url:
        if lead.get("phone") and lead.get("email") and real_website:
            logger.info("[ENRICH] Lead already fully enriched. Skipping Yelp scrape.")
        else:
            logger.info(f"[ENRICH] Step 1: Scraping Yelp page for contact info...")
            scrape_data = await asyncio.get_running_loop().run_in_executor(_firecrawl_executor, _firecrawl_scrape, url)
            markdown = scrape_data.get("markdown", "")
            html = scrape_data.get("html", "")

            if markdown:
                logger.info(f"[TELEMETRY] Firecrawl returned {len(markdown)} chars")

                if not lead.get("phone"):
                    phones = _extract_phones(markdown)
                    if phones:
                        normalized = _normalize_phone_to_e164(phones[0])
                        if normalized:
                            lead["phone"] = normalized
                            logger.info(f"[ENRICH] → Phone from Yelp: {lead['phone']}")

                # Extract website using dual HTML + Markdown parser
                if not real_website:
                    if html:
                        real_website = _extract_website_from_yelp(html)
                    if not real_website and markdown:
                        real_website = _extract_website_from_markdown(markdown)
                    if real_website:
                        lead["website"] = real_website
                        domain = _get_domain(real_website)
                        logger.info(f"[ENRICH] → Website from Yelp: {real_website}")

                addr_match = re.search(
                    r'\d+\s+[A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Way|Ln|Ct|Pl|Pkwy)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}',
                    markdown
                )
                if addr_match:
                    lead["notes"] = (lead.get("notes", "") + f" | Address: {addr_match.group(0)}").strip(" |")
            else:
                logger.warning("[ENRICH] Firecrawl returned nothing for Yelp page")
    else:
        real_website = url
        if not lead.get("website"):
            lead["website"] = url

    # ─── STEP 2: Website Crawl ────────────────────────────────
    if real_website and "yelp.com" not in real_website:
        logger.info(f"[ENRICH] Step 2: Crawling business website: {real_website}")

        pages_to_crawl = [real_website]
        
        # Intelligently discover team and contact pages from the homepage
        homepage_data = await _fetch_page(real_website)
        if homepage_data and homepage_data.get("html"):
            soup = BeautifulSoup(homepage_data["html"], "html.parser")
            domain_part = _get_domain(real_website)
            discovered_paths = set()
            
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                
                # Resolve relative links
                resolved_url = urllib.parse.urljoin(real_website, href)
                resolved_domain = _get_domain(resolved_url)
                
                # Ensure it belongs to the same business domain
                if resolved_domain != domain_part:
                    continue
                    
                path_lower = resolved_url.lower()
                # Check for B2B contact page keywords
                keywords = ["about", "team", "staff", "meet", "leader", "people", "management", "contact", "profile"]
                if any(kw in path_lower for kw in keywords):
                    discovered_paths.add(resolved_url)
            
            # Sort paths to prioritize 'team' and 'leadership'
            prioritized_paths = sorted(
                list(discovered_paths),
                key=lambda u: any(k in u.lower() for k in ["team", "leader", "staff", "people"]),
                reverse=True
            )
            
            # Add discovered pages to crawl list
            pages_to_crawl.extend(prioritized_paths[:4])
            logger.info(f"[CRAWLER] Discovered B2B pages to crawl: {pages_to_crawl}")
        else:
            # Fallback to hardcoded list if homepage fetch failed
            for path in ["/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team"]:
                pages_to_crawl.append(real_website.rstrip("/") + path)

        # Deduplicate to prevent double-crawling the same pages
        pages_to_crawl = list(dict.fromkeys(pages_to_crawl))

        # Perform high-performance concurrent page crawl using asyncio.gather with a semaphore
        async def _fetch_page_guarded(u):
            async with _crawl_semaphore:
                return await _fetch_page(u)

        crawl_tasks = [_fetch_page_guarded(u) for u in pages_to_crawl]
        pages_results = await asyncio.gather(*crawl_tasks, return_exceptions=True)

        for page_url, page_data in zip(pages_to_crawl, pages_results):
            if isinstance(page_data, Exception) or not page_data:
                continue

            html = page_data.get("html", "")
            markdown_fallback = page_data.get("markdown", "")
            content_for_extraction = html or markdown_fallback

            # Special BBB.org Profile Extractor
            if "bbb.org" in page_url:
                soup = BeautifulSoup(content_for_extraction, "html.parser")
                if not lead.get("owner"):
                    for management_header in soup.find_all(text=re.compile(r'Business Management|Key People', re.I)):
                        parent = management_header.parent
                        found_owner = False
                        for _ in range(4):
                            if not parent:
                                break
                            text_content = parent.get_text(separator=" ", strip=True)
                            names = re.findall(r'([A-Z][a-zA-Z\'-]+\s+[A-Z][a-zA-Z\'-]+)', text_content)
                            for name in names:
                                if name not in ['Business Management', 'Key People', 'About Us', 'Contact Us'] and _is_plausible_name(name):
                                    lead["owner"] = name
                                    logger.info(f"[BBB] Extracted Owner from BBB Profile: {name}")
                                    found_owner = True
                                    break
                            if found_owner:
                                break
                            parent = parent.parent
                            
                if not lead.get("phone"):
                    phones = _extract_phones(content_for_extraction)
                    if phones:
                        normalized_phone = _normalize_phone_to_e164(phones[0])
                        if normalized_phone:
                            lead["phone"] = normalized_phone
                            logger.info(f"[BBB] Phone from BBB: {lead['phone']}")
                continue

            if not lead.get("email"):
                emails = _extract_emails(content_for_extraction)
                best_email = _score_and_select_email(emails, domain)
                if best_email:
                    lead["email"] = best_email
                    logger.info(f"[ENRICH] → Email from {page_url}: {lead['email']}")

            if not lead.get("phone"):
                phones = _extract_phones(content_for_extraction)
                if phones:
                    normalized_phone = _normalize_phone_to_e164(phones[0])
                    if normalized_phone:
                        lead["phone"] = normalized_phone
                        logger.info(f"[ENRICH] → Phone from {page_url}: {lead['phone']}")

            if not lead.get("owner"):
                owner = _extract_owner_name(content_for_extraction)
                if owner and _is_plausible_name(owner):
                    lead["owner"] = owner
                    logger.info(f"[ENRICH] → Owner from {page_url}: {lead['owner']}")

            # ─── STEP 2.5: Hawk AI LLM Extraction ─────────────────────
            if not lead.get("owner") or not lead.get("email") or not lead.get("phone"):
                logger.info(f"[ENRICH] Step 2.5: Running Hawk AI LLM extraction on {page_url}...")
                ai_contacts = await _ai_extract_contacts(content_for_extraction, biz_name)
                
                if ai_contacts.get("owner") and not lead.get("owner") and _is_plausible_name(ai_contacts["owner"]):
                    lead["owner"] = ai_contacts["owner"]
                    logger.info(f"[HAWK AI] → Owner extracted: {lead['owner']}")
                
                if ai_contacts.get("email") and not lead.get("email"):
                    lead["email"] = ai_contacts["email"]
                    logger.info(f"[HAWK AI] → Email extracted: {lead['email']}")
                
                if ai_contacts.get("phone") and not lead.get("phone"):
                    normalized = _normalize_phone_to_e164(ai_contacts["phone"])
                    if normalized:
                        lead["phone"] = normalized
                        logger.info(f"[HAWK AI] → Phone extracted: {lead['phone']}")

            if lead.get("email") and lead.get("phone") and lead.get("owner"):
                break
    else:
        logger.info("[ENRICH] Step 2: No real website found. Skipping website crawl.")

    # ─── STEP 3: Hunter.io ────────────────────────────────────
    hunter_key = os.getenv("HUNTER_API_KEY")
    domain = _get_domain(real_website or url)

    if hunter_key and domain and "yelp.com" not in domain and not lead.get("email"):
        logger.info(f"[ENRICH] Step 3: Hunter.io lookup for {domain}...")
        try:
            client = await _get_shared_client()
            resp = await client.get(
                f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={hunter_key}",
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                emails = data.get("emails", [])
                if emails:
                    lead["email"] = emails[0].get("value")
                    logger.info(f"[ENRICH] → Email from Hunter: {lead['email']}")
                    
                    if not lead.get("owner") and emails[0].get("first_name"):
                        fn = emails[0].get("first_name")
                        ln = emails[0].get("last_name") or ""
                        lead["owner"] = f"{fn} {ln}".strip()
                        logger.info(f"[ENRICH] → Owner from Hunter: {lead['owner']}")
        except Exception as e:
            logger.warning(f"[ENRICH] Hunter lookup failed: {e}")

    # ─── STEP 4: Apollo.io ────────────────────────────────────
    apollo_key = os.getenv("APOLLO_API_KEY")
    if apollo_key and domain and "yelp.com" not in domain and (not lead.get("owner") or not lead.get("email")):
        logger.info(f"[ENRICH] Step 4: Apollo.io lookup for {domain}...")
        try:
            headers = {
                "Cache-Control": "no-cache",
                "Content-Type": "application/json",
                "X-Api-Key": apollo_key
            }
            payload = {
                "q_organization_domains": domain,
                "q_organization_domains_list": [domain],
                "person_titles": ["owner", "founder", "ceo", "president", "partner", "principal", "managing director", "director"],
                "page": 1,
                "per_page": 5
            }
            client = await _get_shared_client()
            resp = await client.post("https://api.apollo.io/v1/mixed_people/api_search", json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                people = resp.json().get("people", [])
                if people:
                    # Find first person with a non-empty email
                    p = next((person for person in people if person.get("email")), people[0])
                    found_fields = []
                    if not lead.get("owner") and p.get("name"):
                        lead["owner"] = p.get("name")
                        logger.info(f"[ENRICH] → Owner from Apollo: {lead['owner']}")
                        found_fields.append("owner")
                    if not lead.get("email") and p.get("email"):
                        lead["email"] = p.get("email")
                        logger.info(f"[ENRICH] → Email from Apollo: {lead['email']}")
                        found_fields.append("email")
                    if not lead.get("phone") and p.get("phone_numbers"):
                        lead["phone"] = _normalize_phone_to_e164(p.get("phone_numbers")[0].get("raw_number"))
                        logger.info(f"[ENRICH] → Phone from Apollo: {lead['phone']}")
                        found_fields.append("phone")
                    if found_fields:
                        log_skill_note(
                            "apollo_enrichment",
                            f"Apollo lookup added {', '.join(found_fields)} for {biz_name or domain}.",
                            category="lead_enrichment"
                        )
                else:
                    logger.warning(f"[ENRICH] Apollo API returned no matches for {domain}")
                    log_skill_note(
                        "apollo_enrichment",
                        f"Apollo returned no matches for {biz_name or domain}, domain={domain}.",
                        category="lead_enrichment"
                    )
            else:
                logger.warning(f"[ENRICH] Apollo API returned status {resp.status_code}: {resp.text[:200]}")
                log_skill_note(
                    "apollo_enrichment",
                    f"Apollo status {resp.status_code} for {biz_name or domain}: {resp.text[:200]}",
                    category="lead_enrichment"
                )
        except Exception as e:
            logger.warning(f"[ENRICH] Apollo failed: {e}")

    # ─── STEP 4.5: Free DuckDuckGo Snippet Search ─────────────
    if (not lead.get("owner") or not lead.get("email")) and domain and "yelp.com" not in domain:
        logger.info(f"[ENRICH] Step 4.5: DDG enrichment for {biz_name}...")
        ddg_owner, ddg_email = await _ddg_enrich_contact(biz_name, domain)
        if ddg_owner and not lead.get("owner"):
            lead["owner"] = ddg_owner
            log_skill_note(
                "ddg_enrichment",
                f"DDG enrichment found owner for {biz_name or domain}: {ddg_owner}.",
                category="lead_enrichment"
            )
        if ddg_email and not lead.get("email"):
            lead["email"] = ddg_email
            log_skill_note(
                "ddg_enrichment",
                f"DDG enrichment found email for {biz_name or domain}: {ddg_email}.",
                category="lead_enrichment"
            )

    # ─── STEP 5: Email Guess (Last Resort) ────────────────────
    if not lead.get("email") and lead.get("owner") and domain and "yelp.com" not in domain:
        owner = lead["owner"]
        parts = owner.lower().split()
        if len(parts) >= 2:
            guesses = [
                f"{parts[0]}@{domain}",
                f"{parts[0]}.{parts[-1]}@{domain}",
                f"{parts[0][0]}{parts[-1]}@{domain}",
                f"info@{domain}",
            ]
            lead["email"] = guesses[0]
            lead["notes"] = (lead.get("notes", "") + f" | Email guessed (verify before sending)").strip(" |")
            logger.info(f"[ENRICH] → Guessed email: {lead['email']}")

    # Final Phone Normalization Guardrail
    if lead.get("phone"):
        lead["phone"] = _normalize_phone_to_e164(lead["phone"])

    logger.info(
        f"[ENRICH] ═══ Done: {biz_name} | "
        f"Owner: {lead.get('owner', '—')} | "
        f"Phone: {lead.get('phone', '—')} | "
        f"Email: {lead.get('email', '—')} | "
        f"Website: {lead.get('website', '—')} ═══"
    )
    return lead


def _extract_phones(text: str) -> list:
    return re.findall(PHONE_REGEX, text)


def _validate_email_domain(email: str, business_domain: str) -> bool:
    email_domain = email.split('@')[-1].lower()
    return email_domain == business_domain or email_domain.endswith('.' + business_domain)


def _get_domain(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        domain = url.split("//")[-1].split("/")[0].replace("www.", "").lower()
        if "." in domain and len(domain) > 3:
            return domain
    except Exception:
        pass
    return None


def _firecrawl_scrape(url: str) -> Dict[str, str]:
    try:
        from firecrawl import FirecrawlApp
        key = os.getenv("FIRECRAWL_API_KEY")
        if not key:
            return {"markdown": "", "html": ""}
        app = FirecrawlApp(api_key=key)
        result = app.scrape_url(url, params={'formats': ['markdown', 'html']})
        if isinstance(result, dict):
            return {
                "markdown": result.get("markdown", result.get("content", "")),
                "html": result.get("html", "")
            }
        return {"markdown": str(result), "html": ""}
    except Exception as e:
        logger.warning(f"[ENRICH] Firecrawl scrape failed for {url}: {e}")
        return {"markdown": "", "html": ""}


def _extract_website_from_yelp(html: str) -> Optional[str]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    social = ["yelp.com", "facebook.com", "instagram.com", "twitter.com",
              "linkedin.com", "youtube.com", "tiktok.com", "google.com"]
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/biz_redir?url=' in href:
            try:
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if 'url' not in parsed_qs:
                    continue
                target_url = parsed_qs['url'][0]
                parsed = urllib.parse.urlparse(target_url)
                if any(s in target_url.lower() for s in social):
                    continue
                if any(parsed.path.lower().endswith(ext) for ext in MEDIA_EXTENSIONS):
                    continue
                if any(cdn in parsed.netloc.lower() for cdn in CDN_PATTERNS):
                    continue
                if not parsed.scheme.startswith('http'):
                    continue
                return target_url
            except Exception:
                continue
    return None


def _extract_website_from_markdown(markdown: str) -> Optional[str]:
    if not markdown:
        return None
    links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', markdown)
    social = ["yelp.com", "facebook.com", "instagram.com", "twitter.com",
              "linkedin.com", "youtube.com", "tiktok.com", "google.com", "apple.com"]
    for text, href in links:
        href_lower = href.lower()
        if "/biz_redir" in href_lower:
            try:
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                if 'url' in parsed_qs:
                    target_url = parsed_qs['url'][0]
                    if not any(s in target_url.lower() for s in social):
                        return target_url
            except Exception:
                pass
        else:
            if not any(s in href_lower for s in social):
                parsed = urllib.parse.urlparse(href)
                if not any(parsed.path.lower().endswith(ext) for ext in MEDIA_EXTENSIONS):
                    if not any(cdn in parsed.netloc.lower() for cdn in CDN_PATTERNS):
                        return href
    return None
