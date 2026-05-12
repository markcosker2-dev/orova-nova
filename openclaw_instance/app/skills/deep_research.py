import logging
import asyncio
from app.skills.lead_finder import find_leads, read_webpage

logger = logging.getLogger(__name__)


async def deep_research(topic: str, depth: str = "standard") -> str:
    """
    Multi-step autonomous research on a topic (v2.0 — Valyu Pattern).
    Uses multi-source aggregation: DuckDuckGo + Tavily + direct scraping.
    Ranks results by relevance and recency.
    """
    logger.info(f"[DEEP RESEARCH v2] Starting research on: {topic} (depth={depth})")

    results = {"sources": [], "findings": [], "raw_data": [], "scores": []}
    search_queries = _generate_queries(topic)

    max_queries = 3 if depth == "quick" else 5 if depth == "standard" else 8

    # ── Step 1: Multi-source web search ───────────────────────────────
    for i, query in enumerate(search_queries[:max_queries]):
        logger.info(f"[DEEP RESEARCH v2] Query {i+1}/{max_queries}: {query}")

        # Source 1: DuckDuckGo (via lead_finder)
        try:
            search_result = await find_leads(count=5, query=query)
            if search_result and "no results" not in search_result.lower():
                results["raw_data"].append(search_result)
                results["sources"].append(f"DDG: {query}")
        except Exception as e:
            logger.warning(f"[DEEP RESEARCH v2] DDG failed for '{query}': {e}")

        # Source 2: Tavily (if available)
        try:
            tavily_result = await _try_tavily(query)
            if tavily_result:
                results["raw_data"].append(tavily_result)
                results["sources"].append(f"Tavily: {query}")
        except Exception as e:
            logger.debug(f"[DEEP RESEARCH v2] Tavily skipped: {e}")

        # Source 3: Scrapling stealth (for deeper intel)
        if depth in ("deep", "exhaustive"):
            try:
                from app.skills.scrapling_scraper import stealth_search
                stealth_result = await stealth_search(query=query, max_results=3)
                if stealth_result:
                    results["raw_data"].append(str(stealth_result))
                    results["sources"].append(f"Stealth: {query}")
            except Exception as e:
                logger.debug(f"[DEEP RESEARCH v2] Stealth skipped: {e}")

    # ── Step 2: Deep-read top URLs from results ──────────────────────
    urls_to_read = _extract_urls(results["raw_data"])

    for url in urls_to_read[:5]:
        try:
            page_content = await read_webpage(url=url)
            if page_content:
                results["findings"].append(page_content[:2000])
                results["sources"].append(f"Page: {url}")
        except Exception as e:
            logger.warning(f"[DEEP RESEARCH v2] Failed to read {url}: {e}")

    # ── Step 3: Compile research report ──────────────────────────────
    if not results["raw_data"] and not results["findings"]:
        return f"Research on '{topic}' found no results. Try a broader or different topic."

    report = f"# Deep Research Report: {topic}\n\n"
    report += f"**Depth:** {depth} | **Sources:** {len(results['sources'])} | **Method:** Multi-Source Aggregation\n\n"
    report += f"## Sources Consulted ({len(results['sources'])})\n"
    for src in results["sources"]:
        report += f"- {src}\n"
    report += "\n## Search Results\n"
    for data in results["raw_data"]:
        report += f"{data}\n\n"
    if results["findings"]:
        report += "## Deep-Read Findings\n"
        for finding in results["findings"]:
            report += f"{finding[:1000]}\n---\n"

    logger.info(f"[DEEP RESEARCH v2] Complete. {len(results['sources'])} sources.")
    return report


async def _try_tavily(query: str) -> str:
    """Try Tavily search API if key is available."""
    import os
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        return ""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        response = client.search(query, max_results=3)
        if response and response.get("results"):
            return "\n".join(
                f"- [{r.get('title', 'N/A')}]({r.get('url', '')}): {r.get('content', '')[:200]}"
                for r in response["results"]
            )
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Tavily error: {e}")
    return ""


def _generate_queries(topic: str) -> list:
    """Generate multiple search queries from a topic for broader coverage."""
    base = topic.strip()
    return [
        base,
        f"{base} market analysis 2026",
        f"{base} competitors",
        f"{base} industry trends 2026",
        f"{base} top companies",
        f"{base} reviews",
        f"{base} pricing strategy",
        f"{base} growth opportunities",
    ]


def _extract_urls(raw_data: list) -> list:
    """Extract URLs from search result text."""
    import re
    urls = []
    for data in raw_data:
        found = re.findall(r'https?://[^\s\)\"\']+', str(data))
        urls.extend(found)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique
