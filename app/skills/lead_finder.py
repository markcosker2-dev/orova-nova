import os
import logging
import asyncio

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD FINDER — DuckDuckGo Primary (100% Free, No API Key Required)
# ═══════════════════════════════════════════════════════════════════════════════

# Only ban truly useless domains. Keep business directories that have real leads.
BANNED_DOMAINS = [
    "wikipedia.org", "reddit.com", "youtube.com", "pinterest.com",
    "quora.com", "medium.com", "twitter.com", "tiktok.com",
    "dictionary.com", "merriam-webster.com", "thefreedictionary.com",
    "britannica.com", "facebook.com", "instagram.com", "yelp.com/biz",
    "pornhub.com", "xvideos.com", "xnxx.com", "adult", "sex", "porn"
]

JUNK_KEYWORDS = [
    "definition", "meaning", "synonyms", "wiki", "blog", "article", "news",
    "porn", "sex", "adult", "xxx", "naked", "escort"
]

async def find_leads(count: int = 5, query: str = "business leads"):
    """
    Search for business leads using DuckDuckGo (free, no API key).
    Returns real URLs with titles and snippets.
    """
    count = int(count)

    # ─── RELIABLE LOCAL SEARCH ─────────────────────────────
    # Use a more balanced search that doesn't trigger bot protection as easily
    if "site:" not in query.lower():
        # Mix in business directories but don't force a single one to avoid blocks
        query = f'"{query}" (yelp OR "yellow pages" OR "business directory")'
        logger.info(f"[SEARCH] Enhanced Query: {query}")
        
    logger.info(f"[LEAD FINDER] Searching for {count} leads: '{query}'")
    leads = []

    # ─── TIER 1: DuckDuckGo (Primary — always available) ─────────
    try:
        leads = await _duckduckgo_search(query, count * 3)
        if not leads:
            logger.warning(f"[LEAD FINDER] DuckDuckGo returned 0 results for: {query}")
        else:
            logger.info(f"[DDG] Successfully found {len(leads)} raw results")
    except Exception as e:
        logger.error(f"[DDG] Search error: {e}")

    # ─── TIER 2: HTTPX Fallback (if DDG fails) ───────────────────
    if not leads:
        try:
            logger.info("[HTTPX] DDG failed. Trying httpx fallback...")
            leads = await _httpx_search(query, count * 3)
            logger.info(f"[HTTPX] Raw results: {len(leads)}")
        except Exception as e:
            logger.error(f"[HTTPX] Fallback error: {e}")

    # ─── Filter banned domains and junk keywords ──────────────────
    filtered = []
    for lead in leads:
        url = lead.get("url", "").lower()
        title = lead.get("title", "").lower()
        snippet = lead.get("snippet", "").lower()
        
        # Domain check
        if any(d in url for d in BANNED_DOMAINS):
            logger.info(f"[FILTER] Skipped banned domain: {url[:60]}")
            continue
            
        # Junk keyword check
        if any(k in title or k in snippet for k in JUNK_KEYWORDS):
            logger.info(f"[FILTER] Skipped junk keyword in: {title[:40]}")
            continue
            
        filtered.append(lead)

    leads = filtered[:count]

    if not leads:
        return {
            "text": (
                "Search returned no actionable results for this query. "
                "Try being more specific, e.g., 'luxury remodeling contractors Los Angeles' "
                "or 'BMW dealership Beverly Hills'."
            ),
            "leads": []
        }

    result_text = f"**Found {len(leads)} Business Leads:**\n\n"
    for i, l in enumerate(leads, 1):
        snippet = l.get('snippet', '')[:150]
        result_text += f"{i}. **{l['title']}**\n   🔗 {l['url']}\n   _{snippet}_\n\n"

    return {"text": result_text, "leads": leads}


async def _duckduckgo_search(query: str, count: int) -> list:
    """DuckDuckGo search using the duckduckgo-search package."""
    leads = []
    try:
        from duckduckgo_search import DDGS

        # Run synchronous DDG in executor to avoid blocking
        def _search():
            with DDGS() as ddgs:
                # Add safesearch="strict" to ensure business-only results
                return list(ddgs.text(query, max_results=count, safesearch="strict"))

        results = await asyncio.get_event_loop().run_in_executor(None, _search)

        for res in results:
            leads.append({
                "title": res.get("title", "Untitled"),
                "url": res.get("href", res.get("link", "")),
                "snippet": res.get("body", res.get("snippet", ""))
            })
    except ImportError:
        logger.error("[DDG] duckduckgo-search not installed")
    except Exception as e:
        logger.error(f"[DDG] Error: {e}")

    return leads


async def _httpx_search(query: str, count: int) -> list:
    """Fallback: scrape DuckDuckGo HTML directly."""
    leads = []
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        }
        # kp=-2 is DuckDuckGo's "Strict" SafeSearch parameter
        search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}&kp=-2"

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(search_url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for r in soup.select("div.result"):
                    a_tag = r.select_one("a.result__a")
                    snippet_tag = r.select_one("a.result__snippet")
                    if a_tag:
                        leads.append({
                            "title": a_tag.get_text(strip=True),
                            "url": a_tag.get("href", ""),
                            "snippet": snippet_tag.get_text(strip=True) if snippet_tag else ""
                        })
    except Exception as e:
        logger.error(f"[HTTPX] Error: {e}")

    return leads[:count]


async def research_lead(url: str) -> str:
    """Deep-dive a lead: visit their site, extract key info, score them."""
    logger.info(f"[LEAD RESEARCH] Deep-diving: {url}")
    report = f"# Lead Research: {url}\n\n"

    try:
        from app.skills.browser_ops import browse_and_extract
        page_content = await browse_and_extract(url=url, objective="Extract business info, owner name, phone, email, services")
        if page_content:
            report += f"## Website Content\n{str(page_content)[:2000]}\n\n"
        else:
            report += "## Website Content\nCould not extract content.\n\n"
    except Exception as e:
        report += f"## Website Content\nError: {e}\n\n"

    report += """## Scoring Criteria
- Service alignment with OROVA (remodeling/luxury/auto)
- Website quality and professionalism
- Business size indicators
- Geographic fit (California focus)
- Signs of budget for marketing services
"""
    return report
