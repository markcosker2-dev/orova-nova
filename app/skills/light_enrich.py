import os
import re
import json
import asyncio
import httpx
import logging
import urllib.parse
from bs4 import BeautifulSoup, NavigableString
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

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
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=18.0,
                verify=False,
            ) as client:
                resp = await client.get(url)

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
            None, _firecrawl_scrape, url
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

    # 3. HTML entity decode
    entity_decoded = html.replace("&#64;", "@").replace("&#x40;", "@").replace("&commat;", "@")
    for e in re.findall(EMAIL_REGEX, entity_decoded):
        found.add(e.lower())

    # 4. data-* attributes
    for tag in soup.find_all(True):
        for attr, val in tag.attrs.items():
            if isinstance(val, str) and "email" in attr.lower():
                matches = re.findall(EMAIL_REGEX, val)
                for m in matches:
                    found.add(m.lower())

    # 5. Raw text regex
    text = soup.get_text(separator=" ")
    for e in re.findall(EMAIL_REGEX, text):
        found.add(e.lower())

    # 6. Obfuscated text patterns
    obf_patterns = [
        r'([a-zA-Z0-9._%+\-]+)\s*[\[\(]?\s*(?:at|AT)\s*[\]\)]?\s*([a-zA-Z0-9.\-]+)\s*[\[\(]?\s*(?:dot|DOT)\s*[\]\)]?\s*([a-zA-Z]{2,})',
        r'([a-zA-Z0-9._%+\-]+)\s+at\s+([a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    ]
    for pat in obf_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
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
            if name:
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

    # 3. DOM adjacency scan — FIXED
    heading_tags = soup.find_all(["h1", "h2", "h3", "h4", "p", "span", "div", "li"])
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
            if name not in FALSE_POSITIVE_NAMES:
                logger.debug(f"[OWNER] DOM adjacency hit: {name}")
                return name

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
                if _is_plausible_name(text):
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
    return True


async def _ddg_enrich_contact(biz_name: str, domain: str) -> Tuple[Optional[str], Optional[str]]:
    """DuckDuckGo snippet mining for owner name + email."""
    found_owner = None
    found_email = None

    queries = {
        "owner": [
            f'"{biz_name}" owner OR founder OR CEO',
            f'site:linkedin.com "{biz_name}" owner OR founder',
            f'"{biz_name}" "{domain}" about',
        ],
        "email": [
            f'"{biz_name}" "@{domain}"',
            f'"{biz_name}" contact email "{domain}"',
        ],
    }

    try:
        from duckduckgo_search import DDGS

        def _run_queries():
            results = {"owner": [], "email": []}
            with DDGS() as ddgs:
                for q in queries["owner"]:
                    try:
                        hits = list(ddgs.text(q, max_results=4, safesearch="moderate"))
                        results["owner"].extend(hits)
                        if len(results["owner"]) >= 8:
                            break
                    except Exception:
                        pass
                for q in queries["email"]:
                    try:
                        hits = list(ddgs.text(q, max_results=3, safesearch="moderate"))
                        results["email"].extend(hits)
                        if len(results["email"]) >= 5:
                            break
                    except Exception:
                        pass
            return results

        results = await asyncio.get_running_loop().run_in_executor(None, _run_queries)

        for r in results["owner"]:
            text_to_check = " ".join(filter(None, [
                r.get("title", ""),
                r.get("body", ""),
                r.get("snippet", ""),
            ]))

            for pattern in OWNER_PATTERNS:
                m = re.search(pattern, text_to_check, re.IGNORECASE)
                if m:
                    raw = m.group(1).strip()
                    name = " ".join(w.capitalize() for w in raw.split())
                    if _is_plausible_name(name) and name not in FALSE_POSITIVE_NAMES:
                        found_owner = name
                        logger.info(f"[DDG ENRICH] Owner via regex: {found_owner}")
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
                                            logger.info(f"[DDG ENRICH] Owner via title split: {found_owner}")
                                            break
                            if found_owner:
                                break
                    if found_owner:
                        break

            if found_owner:
                break

        for r in results["email"]:
            text_to_check = " ".join(filter(None, [
                r.get("title", ""),
                r.get("body", ""),
                r.get("snippet", ""),
            ]))
            emails = [e for e in re.findall(EMAIL_REGEX, text_to_check)
                      if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)]

            domain_match = next((e for e in emails if domain in e.lower()), None)
            if domain_match:
                found_email = domain_match
                logger.info(f"[DDG ENRICH] Validated email: {found_email}")
                break
            elif emails:
                found_email = emails[0]
                logger.info(f"[DDG ENRICH] Fallback email: {found_email}")
                break

    except Exception as e:
        logger.warning(f"[DDG ENRICH] Failed: {e}")

    return found_owner, found_email


