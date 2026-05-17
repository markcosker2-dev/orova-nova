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

OWNER_PATTERNS = [
    # "Owner: John Doe" or "CEO John Doe"
    r'(?:owner|founder|ceo|president|principal|operator)[:\s,\-]+([A-Z][a-zA-Z\'-]+(?:\s+[A-Z][a-zA-Z\'-]+){1,2})',
    # "John Doe, Owner" or "John Doe - Founder"
    r'([A-Z][a-zA-Z\'-]+(?:\s+[A-Z][a-zA-Z\'-]+){1,2})[,\s\-–]+(?:owner|founder|ceo|president|principal|operator)',
    # "I'm John Doe, owner" / "I am Jane Smith, founder"
    r"I(?:'m| am)\s+([A-Z][a-zA-Z\'-]+\s+[A-Z][a-zA-Z\'-]+),?\s*(?:owner|founder|ceo)",
    # "Founded by John Doe"
    r'(?:founded|owned|run|operated)\s+by\s+([A-Z][a-zA-Z\'-]+\s+[A-Z][a-zA-Z\'-]+)',
]

BLOCK_SIGNALS = [
    "cf-browser-verification", "challenge-form", 
    "checking your browser", "enable javascript",
    "ddos-guard", "just a moment"
]

def _is_blocked(html: str) -> bool:
    lower = html.lower()
    return any(signal in lower for signal in BLOCK_SIGNALS)

async def _fetch_page(url: str) -> Optional[str]:
    """Fetch a page's HTML. Try fast HTTPX first; if it looks blank or has Cloudflare, fallback to Firecrawl's cloud JS-renderer."""
    # 1. Try fast local HTTPX fetch
    html = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                html = resp.text
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(f"[ENRICH] HTTPX fetch failed for {url}: {e}")

    # 2. Check if content looks empty or blocked by Cloudflare
    if html and len(html) > 5000 and not _is_blocked(html):
        return html

    # 3. Fallback to Cloud Firecrawl JS-rendering (bypasses Render dependency limitations)
    try:
        logger.info(f"[ENRICH] Local HTTPX blank or blocked by CF for {url}. Falling back to cloud Firecrawl JS rendering...")
        scrape_data = await asyncio.get_running_loop().run_in_executor(None, _firecrawl_scrape, url)
        fc_html = scrape_data.get("html") or scrape_data.get("markdown")
        if fc_html and len(fc_html) > 100 and not _is_blocked(fc_html):
            return fc_html
    except Exception as e:
        logger.warning(f"[ENRICH] Firecrawl fallback failed for {url}: {e}")

    return html  # Return the original html as a last resort

def _extract_emails(html: str) -> list:
    """Extract valid emails from HTML: checks mailto links, raw text regex, and obfuscations."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    found = set()
    
    # 1. mailto: href attributes — most reliable
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email:
                found.add(email)
    
    # 2. Raw text regex
    text = soup.get_text(separator=" ")
    for e in re.findall(EMAIL_REGEX, text):
        found.add(e)
    
    # 3. Obfuscated: "user [at] domain [dot] com"
    obfuscated = re.findall(
        r'([a-zA-Z0-9._%+-]+)\s*[\[\(]?at[\]\)]?\s*([a-zA-Z0-9.-]+)\s*[\[\(]?dot[\]\)]?\s*([a-zA-Z]{2,})',
        text, re.IGNORECASE
    )
    for u, d, tld in obfuscated:
        found.add(f"{u}@{d}.{tld}")
    
    return [
        e for e in found
        if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)
    ]

def _extract_phones(text: str) -> list:
    """Extract US phone numbers from text."""
    return re.findall(PHONE_REGEX, text)

def _extract_owner_name(html: str) -> Optional[str]:
    """Try to find owner/founder/CEO name from HTML structure and text patterns."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    
    # Strategy 1: Name in one tag, title in adjacent sibling/child
    for tag in soup.find_all(['h1','h2','h3','h4','p','span','div']):
        text = tag.get_text(strip=True)
        next_text = ""
        sibling = tag.find_next_sibling()
        if sibling:
            next_text = sibling.get_text(strip=True).lower()
        child = tag.find()
        if child:
            next_text += " " + child.get_text(strip=True).lower()
        
        if any(title in next_text for title in ['owner','founder','ceo','president','principal']):
            name_match = re.match(r'^([A-Z][a-zA-Z\'-]+(?:\s+[A-Z][a-zA-Z\'-]+){1,2})$', text)
            if name_match:
                parts = name_match.group(1).split()
                if len(parts) >= 2:
                    return name_match.group(1)
    
    # Strategy 2: Regex on full text
    full_text = soup.get_text(separator=" ", strip=True)
    for pattern in OWNER_PATTERNS:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            parts = name.split()
            FALSE_POSITIVES = {'About Us','Contact Us','Read More','Learn More','Our Team','Get Started','Meet Our','Our Story'}
            if len(parts) >= 2 and name not in FALSE_POSITIVES:
                return name
    return None


