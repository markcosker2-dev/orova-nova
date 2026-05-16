import os
import logging
import asyncio
import re
from app.core.ai_client import UnifiedAIClient

ai = UnifiedAIClient()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD FINDER — Multi-Tier Sourcing Engine
# ═══════════════════════════════════════════════════════════════════════════════

# Ban junk domains. NEVER ban yelp.com — it's our primary source.
BANNED_DOMAINS = [
    "wikipedia.org", "reddit.com", "youtube.com", "pinterest.com",
    "quora.com", "medium.com", "twitter.com", "tiktok.com",
    "dictionary.com", "merriam-webster.com", "thefreedictionary.com",
    "britannica.com", "facebook.com", "instagram.com",
    "pornhub.com", "xvideos.com", "xnxx.com",
    "baidu.com", "iciba.com", "dict.cn", "youdao.com", "zdic.net",
    "wordreference.com", "thesaurus.com", "glosbe.com", "linguee.com"
]

JUNK_KEYWORDS = [
    r"\bdefinition\b", r"\bmeaning\b", r"\bsynonyms\b", r"\bwiki\b", r"\bblog\b", r"\barticle\b", r"\bnews\b",
    r"\bporn\b", r"\bsex\b", r"\badult\b", r"\bxxx\b", r"\bnaked\b", r"\bescort\b", r"\bdictionary\b"
]


async def verify_business_intent(title: str, snippet: str, url: str) -> bool:
    """Uses AI to determine if a search result is a real business or just info/junk."""
    # Yelp business pages are ALWAYS real businesses — skip AI check
    if "yelp.com/biz/" in url.lower():
        return True

    prompt = f"""
    Analyze this search result and determine if it is a REAL LOCAL BUSINESS (e.g. contractor, dealer, service provider).
    Respond with ONLY 'YES' or 'NO'.
    
    Title: {title}
    Snippet: {snippet}
    URL: {url}
    
    Is this a real business? (NO if it's a dictionary, wiki, blog, or news site)
    """
    try:
        res = await ai.quick(prompt)
        return "YES" in res.upper()
    except:
        # If AI is unavailable, allow the lead through — better to have a lead than nothing
        logger.warning("[AI SCORER] AI unavailable. Allowing lead through.")
        return True


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
        clean_query = query.replace('"', '').replace("'", "")
        query = f'site:yelp.com {clean_query}'
        logger.info(f"[YELP HAMMER] Broadened: {query}")
        
    logger.info(f"[LEAD FINDER] Searching for {count} leads: '{query}'")
    leads = []

    # ─── TIER 1: Firecrawl Search (if key available) ────────────
    if firecrawl_key:
        try:
            logger.info("[FIRECRAWL] Starting elite crawl (v1)...")
            from firecrawl import FirecrawlApp
            app = FirecrawlApp(api_key=firecrawl_key)
            search_result = app.search(query)
            for res in search_result.get("data", []):
                leads.append({
                    "title": res.get("title", "Untitled"),
                    "url": res.get("url", ""),
                    "snippet": res.get("description", "")
                })
            logger.info(f"[FIRECRAWL] Found {len(leads)} potential leads")
        except Exception as e:
            logger.warning(f"[FIRECRAWL] Search failed: {e}. Trying direct crawl...")

    # ─── TIER 2: DuckDuckGo (Fallback 1) ───────────────────────
    if not leads:
        try:
            # DDG doesn't like 'site:' operators. Strip it and just add 'yelp'
            ddg_query = query.replace("site:yelp.com", "yelp")
            leads = await _duckduckgo_search(ddg_query, count * 3)
            logger.info(f"[DDG] Found {len(leads)} raw results")
        except Exception as e:
            logger.error(f"[DDG] Search error: {e}")

    # ─── TIER 3: HTTPX Scraper (Fallback 2 — Best for Render) ────
    if not leads:
        try:
            logger.info("[HTTPX] Trying direct HTML scrape fallback...")
            httpx_query = query.replace("site:yelp.com", "yelp")
            leads = await _httpx_search(httpx_query, count * 2)
            logger.info(f"[HTTPX] Found {len(leads)} raw results")
        except Exception as e:
            logger.error(f"[HTTPX] Search error: {e}")

    # ─── TIER 4: Google (Fallback 3 — Unreliable on Render) ──────
    if not leads:
        try:
            logger.info("[GOOGLE] Searching fallback...")
            from app.skills.browser_ops import google_search_scrape_async
            leads = await google_search_scrape_async(query, limit=count*2)
            logger.info(f"[GOOGLE] Found {len(leads)} raw results")
        except Exception as e:
            logger.error(f"[GOOGLE] Search error: {e}")

    # ─── TIER 5: Direct Yelp Crawl (The "Front Door") ──────────
    if not leads:
        try:
            logger.info("[YELP DIRECT] Search engines blocked us. Going to the front door...")
            leads = await direct_yelp_crawl(query.replace("site:yelp.com ", ""), count)
            logger.info(f"[YELP DIRECT] Found {len(leads)} raw results")
        except Exception as e:
            logger.error(f"[YELP DIRECT] Error: {e}")

    # ─── FILTERING ─────────────────────────────────────────────
    filtered = []
    for lead in leads:
        url = lead.get("url", "").lower()
        title = lead.get("title", "")
        snippet = lead.get("snippet", "").lower()
        
        # Ban junk domains (but NEVER ban yelp.com)
        if any(d in url for d in BANNED_DOMAINS):
            logger.info(f"[FILTER] Banned domain: {url}")
            continue
        if any(re.search(k, title.lower()) or re.search(k, snippet) for k in JUNK_KEYWORDS):
            logger.info(f"[FILTER] Junk keyword: {title}")
            continue
        
        # Hard Skip for Information Sites
        info_sites = [".gov", ".edu", "forbes.com", "news.", "blog.", "wiki", "dictionary", "merriam-webster"]
        if any(site in url for site in info_sites):
            logger.info(f"[FILTER] Info site: {url}")
            continue

        # Clean Name
        if "yelp.com/biz/" in url:
            # Extract clean business name from Yelp URL
            biz_slug = url.split("/biz/")[-1].split("?")[0]
            lead["business"] = biz_slug.replace("-", " ").title()
        elif len(title) > 40 or any(x in title.lower() for x in ["best", "top", "how to"]):
            domain_part = url.split("//")[-1].split("/")[0].replace("www.", "").split(".")[0]
            lead["business"] = domain_part.replace("-", " ").replace("_", " ").title()
        else:
            lead["business"] = title.split(" - ")[0].split(" | ")[0].strip()

        # Language Check: Delete if contains non-English characters
        if re.search(r'[^\x00-\x7F]+', lead["business"]):
            continue

        # AI SCORER: Verify business intent (auto-passes Yelp businesses)
        if not await verify_business_intent(title, snippet, url):
            logger.info(f"[AI SCORER] Rejected non-business: {title}")
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

        def _search():
            with DDGS() as ddgs:
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


