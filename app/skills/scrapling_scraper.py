# -*- coding: utf-8 -*-
"""
OROVA Stealth Scraper — Powered by Scrapling
Anti-bot bypass, proxy rotation, fingerprint spoofing.
Designed as Tier 0 for lead_finder.py (runs before Tavily).

Inspired by: https://github.com/D4Vinci/Scrapling
"""

import os
import logging
import asyncio
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

# Proxy list from env (comma-separated)
_PROXY_LIST = [p.strip() for p in os.getenv("PROXY_LIST", "").split(",") if p.strip()]
_SCRAPING_MODE = os.getenv("SCRAPING_MODE", "stealth")  # stealth | fast | headless

# Domains to always skip
BANNED_DOMAINS = [
    "wikipedia.org", "reddit.com", "youtube.com", "facebook.com",
    "instagram.com", "linkedin.com", "twitter.com", "pinterest.com",
    "yelp.com", "tripadvisor.com", "blog.", "news.", "forbes.com",
    "businessinsider.com", "quora.com", "medium.com",
]


def _get_proxy():
    """Round-robin proxy selection."""
    if not _PROXY_LIST:
        return None
    import random
    return random.choice(_PROXY_LIST)


def _is_banned(url: str) -> bool:
    """Check if URL belongs to a non-business domain."""
    lower = url.lower()
    return any(d in lower for d in BANNED_DOMAINS)


# ═══════════════════════════════════════════════════════════════════════════════
# STEALTH SEARCH — Anti-bot Google/Bing search via Scrapling
# ═══════════════════════════════════════════════════════════════════════════════

async def stealth_search(query: str, count: int = 10) -> str:
    """
    Perform a stealth web search using Scrapling's anti-bot fetcher.
    Bypasses Cloudflare and other protections.

    Returns formatted lead list string.
    """
    count = int(count)
    logger.info(f"[STEALTH] Searching: '{query}' (count={count})")
    leads = []

    try:
        from scrapling import StealthyFetcher

        fetcher = StealthyFetcher()

        # Search via Google with stealth
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={count * 2}"
        proxy = _get_proxy()

        page = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fetcher.fetch(
                search_url,
                headless=True,
                disable_resources=True,
                proxy={"server": proxy} if proxy else None,
            )
        )

        if page and page.status == 200:
            # Extract search result blocks
            results = page.css("div.g")
            for result in results[:count * 2]:
                try:
                    link_el = result.css_first("a[href]")
                    title_el = result.css_first("h3")
                    snippet_el = result.css_first("div.VwiC3b, span.aCOpRe, div[data-sncf]")

                    if not link_el or not title_el:
                        continue

                    url = link_el.attrib.get("href", "")
                    title = title_el.text or "Untitled"
                    snippet = snippet_el.text if snippet_el else ""

                    # Skip non-business domains
                    if _is_banned(url):
                        continue

                    # Skip Google internal links
                    if not url.startswith("http"):
                        continue

                    leads.append({
                        "title": title.strip(),
                        "url": url.strip(),
                        "snippet": snippet.strip()[:200]
                    })
                except Exception:
                    continue

            logger.info(f"[STEALTH] Found {len(leads)} vetted results")
        else:
            status = page.status if page else "no response"
            logger.warning(f"[STEALTH] Google returned status: {status}")

    except ImportError:
        logger.warning("[STEALTH] Scrapling not installed. Falling back. Run: pip install scrapling")
        # Fallback to httpx-based search
        leads = await _httpx_fallback_search(query, count)
    except Exception as e:
        logger.error(f"[STEALTH] Search error: {e}")
        leads = await _httpx_fallback_search(query, count)

    # Format output
    leads = leads[:count]
    if not leads:
        return ""

    result_text = f"**[STEALTH] Found {len(leads)} Business Leads:**\n\n"
    for i, l in enumerate(leads, 1):
        snippet = l.get('snippet', '')[:120]
        result_text += f"{i}. **[{l['title']}]({l['url']})**\n   _{snippet}..._\n\n"

    return result_text


async def _httpx_fallback_search(query: str, count: int) -> list:
    """Lightweight fallback using httpx with TLS fingerprint spoofing."""
    leads = []
    try:
        import httpx

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "DNT": "1",
        }

        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=20.0,
            proxy=_get_proxy()
        ) as client:
            resp = await client.get(search_url)

            if resp.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                results = soup.select("div.result, div.web-result")

                for r in results[:count * 2]:
                    a_tag = r.select_one("a.result__a, a.result__url")
                    snippet_tag = r.select_one("a.result__snippet, div.result__snippet")

                    if not a_tag:
                        continue

                    url = a_tag.get("href", "")
                    title = a_tag.get_text(strip=True)
                    snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

                    if _is_banned(url) or not url.startswith("http"):
                        continue

                    leads.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet[:200]
                    })

    except Exception as e:
        logger.error(f"[STEALTH FALLBACK] Error: {e}")

    return leads[:count]


# ═══════════════════════════════════════════════════════════════════════════════
# STEALTH EXTRACT — Deep page extraction with anti-bot bypass
# ═══════════════════════════════════════════════════════════════════════════════

