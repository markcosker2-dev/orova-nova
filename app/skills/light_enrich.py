import os
import re
import asyncio
import httpx
import logging
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT ENGINE V3 — Find the HUMAN behind the business
# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline:
#   1. Yelp Page Scrape (if Yelp URL) → phone, real website
#   2. Website Crawl → email, phone, owner name from /contact, /about, /team
#   3. Hunter.io → verified emails by domain (free: 25/mo)
#   4. Apollo.io → decision-maker name, title, verified email
#   5. Email Guess → first@domain.com, info@domain.com

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_REGEX = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
JUNK_EMAIL_PATTERNS = [
    'example', 'png', 'jpg', 'gif', 'sentry', 'webpack', 'wixpress',
    'noreply', 'test@', 'email@', 'your@', 'name@', 'user@', 'admin@',
    'support@', 'no-reply', '.svg', '.webp', '.css', '.js'
]

# Common owner/founder title patterns to find on websites
OWNER_PATTERNS = [
    r'(?:owner|founder|ceo|president|principal|director|managing\s+partner)[:\s]*([A-Z][a-z]+\s+[A-Z][a-z]+)',
    r'([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]*(?:owner|founder|ceo|president|principal)',
    r'(?:meet|about)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
]


async def _fetch_page(url: str) -> Optional[str]:
    """Fetch a page's HTML with proper headers."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        logger.warning(f"[ENRICH] Failed to fetch {url}: {e}")
    return None


def _extract_emails(text: str) -> list:
    """Extract valid emails from text, filtering out junk."""
    emails = re.findall(EMAIL_REGEX, text)
    return [e for e in emails if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)]


def _extract_phones(text: str) -> list:
    """Extract US phone numbers from text."""
    return re.findall(PHONE_REGEX, text)


def _extract_owner_name(html: str) -> Optional[str]:
    """Try to find owner/founder/CEO name from HTML text."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    for pattern in OWNER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Validate: must be 2 words, both capitalized, no junk
            parts = name.split()
            if len(parts) == 2 and all(p[0].isupper() for p in parts):
                # Filter out common false positives
                false_positives = ['About Us', 'Contact Us', 'Read More', 'Learn More', 'Our Team', 'Get Started']
                if name not in false_positives:
                    return name
    return None