async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    biz_name = lead.get("business", "Unknown")
    logger.info(f"[ENRICH] ═══ Starting enrichment for: {biz_name} ═══")

    real_website = lead.get("website") or None

    # ─── STEP 1: Yelp Page Scrape ─────────────────────────────
    if "yelp.com/biz/" in url:
        if lead.get("phone") and lead.get("email") and real_website:
            logger.info("[ENRICH] Lead already fully enriched. Skipping Yelp scrape.")
        else:
            logger.info(f"[ENRICH] Step 1: Scraping Yelp page for contact info...")
            scrape_data = await asyncio.get_running_loop().run_in_executor(None, _firecrawl_scrape, url)
            markdown = scrape_data.get("markdown", "")
            html = scrape_data.get("html", "")

            if markdown:
                logger.info(f"[TELEMETRY] Firecrawl returned {len(markdown)} chars")

                if not lead.get("phone"):
                    phones = _extract_phones(markdown)
                    if phones:
                        lead["phone"] = phones[0]
                        logger.info(f"[ENRICH] → Phone from Yelp: {lead['phone']}")

                # Extract website using dual HTML + Markdown parser
                if not real_website:
                    if html:
                        real_website = _extract_website_from_yelp(html)
                    if not real_website and markdown:
                        real_website = _extract_website_from_markdown(markdown)
                    if real_website:
                        lead["website"] = real_website
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
        lead["website"] = url

    # ─── STEP 2: Website Crawl ────────────────────────────────
    if real_website and "yelp.com" not in real_website:
        logger.info(f"[ENRICH] Step 2: Crawling business website: {real_website}")

        pages_to_crawl = [real_website]
        for path in ["/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team"]:
            pages_to_crawl.append(real_website.rstrip("/") + path)

        for page_url in pages_to_crawl:
            page_data = await _fetch_page(page_url)
            if not page_data:
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
                                if name not in ['Business Management', 'Key People', 'About Us', 'Contact Us']:
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
                        lead["phone"] = phones[0]
                        logger.info(f"[BBB] Phone from BBB: {lead['phone']}")
                continue

            if not lead.get("email"):
                emails = _extract_emails(content_for_extraction)
                if emails:
                    lead["email"] = emails[0]
                    logger.info(f"[ENRICH] → Email from {page_url}: {lead['email']}")

            if not lead.get("phone"):
                phones = _extract_phones(content_for_extraction)
                if phones:
                    lead["phone"] = phones[0]
                    logger.info(f"[ENRICH] → Phone from {page_url}: {lead['phone']}")

            if not lead.get("owner"):
                owner = _extract_owner_name(content_for_extraction)
                if owner:
                    lead["owner"] = owner
                    logger.info(f"[ENRICH] → Owner from {page_url}: {lead['owner']}")

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
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={hunter_key}"
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
                "x-api-key": apollo_key
            }
            payload = {
                "q_organization_domains": domain,
                "person_titles": ["owner", "founder", "ceo", "president", "partner", "principal"],
                "page": 1,
                "per_page": 3
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post("https://api.apollo.io/v1/mixed_people/search", json=payload, headers=headers)
                if resp.status_code == 200:
                    people = resp.json().get("people", [])
                    if people:
                        p = people[0]
                        if not lead.get("owner"):
                            lead["owner"] = p.get("name")
                            logger.info(f"[ENRICH] → Owner from Apollo: {lead['owner']}")
                        if not lead.get("email") and p.get("email"):
                            lead["email"] = p.get("email")
                            logger.info(f"[ENRICH] → Email from Apollo: {lead['email']}")
        except Exception as e:
            logger.warning(f"[ENRICH] Apollo failed: {e}")

    # ─── STEP 4.5: Free DuckDuckGo Snippet Search ─────────────
    if (not lead.get("owner") or not lead.get("email")) and domain and "yelp.com" not in domain:
        logger.info(f"[ENRICH] Step 4.5: DDG enrichment for {biz_name}...")
        ddg_owner, ddg_email = await _ddg_enrich_contact(biz_name, domain)
        if ddg_owner and not lead.get("owner"):
            lead["owner"] = ddg_owner
        if ddg_email and not lead.get("email"):
            lead["email"] = ddg_email

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
