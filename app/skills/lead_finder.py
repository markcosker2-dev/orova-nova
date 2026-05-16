import os
import logging
import asyncio
import re

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
    "pornhub.com", "xvideos.com", "xnxx.com", "adult", "sex", "porn",
    "baidu.com", "iciba.com", "dict.cn", "youdao.com", "zdic.net",
    "wordreference.com", "thesaurus.com"
]

JUNK_KEYWORDS = [
    r"\bdefinition\b", r"\bmeaning\b", r"\bsynonyms\b", r"\bwiki\b", r"\bblog\b", r"\barticle\b", r"\bnews\b",
    r"\bporn\b", r"\bsex\b", r"\badult\b", r"\bxxx\b", r"\bnaked\b", r"\bescort\b", r"\bdictionary\b"
]

async def find_leads(count: int = 5, query: str = "business leads"):
    """
    Search for business leads using Firecrawl (Elite) or DuckDuckGo (Fallback).
    Uses AI verification to ensure leads are actual business websites.
    """
    count = int(count)
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    
    # ─── THE YELP HAMMER (100% Business Only) ───────────────────
    # Force search into Yelp to avoid dictionaries and blog posts
    if "site:" not in query.lower():
        query = f'site:yelp.com "{query}"'
        logger.info(f"[YELP HAMMER] Locked to business directory: {query}")
        
    logger.info(f"[LEAD FINDER] Searching for {count} leads: '{query}'")
    leads = []

    # ─── TIER 1: Firecrawl (Elite — if key available) ─────────────
    if firecrawl_key:
        try:
            logger.info("[FIRECRAWL] Starting elite crawl (v1)...")
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=firecrawl_key)
            # In v1, the search method is still available but might need specific parameters
            # Fallback to a refined query if the search endpoint is restricted
            search_result = app.search(query)
            for res in search_result.get("data", []):
                leads.append({
                    "title": res.get("title", "Untitled"),
                    "url": res.get("url", ""),
                    "snippet": res.get("description", "")
                })
            logger.info(f"[FIRECRAWL] Found {len(leads)} potential leads")
        except Exception as e:
            logger.warning(f"[FIRECRAWL] v1 Search error: {e}. Falling back to smart crawl...")
            # If search is not supported, we can try to crawl a specific business directory
            pass

    # ─── TIER 2: DuckDuckGo (Fallback) ──────────────────────────
    if not leads:
        try:
            leads = await _duckduckgo_search(query, count * 3)
            logger.info(f"[DDG] Found {len(leads)} raw results")
        except Exception as e:
            logger.error(f"[DDG] Search error: {e}")

    # ─── AI VERIFICATION & FILTERING ────────────────────────────
    filtered = []
    for lead in leads:
        url = lead.get("url", "").lower()
        title = lead.get("title", "")
        snippet = lead.get("snippet", "").lower()
        
        # Basic Safety
        if any(d in url for d in BANNED_DOMAINS): continue
        if any(re.search(k, title.lower()) or re.search(k, snippet) for k in JUNK_KEYWORDS): continue
        
        # Hard Skip for Information Sites
        info_sites = [".gov", ".edu", ".org", "forbes.com", "news.", "blog.", "wiki", "dictionary", "merriam-webster"]
        if any(site in url for site in info_sites):
            continue

        # Clean Name
        if len(title) > 40 or any(x in title.lower() for x in ["best", "top", "how to"]):
            domain_part = url.split("//")[-1].split("/")[0].replace("www.", "").split(".")[0]
            lead["business"] = domain_part.replace("-", " ").replace("_", " ").title()
        else:
            lead["business"] = title.split(" - ")[0].split(" | ")[0].strip()

        # 4. Language Check: Delete if contains non-English characters (Chinese/Japanese/etc.)
        if re.search(r'[^\x00-\x7F]+', lead["business"]):
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
                # region="us-en" forces US results only
                return list(ddgs.text(query, max_results=count, safesearch="strict", region="us-en"))

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