def _extract_website_from_yelp(markdown: str) -> Optional[str]:
    """Extract the real business website URL from Yelp page markdown."""
    social = ["yelp.com", "facebook.com", "instagram.com", "twitter.com",
              "linkedin.com", "youtube.com", "tiktok.com", "google.com",
              "yelpcdn.com", ".jpg", ".jpeg", ".png", ".gif", ".svg", "schema.org", "w3.org"]

    # Method 1: Look for explicit website label
    patterns = [
        r'(?:Business website|Website|business\.website)[:\s]*\[?([^\]\s\)]+)',
        r'(?:website|web\s*site)[:\s]*(https?://[^\s\)\]]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, markdown, re.IGNORECASE)
        if match:
            url = match.group(1).rstrip('.,;:)')
            if not any(s in url.lower() for s in social):
                return url

    # Method 2: Find non-social URLs in the content
    urls = re.findall(r'https?://[^\s\)\]\"\'\<\>]+', markdown)
    for u in urls:
        u_clean = u.rstrip('.,;:)')
        if not any(s in u_clean.lower() for s in social):
            return u_clean

    return None


def _firecrawl_scrape(url: str) -> Optional[str]:
    """Use Firecrawl to scrape a page (renders JavaScript). Returns markdown."""
    try:
        from firecrawl import FirecrawlApp
        key = os.getenv("FIRECRAWL_API_KEY")
        if not key:
            return None
        app = FirecrawlApp(api_key=key)
        result = app.scrape_url(url, params={'formats': ['markdown']})

        # Handle different response formats
        if isinstance(result, dict):
            return result.get("markdown", result.get("content", str(result)))
        elif isinstance(result, str):
            return result
        return str(result)
    except Exception as e:
        logger.warning(f"[ENRICH] Firecrawl scrape failed for {url}: {e}")
        return None


async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    4-step enrichment cascade:
    1. Yelp Page Scrape → phone, real website URL
    2. Website Crawl → email, phone, owner name
    3. Hunter.io → verified emails by domain
    4. Apollo.io → decision-maker name + verified email
    """
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    biz_name = lead.get("business", "Unknown")
    logger.info(f"[ENRICH] ═══ Starting enrichment for: {biz_name} ═══")

    real_website = lead.get("website") or None

    # ─── STEP 1: Yelp Page Scrape ─────────────────────────────
    if "yelp.com/biz/" in url:
        # Skip if we already have phone + email + website
        if lead.get("phone") and lead.get("email") and real_website:
            logger.info("[ENRICH] Lead already fully enriched. Skipping Yelp scrape.")
        else:
            logger.info(f"[ENRICH] Step 1: Scraping Yelp page for contact info...")
            markdown = await asyncio.get_event_loop().run_in_executor(None, _firecrawl_scrape, url)

            if markdown:
                logger.info(f"[TELEMETRY] Firecrawl returned {len(markdown)} chars")

                # Extract phone
                if not lead.get("phone"):
                    phones = _extract_phones(markdown)
                    if phones:
                        lead["phone"] = phones[0]
                        logger.info(f"[ENRICH] → Phone from Yelp: {lead['phone']}")

                # Extract real website
                if not real_website:
                    real_website = _extract_website_from_yelp(markdown)
                    if real_website:
                        lead["website"] = real_website
                        logger.info(f"[ENRICH] → Website from Yelp: {real_website}")

                # Extract address
                addr_match = re.search(
                    r'\d+\s+[A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Way|Ln|Ct|Pl|Pkwy)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}',
                    markdown
                )
                if addr_match:
                    lead["notes"] = (lead.get("notes", "") + f" | Address: {addr_match.group(0)}").strip(" |")
            else:
                logger.warning("[ENRICH] Firecrawl returned nothing for Yelp page")
    else:
        # Non-Yelp URL — the URL itself IS the business website
        real_website = url
        lead["website"] = url

    # ─── STEP 2: Website Crawl ────────────────────────────────
    if real_website and "yelp.com" not in real_website:
        logger.info(f"[ENRICH] Step 2: Crawling business website: {real_website}")

        # Crawl homepage + key pages
        pages_to_crawl = [real_website]
        for path in ["/contact", "/contact-us", "/about", "/about-us", "/team", "/our-team"]:
            pages_to_crawl.append(real_website.rstrip("/") + path)

        for page_url in pages_to_crawl:
            html = await _fetch_page(page_url)
            if not html:
                continue

            # Extract email
            if not lead.get("email"):
                emails = _extract_emails(html)
                if emails:
                    lead["email"] = emails[0]
                    logger.info(f"[ENRICH] → Email from {page_url}: {lead['email']}")

            # Extract phone
            if not lead.get("phone"):
                phones = _extract_phones(html)
                if phones:
                    lead["phone"] = phones[0]
                    logger.info(f"[ENRICH] → Phone from {page_url}: {lead['phone']}")

            # Extract owner name
            if not lead.get("owner"):
                owner = _extract_owner_name(html)
                if owner:
                    lead["owner"] = owner
                    logger.info(f"[ENRICH] → Owner from {page_url}: {lead['owner']}")

            # If we found everything, stop crawling
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
                    hunter_emails = data.get("emails", [])
                    if hunter_emails:
                        # Find the best email (owner/founder/CEO preferred)
                        best_email = None
                        for he in hunter_emails:
                            position = (he.get("position") or "").lower()
                            if any(t in position for t in ["owner", "founder", "ceo", "president", "director"]):
                                best_email = he
                                break
                        if not best_email:
                            best_email = hunter_emails[0]

                        lead["email"] = best_email.get("value", "")
                        if best_email.get("first_name") and best_email.get("last_name"):
                            owner_name = f"{best_email['first_name']} {best_email['last_name']}"
                            if not lead.get("owner"):
                                lead["owner"] = owner_name
                        logger.info(f"[ENRICH] → Hunter.io: {lead.get('owner', 'N/A')} ({lead['email']})")
        except Exception as e:
            logger.warning(f"[ENRICH] Hunter.io failed: {e}")

    # ─── STEP 4: Apollo.io ────────────────────────────────────
    apollo_key = os.getenv("APOLLO_API_KEY")
    if apollo_key and domain and "yelp.com" not in domain:
        # Only call Apollo if we're still missing owner or email
        if not lead.get("owner") or not lead.get("email"):
            logger.info(f"[ENRICH] Step 4: Apollo lookup for {domain}...")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Use people/search to find decision-makers at this company
                    payload = {
                        "api_key": apollo_key,
                        "q_organization_domains": domain,
                        "person_titles": ["owner", "founder", "ceo", "president", "managing director"],
                        "page": 1,
                        "per_page": 1
                    }
                    resp = await client.post(
                        "https://api.apollo.io/v1/mixed_people/search",
                        json=payload
                    )
                    if resp.status_code == 200:
                        people = resp.json().get("people", [])
                        if people:
                            person = people[0]
                            name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                            if name and not lead.get("owner"):
                                lead["owner"] = name
                            if person.get("email") and not lead.get("email"):
                                lead["email"] = person["email"]
                            if person.get("phone_numbers"):
                                phones = person["phone_numbers"]
                                if phones and not lead.get("phone"):
                                    lead["phone"] = phones[0].get("sanitized_number", phones[0].get("raw_number", ""))
                            lead["notes"] = (lead.get("notes", "") + f" | Title: {person.get('title', 'N/A')} | LinkedIn: {person.get('linkedin_url', 'N/A')}").strip(" |")
                            logger.info(f"[ENRICH] → Apollo: {lead.get('owner')} ({lead.get('email')})")
            except Exception as e:
                logger.warning(f"[ENRICH] Apollo failed: {e}")

    # ─── STEP 4.5: Free DuckDuckGo Snippet Search ─────────────
    if (not lead.get("owner") or not lead.get("email")) and domain and "yelp.com" not in domain:
        logger.info(f"[ENRICH] Step 4.5: Free DDG search for {biz_name} contact info...")
        try:
            from duckduckgo_search import DDGS
            def _ddg_enrich():
                with DDGS() as ddgs:
                    # Search for owner/founder
                    owner_query = f'"{biz_name}" ("owner" OR "founder" OR "ceo")'
                    owner_results = list(ddgs.text(owner_query, max_results=3))
                    
                    # Search for email
                    email_query = f'"{biz_name}" "{domain}" "@" email contact'
                    email_results = list(ddgs.text(email_query, max_results=3))
                    
                    return owner_results, email_results
                    
            owner_res, email_res = await asyncio.get_event_loop().run_in_executor(None, _ddg_enrich)
            
            # Parse Owner
            if not lead.get("owner"):
                for r in owner_res:
                    snippet = r.get("body", "")
                    title = r.get("title", "")
                    text_to_check = title + " " + snippet
                    owner = _extract_owner_name(text_to_check)
                    if owner:
                        lead["owner"] = owner
                        logger.info(f"[ENRICH] → DDG Found Owner: {owner}")
                        break

            # Parse Email
            if not lead.get("email"):
                for r in email_res:
                    snippet = r.get("body", "")
                    title = r.get("title", "")
                    text_to_check = title + " " + snippet
                    emails = _extract_emails(text_to_check)
                    if emails:
                        lead["email"] = emails[0]
                        logger.info(f"[ENRICH] → DDG Found Email: {lead['email']}")
                        break
        except Exception as e:
            logger.warning(f"[ENRICH] DDG free enrichment failed: {e}")

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
            lead["email"] = guesses[0]  # Most common format
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


def _get_domain(url: str) -> Optional[str]:
    """Extract clean domain from a URL."""
    if not url:
        return None
    try:
        domain = url.split("//")[-1].split("/")[0].replace("www.", "").lower()
        if "." in domain and len(domain) > 3:
            return domain
    except Exception:
        pass
    return None
