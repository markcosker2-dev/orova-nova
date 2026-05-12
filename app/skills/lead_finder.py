"""
app/skills/lead_finder.py
HAWK's lead discovery engine — 3-tier fallback.

TIER 1: DDGS (duckduckgo-search library) — no bot detection, fastest
TIER 2: Scrapling StealthyFetcher — if DDGS rate-limited
TIER 3: Playwright headless — last resort with full stealth args

Each tier extracts: title, url, snippet.
Contact extraction (email + phone) runs via scrape_contact_info on the URL.
"""

import re
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set, Tuple

logger = logging.getLogger("orova.hawk")

# Search deduplication & memory
SEARCH_HISTORY: Dict[str, datetime] = {}
SEARCH_EXPIRY_HOURS = 24

# ── Contact extraction constants ──────────────────────────────────────────
EMAIL_RE   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE   = re.compile(r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
EMAIL_BLACKLIST = {
    "example.com", "domain.com", "wixpress.com", "squarespace.com",
    "shopify.com", "wordpress.com", "noreply.com", "sentry.io",
}
CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us"]
BROWSER_ARGS  = [
    "--no-sandbox", "--disable-setuid-sandbox",
    "--disable-dev-shm-usage", "--disable-gpu",
    "--window-size=1920,1080",
]


# ══════════════════════════════════════════════════════════════════════════════
# TIER 1 — DDGS (primary, no bot detection)
# ══════════════════════════════════════════════════════════════════════════════

def _ddgs_search(query: str, count: int = 10) -> List[Dict]:
    """DuckDuckGo via library — handles rate limiting automatically."""
    for attempt in range(3):
        try:
            from duckduckgo_search import DDGS
            results = list(DDGS().text(query, max_results=count))
            logger.info(f"[HAWK/DDGS] {len(results)} results for '{query}'")
            return results
        except Exception as e:
            err = str(e).lower()
            if "ratelimit" in err or "202" in err:
                wait = (attempt + 1) * 12
                logger.warning(f"[HAWK/DDGS] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"[HAWK/DDGS] Attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    return []
                time.sleep(4)
    return []


# ══════════════════════════════════════════════════════════════════════════════
# TIER 2 — Scrapling StealthyFetcher
# ══════════════════════════════════════════════════════════════════════════════

def _scrapling_search(query: str, count: int = 10) -> List[Dict]:
    """Scrapling with stealth — bypasses most bot detection."""
    try:
        from scrapling import StealthyFetcher
        encoded = query.replace(" ", "+")
        url     = f"https://html.duckduckgo.com/html/?q={encoded}"
        fetcher = StealthyFetcher()
        page    = fetcher.fetch(url)
        results = []
        for result in page.css(".result")[:count]:
            try:
                title   = result.css_first(".result__title")
                link    = result.css_first(".result__url")
                snippet = result.css_first(".result__snippet")
                if title and link:
                    results.append({
                        "title": title.text,
                        "href":  "https://" + link.text.strip() if not link.text.startswith("http") else link.text.strip(),
                        "body":  snippet.text if snippet else "",
                    })
            except Exception:
                continue
        logger.info(f"[HAWK/SCRAPLING] {len(results)} results for '{query}'")
        return results
    except Exception as e:
        logger.error(f"[HAWK/SCRAPLING] Failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# TIER 3 — Playwright (last resort)
# ══════════════════════════════════════════════════════════════════════════════

async def _playwright_search(query: str, count: int = 10) -> List[Dict]:
    """Full headless browser — slowest but most capable."""
    results = []
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
            ctx     = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await ctx.new_page()

            # DuckDuckGo HTML version — less bot detection than main site
            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")

            # Try multiple selectors for resilience
            for selector in [".result", ".links_main", ".web-result"]:
                items = await page.query_selector_all(selector)
                if items:
                    for item in items[:count]:
                        try:
                            title_el   = await item.query_selector(".result__title, .result__a, a")
                            snippet_el = await item.query_selector(".result__snippet, .result__body")
                            url_el     = await item.query_selector("a")
                            if title_el:
                                title = await title_el.inner_text()
                                href  = await url_el.get_attribute("href") if url_el else ""
                                snip  = await snippet_el.inner_text() if snippet_el else ""
                                if href and href.startswith("http"):
                                    results.append({
                                        "title": title.strip(),
                                        "href":  href,
                                        "body":  snip.strip(),
                                    })
                        except Exception:
                            continue
                    break

            await browser.close()
        logger.info(f"[HAWK/PLAYWRIGHT] {len(results)} results for '{query}'")
    except Exception as e:
        logger.error(f"[HAWK/PLAYWRIGHT] Failed: {e}")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# CONTACT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def scrape_contact_info(url: str) -> Dict[str, Optional[str]]:
    """Extract email and phone from a URL. Tries main page + /contact."""
    import requests
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
    }
    if not url or not url.startswith("http"):
        return {"email": None, "phone": None}

    pages       = [url] + [url.rstrip("/") + p for p in CONTACT_PATHS[:2]]
    all_emails: List[str] = []
    all_phones: List[str] = []

    for page_url in pages:
        try:
            from bs4 import BeautifulSoup
            resp = requests.get(page_url, timeout=10, headers=headers, allow_redirects=True)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            # mailto: links first
            for a in soup.find_all("a", href=True):
                if a["href"].lower().startswith("mailto:"):
                    e = a["href"][7:].split("?")[0].strip().lower()
                    if "@" in e:
                        all_emails.append(e)
                elif a["href"].lower().startswith("tel:"):
                    p = re.sub(r"[^\d+\-\s()]", "", a["href"][4:]).strip()
                    if len(re.sub(r"\D", "", p)) >= 10:
                        all_phones.append(p)

            text = soup.get_text(separator=" ", strip=True)
            all_emails.extend(EMAIL_RE.findall(text))
            for m in PHONE_RE.findall(text):
                raw = "".join(m).strip()
                if len(re.sub(r"\D", "", raw)) >= 10:
                    all_phones.append(raw)

            if all_emails:
                break
        except Exception:
            continue

    return {
        "email": _best_email(all_emails),
        "phone": _best_phone(all_phones),
    }


def _best_email(emails: List[str]) -> Optional[str]:
    priority = ["info@", "contact@", "hello@", "sales@", "office@"]
    seen, clean = set(), []
    for e in emails:
        e = e.lower().strip()
        domain = e.split("@")[-1] if "@" in e else ""
        if domain in EMAIL_BLACKLIST or e in seen:
            continue
        if any(e.endswith(x) for x in [".png", ".jpg", ".gif", ".svg", ".pdf"]):
            continue
        seen.add(e)
        clean.append(e)
    if not clean:
        return None
    for prefix in priority:
        for e in clean:
            if e.startswith(prefix):
                return e
    return clean[0]


def _best_phone(phones: List[str]) -> Optional[str]:
    seen_digits, clean = set(), []
    for p in phones:
        digits = re.sub(r"\D", "", p)
        if len(digits) >= 10 and digits not in seen_digits:
            seen_digits.add(digits)
            clean.append(p.strip())
    if not clean:
        return None
    clean.sort(key=lambda x: len(re.sub(r"\D", "", x)), reverse=True)
    return clean[0]


# ══════════════════════════════════════════════════════════════════════════════
# LEAD VALIDATION & ENRICHMENT
# ══════════════════════════════════════════════════════════════════════════════

async def validate_and_enrich_lead(lead: Dict, max_retries: int = 2) -> Dict:
    """
    QUALIFICATION GATE: Before a lead enters outreach pipeline, it MUST have:
    1. A verified email (not generic/blacklisted)
    2. A phone number (preferred) OR LinkedIn URL

    If missing, attempts secondary search on free sources.
    """
    lead["qualified"] = False
    lead["enrichment_source"] = "initial_scrape"
    lead["validation_attempts"] = 0

    has_email = bool(lead.get("email") and "@" in lead.get("email", ""))
    has_phone = bool(lead.get("phone") and len(re.sub(r"\D", "", lead.get("phone", ""))) >= 7)
    has_linkedin = bool(lead.get("linkedin"))

    if has_email and (has_phone or has_linkedin):
        lead["qualified"] = True
        lead["qualification_score"] = 90
        return lead

    url = lead.get("url", "")
    title = lead.get("title", "")

    for attempt in range(max_retries):
        lead["validation_attempts"] = attempt + 1

        if not has_email or not has_phone:
            contact = _deep_contact_scrape(url, title)
            if contact.get("email") and not lead.get("email"):
                lead["email"] = contact["email"]
                lead["enrichment_source"] = "deep_contact_scrape"
                has_email = True
            if contact.get("phone") and not lead.get("phone"):
                lead["phone"] = contact["phone"]
                has_phone = True
            if contact.get("linkedin") and not lead.get("linkedin"):
                lead["linkedin"] = contact["linkedin"]
                has_linkedin = True

        if not has_linkedin and title:
            linkedin_url = _find_linkedin_company(title)
            if linkedin_url:
                lead["linkedin"] = linkedin_url
                lead["enrichment_source"] = "linkedin_search"
                has_linkedin = True

        if not has_email and title:
            ddg_email = _ddgs_email_search(title, url)
            if ddg_email:
                lead["email"] = ddg_email
                lead["enrichment_source"] = "ddgs_email_search"
                has_email = True

        if has_email and (has_phone or has_linkedin):
            lead["qualified"] = True
            lead["qualification_score"] = 75 + (10 if has_phone else 0) + (5 if has_linkedin else 0)
            return lead

    if has_email:
        lead["qualified"] = True
        lead["qualification_score"] = 60
        lead["enrichment_source"] = "email_only"
        return lead

    lead["qualification_score"] = 0
    lead["qualification_reason"] = "No verified email or phone found after enrichment"
    return lead


def _deep_contact_scrape(url: str, company_name: str = "") -> Dict:
    """Aggressive contact extraction — tries additional paths."""
    extended_paths = [
        "/contact", "/contact-us", "/about", "/about-us",
        "/team", "/our-team", "/staff", "/people",
        "/imprint", "/legal", "/privacy", "/terms",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    }
    if not url or not url.startswith("http"):
        return {}
    pages = [url] + [url.rstrip("/") + p for p in extended_paths]
    all_emails: List[str] = []
    all_phones: List[str] = []
    linkedin_url = None
    for page_url in pages:
        try:
            import requests
            from bs4 import BeautifulSoup
            resp = requests.get(page_url, timeout=8, headers=headers, allow_redirects=True)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].lower()
                if href.startswith("mailto:"):
                    e = a["href"][7:].split("?")[0].strip().lower()
                    if "@" in e and not any(b in e for b in EMAIL_BLACKLIST):
                        all_emails.append(e)
                elif href.startswith("tel:"):
                    p = re.sub(r"[^\d+\-\s()]", "", a["href"][4:]).strip()
                    if len(re.sub(r"\D", "", p)) >= 7:
                        all_phones.append(p)
                elif "linkedin.com/company" in href or "linkedin.com/in" in href:
                    linkedin_url = a["href"]
            text = soup.get_text(separator=" ", strip=True)
            all_emails.extend(EMAIL_RE.findall(text))
            for m in PHONE_RE.findall(text):
                raw = "".join(m).strip()
                if len(re.sub(r"\D", "", raw)) >= 7:
                    all_phones.append(raw)
            og_url = soup.find("meta", property="og:url")
            if og_url and "linkedin.com" in og_url.get("content", ""):
                linkedin_url = og_url["content"]
            if all_emails and linkedin_url:
                break
        except Exception:
            continue
    return {
        "email": _best_email(all_emails),
        "phone": _best_phone(all_phones),
        "linkedin": linkedin_url,
    }


def _find_linkedin_company(company_name: str) -> Optional[str]:
    """Search DuckDuckGo for company LinkedIn page."""
    try:
        from duckduckgo_search import DDGS
        query = f"{company_name} site:linkedin.com/company"
        results = list(DDGS().text(query, max_results=3))
        for r in results:
            href = r.get("href", r.get("url", ""))
            if "linkedin.com/company" in href:
                return href
    except Exception:
        pass
    return None


def _ddgs_email_search(company_name: str, company_url: str = "") -> Optional[str]:
    """Search DuckDuckGo specifically for company email addresses."""
    try:
        from duckduckgo_search import DDGS
        queries = [
            f"{company_name} email contact",
            f"{company_name} @email",
            f"{company_name} contact us email",
        ]
        for q in queries:
            results = list(DDGS().text(q, max_results=5))
            for r in results:
                body = r.get("body", "") + " " + r.get("href", "")
                emails = EMAIL_RE.findall(body)
                for e in emails:
                    e = e.lower().strip()
                    domain = e.split("@")[-1] if "@" in e else ""
                    if domain not in EMAIL_BLACKLIST and not e.endswith((".png", ".jpg")):
                        return e
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT — Called by Router and Scheduler
# ══════════════════════════════════════════════════════════════════════════════

async def find_leads(count: int = 10, query: str = "luxury home renovation") -> dict:
    """
    HAWK's primary lead discovery function.
    3-tier fallback: DDGS → Scrapling → Playwright.
    QUALIFICATION GATE: Each lead validated before pipeline entry.
    Returns dict with {"leads": [...], "text": "...", "qualified_count": N}
    """
    # Normalize query for deduplication
    normalized_query = query.strip().lower()
    
    # Clean expired entries first
    now = datetime.utcnow()
    expired = [q for q, ts in SEARCH_HISTORY.items() if now - ts > timedelta(hours=SEARCH_EXPIRY_HOURS)]
    for q in expired:
        del SEARCH_HISTORY[q]
    
    # Check if query already exists in history
    if normalized_query in SEARCH_HISTORY:
        logger.info(f"[HAWK] Skipping duplicate search: '{query}'")
        return {
            "leads": [],
            "text": "Already searched for this query. Skipping.",
            "qualified_count": 0,
            "skipped": True
        }
    
    # Mark query as searched before running to prevent race conditions
    SEARCH_HISTORY[normalized_query] = now
    
    logger.info(f"[HAWK] Searching: '{query}' count={count}")

    # Tier 1: DDGS
    raw_results = _ddgs_search(query, count)

    # Tier 2: Scrapling fallback
    if not raw_results:
        logger.info("[HAWK] DDGS empty — falling back to Scrapling")
        raw_results = _scrapling_search(query, count)

    # Tier 3: Playwright last resort
    if not raw_results:
        logger.info("[HAWK] Scrapling empty — falling back to Playwright")
        raw_results = await _playwright_search(query, count)

    if not raw_results:
        return {
            "leads": [],
            "text": f"No leads found for '{query}'. Try a more specific search query.",
            "qualified_count": 0,
        }

    # Enrich with contact info + QUALIFICATION GATE
    leads = []
    qualified_count = 0

    for r in raw_results[:count]:
        url = r.get("href") or r.get("url", "")
        contact = scrape_contact_info(url) if url else {}
        lead = {
            "title":   r.get("title", "Unknown"),
            "url":     url,
            "snippet": (r.get("body") or "")[:150],
            "email":   contact.get("email"),
            "phone":   contact.get("phone"),
        }

        # ── QUALIFICATION GATE ──────────────────────────────────
        lead = await validate_and_enrich_lead(lead)

        if lead.get("qualified"):
            qualified_count += 1
        else:
            logger.warning(f"[HAWK] Lead NOT qualified: {lead['title']} — {lead.get('qualification_reason', 'unknown')}")

        leads.append(lead)

    # Format text for human-readable output
    output = f"HAWK — Found {len(leads)} Leads ({qualified_count} qualified) for '{query}':\n\n"
    for i, lead in enumerate(leads, 1):
        status = "✅" if lead.get("qualified") else "❌"
        output += f"{status} {i}. {lead['title']}\n"
        output += f"   {lead['url']}\n"
        if lead.get("email"):
            output += f"   📧 Email: {lead['email']}\n"
        if lead.get("phone"):
            output += f"   📞 Phone: {lead['phone']}\n"
        if lead.get("linkedin"):
            output += f"   🔗 LinkedIn: {lead['linkedin']}\n"
        if lead.get("snippet"):
            output += f"   {lead['snippet'][:100]}...\n"
        output += f"   Score: {lead.get('qualification_score', 0)}/100 | Source: {lead.get('enrichment_source', 'unknown')}\n"
        output += "\n"

    return {"leads": leads, "text": output, "qualified_count": qualified_count}


async def read_webpage(url: str) -> str:
    """Visit a specific URL and extract main text content."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
            page    = await browser.new_page()
            await page.goto(url, timeout=30000)
            title   = await page.title()
            content = await page.evaluate("document.body.innerText")
            await browser.close()
            cleaned = " ".join(content.split())[:3000]
            return f"Page: {title}\n\n{cleaned}..."
    except Exception as e:
        return f"Could not read page: {str(e)}"


def get_search_history() -> Dict:
    """
    API endpoint handler for /api/searches
    Returns current search history with timestamps and expiry info
    """
    now = datetime.utcnow()
    history_list = []
    
    for query, timestamp in SEARCH_HISTORY.items():
        age = now - timestamp
        expires_in = timedelta(hours=SEARCH_EXPIRY_HOURS) - age
        history_list.append({
            "query": query,
            "timestamp": timestamp.isoformat(),
            "age_seconds": int(age.total_seconds()),
            "expires_in_seconds": max(0, int(expires_in.total_seconds()))
        })
    
    return {
        "total": len(history_list),
        "expiry_hours": SEARCH_EXPIRY_HOURS,
        "searches": history_list
    }
