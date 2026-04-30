import logging
import asyncio
from app.skills.lead_finder import find_leads, read_webpage

logger = logging.getLogger(__name__)


async def deep_research(topic: str, depth: str = "standard") -> str:
    """
    Multi-step autonomous research on a topic.
    Uses web search + page reading to gather comprehensive intelligence.
    Inspired by awesome-claude-skills/deep-research.
    """
    logger.info(f"[DEEP RESEARCH] Starting research on: {topic} (depth={depth})")

    results = {"sources": [], "findings": [], "raw_data": []}
    search_queries = _generate_queries(topic)

    max_queries = 3 if depth == "quick" else 5 if depth == "standard" else 8

    # ── Step 1: Multi-query web search ───────────────────────────────
    for i, query in enumerate(search_queries[:max_queries]):
        logger.info(f"[DEEP RESEARCH] Query {i+1}/{max_queries}: {query}")
        try:
            search_result = await find_leads(count=5, query=query)
            if search_result and "no results" not in search_result.lower():
                results["raw_data"].append(search_result)
                results["sources"].append(f"Search: {query}")
        except Exception as e:
            logger.warning(f"[DEEP RESEARCH] Search failed for '{query}': {e}")

    # ── Step 2: Deep-read top URLs from results ──────────────────────
    urls_to_read = _extract_urls(results["raw_data"])

    for url in urls_to_read[:5]:
        try:
            page_content = await read_webpage(url=url)
            if page_content:
                # Truncate to avoid token overflow
                results["findings"].append(page_content[:2000])
                results["sources"].append(f"Page: {url}")
        except Exception as e:
            logger.warning(f"[DEEP RESEARCH] Failed to read {url}: {e}")

    # ── Step 3: Compile research report ──────────────────────────────
    if not results["raw_data"] and not results["findings"]:
        return f"Research on '{topic}' found no results. Try a broader or different topic."

    report = f"# Deep Research Report: {topic}\n\n"
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

    logger.info(f"[DEEP RESEARCH] Complete. {len(results['sources'])} sources.")
    return report


def _generate_queries(topic: str) -> list:
    """Generate multiple search queries from a topic for broader coverage."""
    base = topic.strip()
    return [
        base,
        f"{base} market analysis 2025",
        f"{base} competitors",
        f"{base} industry trends",
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