async def stealth_extract(url: str, selectors: str = "") -> str:
    """
    Visit a URL with full anti-bot bypass and extract structured content.
    Automatically finds contact info, owner names, phone numbers, emails.

    Args:
        url: Target URL to scrape
        selectors: Optional CSS selectors (comma-separated) to extract specific elements

    Returns:
        Formatted extraction report
    """
    logger.info(f"[STEALTH EXTRACT] Visiting: {url}")

    try:
        from scrapling import StealthyFetcher

        fetcher = StealthyFetcher()
        proxy = _get_proxy()

        page = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: fetcher.fetch(
                url,
                headless=True,
                proxy={"server": proxy} if proxy else None,
            )
        )

        if not page or page.status != 200:
            return f"⚠️ Could not access {url} (status: {page.status if page else 'no response'})"

        report = f"# Stealth Extraction: {url}\n\n"

        # Extract page title
        title_el = page.css_first("title")
        if title_el:
            report += f"**Title:** {title_el.text}\n\n"

        # Auto-extract contact information
        report += "## Contact Information\n"
        contact_info = _extract_contact_info(page)
        if contact_info:
            for key, values in contact_info.items():
                report += f"- **{key}:** {', '.join(values)}\n"
        else:
            report += "- No contact info found on main page\n"

        report += "\n"

        # Custom selectors if provided
        if selectors:
            report += "## Custom Extractions\n"
            for sel in selectors.split(","):
                sel = sel.strip()
                elements = page.css(sel)
                if elements:
                    report += f"### `{sel}` ({len(elements)} found)\n"
                    for el in elements[:5]:
                        report += f"- {el.text[:200]}\n"
                else:
                    report += f"### `{sel}` — Not found\n"
            report += "\n"

        # Main content extraction
        body_text = page.css_first("body")
        if body_text:
            clean_text = " ".join(body_text.text.split())[:3000]
            report += f"## Page Content\n{clean_text}...\n"

        return report

    except ImportError:
        logger.warning("[STEALTH EXTRACT] Scrapling not installed, using Playwright fallback")
        return await _playwright_extract_fallback(url)
    except Exception as e:
        logger.error(f"[STEALTH EXTRACT] Error: {e}")
        return f"⚠️ Stealth extraction failed: {str(e)}"


def _extract_contact_info(page) -> Dict[str, List[str]]:
    """Extract phone numbers, emails, and names from a Scrapling page response."""
    import re

    info = {}
    text = page.css_first("body").text if page.css_first("body") else ""

    # Phone numbers
    phones = re.findall(
        r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,3}[)]?[-\s\.]?[0-9]{3,4}[-\s\.]?[0-9]{3,4}',
        text
    )
    phones = list(set(p.strip() for p in phones if len(p.strip()) >= 10))
    if phones:
        info["Phones"] = phones[:5]

    # Emails
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    emails = list(set(e for e in emails if not any(
        x in e.lower() for x in ["example.com", "test.com", "email.com", "domain.com", "sentry.io"]
    )))
    if emails:
        info["Emails"] = emails[:5]

    # Try to find owner/team names from common patterns
    about_sections = page.css("section#about, div#about, .about-us, .team, .leadership, #team")
    for section in about_sections:
        names = re.findall(
            r'(?:CEO|Owner|Founder|President|Director|Manager)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
            section.text
        )
        if names:
            info["Key People"] = list(set(names))[:5]

    return info


async def _playwright_extract_fallback(url: str) -> str:
    """Fallback extraction using Playwright when Scrapling is unavailable."""
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page()
            await page.goto(url, timeout=30000)
            title = await page.title()
            content = await page.evaluate("document.body.innerText")
            await browser.close()

            cleaned = " ".join(content.split())[:3000]
            return f"📄 **{title}**\n\n{cleaned}..."
    except Exception as e:
        return f"⚠️ All extraction methods failed: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════════════
# BULK SCRAPE — Multiple URLs in parallel with rate limiting
# ═══════════════════════════════════════════════════════════════════════════════

async def bulk_scrape(urls: str, objective: str = "Extract contact information") -> str:
    """
    Scrape multiple URLs in parallel with stealth.

    Args:
        urls: Comma-separated list of URLs to scrape
        objective: What to extract from each page

    Returns:
        Combined extraction report
    """
    url_list = [u.strip() for u in urls.split(",") if u.strip()]

    if not url_list:
        return "⚠️ No valid URLs provided."

    logger.info(f"[BULK SCRAPE] Processing {len(url_list)} URLs: {objective}")

    # Rate limit: max 5 concurrent
    semaphore = asyncio.Semaphore(5)
    results = []

    async def scrape_one(url):
        async with semaphore:
            result = await stealth_extract(url)
            await asyncio.sleep(1)  # Polite delay between requests
            return {"url": url, "result": result}

    tasks = [scrape_one(url) for url in url_list[:20]]  # Cap at 20
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    report = f"# Bulk Scrape Report ({len(url_list)} sites)\n"
    report += f"**Objective:** {objective}\n\n"

    for item in completed:
        if isinstance(item, Exception):
            report += f"---\n⚠️ Error: {str(item)}\n"
        elif isinstance(item, dict):
            report += f"---\n## {item['url']}\n{item['result']}\n"

    return report