async def direct_yelp_crawl(topic: str, count: int) -> list:
    """Scrapes Yelp search results directly when search engines fail."""
    leads = []
    search_topic = topic.replace(" ", "+")
    yelp_url = f"https://www.yelp.com/search?find_desc={search_topic}"
    
    try:
        from firecrawl import FirecrawlApp
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_key:
            app = FirecrawlApp(api_key=firecrawl_key)
            logger.info(f"[YELP DIRECT] Crawling with Firecrawl: {yelp_url}")
            scrape_res = app.scrape_url(yelp_url, params={'formats': ['markdown']})
            content = str(scrape_res.get("markdown", ""))
            
            matches = re.findall(r'/biz/[a-zA-Z0-9\-%]+', content)
            for m in list(set(matches))[:count*2]:
                biz_url = f"https://www.yelp.com{m}"
                leads.append({
                    "title": m.split("/")[-1].replace("-", " ").title(),
                    "url": biz_url,
                    "snippet": "Directly sourced from Yelp listings."
                })
    except Exception as e:
        logger.warning(f"[YELP DIRECT] Firecrawl failed: {e}. Falling back to internal browser...")

    if not leads:
        try:
            from app.skills.browser_ops import browse_and_extract
            logger.info(f"[YELP DIRECT] Internal Browser Sourcing: {yelp_url}")
            # browse_and_extract is sync, run in executor
            res = await asyncio.get_event_loop().run_in_executor(
                None, browse_and_extract, yelp_url, "Find links to business profiles (starting with /biz/)"
            )
            content = str(res)
            matches = re.findall(r'/biz/[a-zA-Z0-9\-%]+', content)
            for m in list(set(matches))[:count*2]:
                biz_url = f"https://www.yelp.com{m}"
                leads.append({
                    "title": m.split("/")[-1].replace("-", " ").title(),
                    "url": biz_url,
                    "snippet": "Sourced via Internal Browser."
                })
        except Exception as e:
            logger.error(f"[YELP DIRECT] Internal Browser failed: {e}")
    
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
