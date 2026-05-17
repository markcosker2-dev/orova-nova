import os
import logging
import asyncio
import re
import httpx
from bs4 import BeautifulSoup
from app.core.ai_client import UnifiedAIClient

ai = UnifiedAIClient()
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD FINDER V3 — Multi-Source Discovery Engine
# ═══════════════════════════════════════════════════════════════════════════════
# Sources: DuckDuckGo, Direct Yelp, Google Maps (SerpAPI), Business Directories
# Goal: Find REAL businesses with owner names, emails, and phone numbers.

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

JUNK_COMPILED = [re.compile(p, re.IGNORECASE) for p in JUNK_KEYWORDS]


async def find_leads(count: int = 5, query: str = "business leads"):
    """
    Multi-source lead discovery engine.
    Sources leads from DuckDuckGo, Yelp, and business directories.
    Does NOT force everything through Yelp — searches broadly for real businesses.
    """
    count = int(count)
    logger.info(f"[LEAD FINDER V3] Searching for {count} leads: '{query}'")
    all_leads = []

    # ─── SOURCE 1: DuckDuckGo — Broad Business Search ──────────
    # Search for actual businesses, not just Yelp listings
    ddg_leads = await _source_duckduckgo(query, count * 2)
    all_leads.extend(ddg_leads)
    logger.info(f"[SOURCE 1: DDG] Found {len(ddg_leads)} leads")

    # ─── SOURCE 2: DuckDuckGo — Yelp-Focused Search ───────────
    # Also search Yelp specifically to catch directory-listed businesses
    yelp_leads = await _source_duckduckgo(f"{query} yelp", count)
    all_leads.extend(yelp_leads)
    logger.info(f"[SOURCE 2: DDG+Yelp] Found {len(yelp_leads)} leads")

    # ─── SOURCE 3: HTTPX Direct HTML Scrape ────────────────────
    if len(all_leads) < count:
        httpx_leads = await _source_httpx(query, count * 2)
        all_leads.extend(httpx_leads)
        logger.info(f"[SOURCE 3: HTTPX] Found {len(httpx_leads)} leads")

    # ─── SOURCE 4: Direct Yelp Crawl (Firecrawl) ──────────────
    if len(all_leads) < count:
        yelp_direct = await _source_yelp_direct(query, count)
        all_leads.extend(yelp_direct)
        logger.info(f"[SOURCE 4: Yelp Direct] Found {len(yelp_direct)} leads")

    # ─── SOURCE 4.5: BBB.org (Better Business Bureau) ────────
    if len(all_leads) < count:
        bbb_leads = await _source_bbb(query, count)
        all_leads.extend(bbb_leads)
        logger.info(f"[SOURCE 4.5: BBB.org] Found {len(bbb_leads)} leads")

    # ─── SOURCE 5: SerpAPI Google Maps (if key available) ──────
    serpapi_key = os.getenv("SERPAPI_KEY")
    if serpapi_key and len(all_leads) < count:
        maps_leads = await _source_google_maps(query, count, serpapi_key)
        all_leads.extend(maps_leads)
        logger.info(f"[SOURCE 5: Google Maps] Found {len(maps_leads)} leads")

    # ─── DEDUP & FILTER ───────────────────────────────────────
    filtered = _filter_and_deduplicate(all_leads, count)
    logger.info(f"[LEAD FINDER V3] Final filtered count: {len(filtered)}")

    if not filtered:
        return {
            "text": (
                "Search returned no actionable results for this query. "
                "Try being more specific, e.g., 'luxury remodeling contractors Los Angeles' "
                "or 'BMW dealership Beverly Hills'."
            ),
            "leads": []
        }

    result_text = f"**Found {len(filtered)} Business Leads:**\n\n"
    for i, l in enumerate(filtered, 1):
        snippet = l.get('snippet', '')[:150]
        result_text += f"{i}. **{l.get('business', l.get('title', 'Unknown'))}**\n   🔗 {l['url']}\n   _{snippet}_\n\n"

    return {"text": result_text, "leads": filtered}


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCE IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def _source_duckduckgo(query: str, count: int) -> list:
    """DuckDuckGo text search — finds actual business websites."""
    leads = []
    try:
        from duckduckgo_search import DDGS

        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=count, safesearch="strict", region="us-en"))

        results = await asyncio.get_running_loop().run_in_executor(None, _search)
        for res in results:
            url = res.get("href", res.get("link", ""))
            title = res.get("title", "Untitled")
            leads.append({
                "title": title,
                "url": url,
                "snippet": res.get("body", res.get("snippet", "")),
                "source_type": "DuckDuckGo"
            })
    except ImportError:
        logger.error("[DDG] duckduckgo-search not installed")
    except Exception as e:
        logger.error(f"[DDG] Error: {e}")
    return leads