import urllib.parse

MEDIA_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.ico', '.pdf', '.mp4'}
CDN_PATTERNS = ['cloudinary', 'cloudfront', 'amazonaws', 'akamai', 'imgix', 'twimg', 'fbcdn', 'yelpcdn.com']

def _extract_website_from_yelp(html: str) -> Optional[str]:
    """Extract the real business website URL from Yelp HTML via /biz_redir links."""
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
                
                # Reject social, media, CDN
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

def _extract_owner_from_text(text: str) -> Optional[str]:
    """Try to find owner/founder/CEO name from plain text without BeautifulSoup."""
    for pattern in OWNER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            parts = name.split()
            if len(parts) == 2 and all(p[0].isupper() for p in parts):
                false_positives = ['About Us', 'Contact Us', 'Read More', 'Learn More', 'Our Team', 'Get Started']
                if name not in false_positives:
                    return name
    return None

def _validate_email_domain(email: str, business_domain: str) -> bool:
    """Validate that the extracted email domain matches or is a subdomain of the business domain."""
    email_domain = email.split('@')[-1].lower()
    return email_domain == business_domain or email_domain.endswith('.' + business_domain)


def _firecrawl_scrape(url: str) -> Dict[str, str]:
    """Use Firecrawl to scrape a page. Returns markdown and html."""
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
        return {"markdown": str(result), "html": str(result)}
    except Exception as e:
        logger.warning(f"[ENRICH] Firecrawl scrape failed for {url}: {e}")
        return {"markdown": "", "html": ""}


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
            scrape_data = await asyncio.get_running_loop().run_in_executor(None, _firecrawl_scrape, url)
            markdown = scrape_data.get("markdown", "")
            html = scrape_data.get("html", "")

            if markdown:
                logger.info(f"[TELEMETRY] Firecrawl returned {len(markdown)} chars")

                # Extract phone
                if not lead.get("phone"):
                    phones = _extract_phones(markdown)
                    if phones:
                        lead["phone"] = phones[0]
                        logger.info(f"[ENRICH] → Phone from Yelp: {lead['phone']}")

                # Extract real website
                if not real_website and html:
                    real_website = _extract_website_from_yelp(html)
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
                    
            owner_res, email_res = await asyncio.get_running_loop().run_in_executor(None, _ddg_enrich)
            
            # Parse Owner using the optimized plain-text matcher
            if not lead.get("owner"):
                for r in owner_res:
                    snippet = r.get("body", "")
                    title = r.get("title", "")
                    text_to_check = title + " " + snippet
                    owner = _extract_owner_from_text(text_to_check)
                    if owner:
                        lead["owner"] = owner
                        logger.info(f"[ENRICH] → DDG Found Owner: {owner}")
                        break

            # Parse Email with domain validation protection
            if not lead.get("email"):
                for r in email_res:
                    snippet = r.get("body", "")
                    title = r.get("title", "")
                    text_to_check = title + " " + snippet
                    emails = _extract_emails(text_to_check)
                    
                    # Try to find a domain-validated email first
                    validated_email = None
                    for email in emails:
                        if _validate_email_domain(email, domain):
                            validated_email = email
                            break
                            
                    if validated_email:
                        lead["email"] = validated_email
                        logger.info(f"[ENRICH] → DDG Found Validated Email: {lead['email']}")
                        break
                    elif emails:
                        # Fallback: accept the first email if no domain matches
                        lead["email"] = emails[0]
                        logger.info(f"[ENRICH] → DDG Found Email (fallback): {lead['email']}")
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
