import os
import logging
import asyncio

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD FINDER - 4-Tier Search: Stealth -> Tavily -> Google Scraper -> DuckDuckGo
# Powered by Scrapling + OpenClaw Ecosystem
# ═══════════════════════════════════════════════════════════════════════════════

async def find_leads(count: int = 10, query: str = "business leads"):
    """
    Search for leads using a 4-tier fallback system.
    Tier 0: Scrapling stealth (anti-bot bypass, proxy rotation)
    Tier 1: Tavily API
    Tier 2: Google Scraper (Playwright)
    Tier 3: DuckDuckGo (failsafe)
    Strictly filters out non-business URLs (blogs, lists, forums).
    """
    count = int(count)
    # ─── QUERY HARDENING (Business Intent) ──────────────────────────
    intent_keywords = ["official website", "dealership", "contact", "services"]
    if not any(k in query.lower() for k in intent_keywords):
        query += " (official website or dealership)"
        
    logger.info(f"[LEAD FINDER] Searching for {count} leads: '{query}'")
    leads = []

    BANNED_DOMAINS = [
        "wikipedia.org", "reddit.com", "youtube.com", "facebook.com", 
        "instagram.com", "linkedin.com", "twitter.com", "pinterest.com",
        "yelp.com", "tripadvisor.com", "blog.", "news.", "forbes.com",
        "businessinsider.com", "reddit.", "quora.com", "medium.com"
    ]

    # ─── TIER 0: SCRAPLING STEALTH (Anti-Bot Bypass) ──────────────────────
    try:
        from app.skills.scrapling_scraper import stealth_search
        logger.info("[STEALTH] Tier 0: Trying Scrapling stealth search...")
        stealth_result = await stealth_search(query, count)
        if stealth_result and "Found" in stealth_result:
            logger.info("[STEALTH] Success! Returning stealth results.")
            return stealth_result
    except Exception as e:
        logger.warning(f"[STEALTH] Tier 0 skipped: {e}")

    # ─── TIER 1: TAVILY (API) ─────────────────────────────────────────────
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key and len(query.strip()) >= 2:
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=tavily_key)
            response = tavily.search(query=query, search_depth="advanced", max_results=count * 2)
            for res in response.get("results", []):
                url = res.get("url", "").lower()
                # Skip non-actionable domains
                if any(domain in url for domain in BANNED_DOMAINS):
                    continue
                leads.append({
                    "title": res.get("title", "Untitled"),
                    "url": res.get("url"),
                    "snippet": res.get("content", "")
                })
            if leads:
                logger.info(f"[TAVILY] Found {len(leads)} vetted leads.")
        except Exception as e:
            logger.warning(f"[TAVILY] Failed: {e}")

    # ─── TIER 2: GOOGLE SCRAPER (Playwright) ──────────────────────────────
    if not leads:
        try:
            from app.skills.browser_ops import google_search_scrape_async
            logger.info("[GOOGLE SCRAPER] Tavily empty or filtered. Trying Google...")
            google_results = await google_search_scrape_async(query, limit=count * 2)
            if google_results:
                for res in google_results:
                    url = res.get("url", "").lower()
                    if any(domain in url for domain in BANNED_DOMAINS):
                        continue
                    leads.append({
                        "title": res.get("title", "Untitled"),
                        "url": res.get("url"),
                        "snippet": res.get("snippet", "")
                    })
                logger.info(f"[GOOGLE] Found {len(leads)} vetted leads.")
        except Exception as e:
            logger.error(f"[GOOGLE SCRAPER] Error: {e}")

    # ─── TIER 3: DUCKDUCKGO (Failsafe) ───────────────────────────────────
    if not leads:
        try:
            logger.info("[DUCKDUCKGO] Trying DuckDuckGo...")
            raw_leads = await _duckduckgo_search(query, count * 2)
            for l in raw_leads:
                url = l.get("url", "").lower()
                if any(domain in url for domain in BANNED_DOMAINS):
                    continue
                leads.append(l)
        except Exception as e:
            logger.error(f"[DUCKDUCKGO] Error: {e}")

    # ─── FORMAT OUTPUT ────────────────────────────────────────────────────
    leads = leads[:count] # Trim to requested count after filtering
    
    if not leads:
        return {
            "text": (
                "I found results, but they were all non-actionable sites (blogs, forums, news). "
                "I have filtered them out. TRY A MORE SPECIFIC QUERY targeting a city or owner, "
                "e.g., 'Luxury car dealerships in Beverly Hills' instead of just 'Luxury cars'."
            ),
            "leads": []
        }

    result_text = f"**Found {len(leads)} Actionable Business Leads:**\n\n"
    for i, l in enumerate(leads, 1):
        snippet = l.get('snippet', '')[:120]
        result_text += f"{i}. **[{l['title']}]({l['url']})**\n   _{snippet}..._\n\n"

    return {"text": result_text, "leads": leads}


async def _duckduckgo_search(query: str, count: int) -> list:
    """DuckDuckGo search using the 'duckduckgo_search' package (100% Free)."""
    count = int(count)
    leads = []

    try:
        from duckduckgo_search import DDGS
        # Correct usage for duckduckgo-search >= 5.x
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=count))
            
        for res in results:
            leads.append({
                "title": res.get("title", "Untitled"),
                "url": res.get("href", res.get("link", "")),
                "snippet": res.get("body", res.get("snippet", ""))
            })
        return leads
    except ImportError:
        logger.error("duckduckgo-search package not installed.")
    except Exception as e:
        logger.error(f"DDG search error: {e}")

    return leads


async def research_lead(url: str) -> str:
    """
    Deep-dive a lead: visit their site, extract key info, score them 1-10.
    Inspired by awesome-claude-skills/lead-research-assistant.
    """
    logger.info(f"[LEAD RESEARCH] Deep-diving: {url}")

    report = f"# Lead Research: {url}\n\n"

    try:
        from app.skills.browser_ops import browse_and_extract
        page_content = await browse_and_extract(url=url, objective="Extract main text content")
        if page_content:
            report += f"## Website Content\n{page_content[:2000]}\n\n"
        else:
            report += "## Website Content\nCould not extract content.\n\n"
    except Exception as e:
        report += f"## Website Content\nError: {e}\n\n"

    # Search for more info about this business
    try:
        # Extract domain name for searching
        import re
        domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        domain = domain_match.group(1) if domain_match else url

        search_result = await find_leads(count=3, query=f"{domain} owner reviews")
        if search_result:
            report += f"## Additional Info\n{search_result}\n\n"
    except Exception as e:
        logger.warning(f"[LEAD RESEARCH] Additional search failed: {e}")

    report += """## Scoring Criteria (Score this lead 1-10)
- Service alignment with OROVA (remodeling/luxury)
- Website quality and professionalism
- Business size indicators
- Geographic fit (California focus)
- Signs of budget for marketing services

## Suggested Outreach
- Identify the decision maker (owner/marketing director)
- Reference something specific from their website
- Lead with OROVA's value proposition for their specific niche
"""

    return report