async def _source_httpx(query: str, count: int) -> list:
    """Direct HTML scrape of DuckDuckGo — works on Render without Playwright."""
    leads = []
    try:
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
                            "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                            "source_type": "HTTPX Direct"
                        })
    except Exception as e:
        logger.error(f"[HTTPX] Error: {e}")
    return leads[:count]


async def _source_yelp_direct(topic: str, count: int) -> list:
    """Scrapes Yelp search results directly via Firecrawl."""
    leads = []
    search_topic = topic.replace(" ", "+")
    yelp_url = f"https://www.yelp.com/search?find_desc={search_topic}"

    try:
        from firecrawl import FirecrawlApp
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
        if firecrawl_key:
            app = FirecrawlApp(api_key=firecrawl_key)
            logger.info(f"[YELP DIRECT] Crawling: {yelp_url}")
            scrape_res = await asyncio.get_running_loop().run_in_executor(
                None, lambda: app.scrape_url(yelp_url, params={'formats': ['markdown']})
            )
            
            # Handle different Firecrawl response formats
            content = ""
            if isinstance(scrape_res, dict):
                content = str(scrape_res.get("markdown", scrape_res.get("content", "")))
            elif isinstance(scrape_res, str):
                content = scrape_res
            
            logger.info(f"[YELP DIRECT] Got {len(content)} chars of content")
            
            if content:
                biz_matches = re.findall(r'/biz/([a-zA-Z0-9\-%]+)', content)
                seen = set()
                for slug in biz_matches:
                    if slug in seen:
                        continue
                    seen.add(slug)
                    if len(leads) >= count * 2:
                        break
                    
                    biz_url = f"https://www.yelp.com/biz/{slug}"
                    biz_name = slug.replace("-", " ").title()
                    # Remove trailing location numbers (e.g., "Business Name 3")
                    biz_name = re.sub(r'\s+\d+$', '', biz_name)
                    
                    # Extract phone near this business listing
                    idx = content.find(slug)
                    context = content[max(0, idx-300):min(len(content), idx+600)]
                    phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', context)
                    phone = phone_match.group(0) if phone_match else None
                    
                    leads.append({
                        "title": biz_name,
                        "business": biz_name,
                        "url": biz_url,
                        "phone": phone,
                        "snippet": f"From Yelp directory. {f'Phone: {phone}' if phone else ''}",
                        "source_type": "Yelp Direct"
                    })
    except Exception as e:
        logger.warning(f"[YELP DIRECT] Firecrawl failed: {e}")

    return leads[:count]


async def _source_google_maps(query: str, count: int, api_key: str) -> list:
    """Uses SerpAPI to search Google Maps for local businesses with full contact info."""
    leads = []
    try:
        params = {
            "engine": "google_maps",
            "q": query,
            "type": "search",
            "api_key": api_key
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                for biz in data.get("local_results", []):
                    leads.append({
                        "title": biz.get("title", ""),
                        "business": biz.get("title", ""),
                        "url": biz.get("website", biz.get("link", "")),
                        "phone": biz.get("phone", ""),
                        "website": biz.get("website", ""),
                        "snippet": biz.get("description", biz.get("type", "")),
                        "notes": f"Address: {biz.get('address', 'N/A')} | Rating: {biz.get('rating', 'N/A')}",
                        "source_type": "Google Maps"
                    })
                logger.info(f"[GOOGLE MAPS] SerpAPI returned {len(leads)} businesses")
    except Exception as e:
        logger.error(f"[GOOGLE MAPS] SerpAPI error: {e}")
    return leads[:count]


# ═══════════════════════════════════════════════════════════════════════════════
# FILTERING & DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

def _filter_and_deduplicate(leads: list, count: int) -> list:
    """Filter junk, deduplicate, and clean business names."""
    filtered = []
    seen_domains = set()
    seen_names = set()

    for lead in leads:
        url = lead.get("url", "").lower()
        title = lead.get("title", "")
        snippet = lead.get("snippet", "").lower()

        # Skip empty URLs
        if not url or not url.startswith("http"):
            continue

        # Ban junk domains
        if any(d in url for d in BANNED_DOMAINS):
            continue

        # Ban junk keywords
        if any(p.search(title + " " + snippet) for p in JUNK_COMPILED):
            continue

        # Ban info sites
        info_sites = [".gov", ".edu", "forbes.com", "news.", "blog.", "wiki", "dictionary"]
        if any(site in url for site in info_sites):
            continue

        # Language check: no non-English characters in business name
        if re.search(r'[^\x00-\x7F]+', title):
            continue

        # Deduplicate by domain
        domain = url.split("//")[-1].split("/")[0].replace("www.", "")
        if domain in seen_domains and "yelp.com" not in domain:
            continue
        seen_domains.add(domain)

        # Clean business name
        if "yelp.com/biz/" in url:
            biz_slug = url.split("/biz/")[-1].split("?")[0]
            lead["business"] = re.sub(r'\s+\d+$', '', biz_slug.replace("-", " ").title())
        elif len(title) > 40 or any(x in title.lower() for x in ["best", "top", "how to", "list"]):
            domain_part = domain.split(".")[0]
            lead["business"] = domain_part.replace("-", " ").replace("_", " ").title()
        else:
            lead["business"] = title.split(" - ")[0].split(" | ")[0].strip()

        # Deduplicate by business name
        name_key = lead["business"].lower().strip()
        if name_key in seen_names:
            continue
        seen_names.add(name_key)

        filtered.append(lead)

    return filtered[:count]


async def _source_bbb(query: str, count: int) -> list:
    """
    Finds BBB profile pages via DuckDuckGo and extracts business details.
    Resilient to DDG A/B layout snippets and unwraps redirects.
    """
    import urllib.parse
    leads = []
    try:
        bbb_query = f"site:bbb.org/profile {query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(bbb_query)}"

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(search_url)

        if resp.status_code != 200:
            logger.warning(f"[BBB] DDG returned HTTP {resp.status_code}")
            return leads

        soup = BeautifulSoup(resp.text, "html.parser")

        for r in soup.select("div.result"):
            a_tag = r.select_one("a.result__a")
            if not a_tag:
                continue

            raw_href = a_tag.get("href", "")
            cleaned_url = _clean_ddg_url(raw_href)

            if not cleaned_url or "bbb.org/local-bbb" in cleaned_url:
                continue

            snippet_el = (
                r.select_one("div.result__snippet") or
                r.select_one("a.result__snippet") or
                r.select_one(".result__snippet")
            )
            snippet_text = snippet_el.get_text(strip=True) if snippet_el else ""

            title_text = (
                a_tag.get_text(strip=True)
                .replace("| Better Business Bureau®", "")
                .replace("| Better Business Bureau", "")
                .replace("| BBB", "")
                .strip()
            )

            if not title_text:
                continue

            leads.append({
                "title": title_text,
                "business": title_text,
                "url": cleaned_url,
                "snippet": snippet_text,
                "source_type": "BBB.org",
            })

            if len(leads) >= count:
                break

    except Exception as e:
        logger.error(f"[BBB] Error: {e}")

    return leads[:count]


def _clean_ddg_url(href: str) -> str:
    """Unwraps DDG's redirection links to retrieve the actual outbound business URL."""
    import urllib.parse
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc and "uddg" in parsed.query:
            qs = urllib.parse.parse_qs(parsed.query)
            if "uddg" in qs:
                return urllib.parse.unquote(qs["uddg"][0])
    except Exception:
        pass
    return href



async def research_lead(url: str) -> str:
    """Deep-dive a lead: visit their site, extract key info, score them."""
    logger.info(f"[LEAD RESEARCH] Deep-diving: {url}")
    report = f"# Lead Research: {url}\n\n"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                text = soup.get_text(separator=" ", strip=True)[:3000]
                report += f"## Website Content\n{text}\n\n"
            else:
                report += f"## Website Content\nHTTP {resp.status_code}\n\n"
    except Exception as e:
        report += f"## Website Content\nError: {e}\n\n"

    report += """## Scoring Criteria
- Service alignment with client needs
- Website quality and professionalism
- Business size indicators
- Geographic fit
- Signs of budget for marketing services
"""
    return report
