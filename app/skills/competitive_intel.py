import logging
from app.skills.lead_finder import find_leads
from app.skills.browser_ops import browse_and_extract

logger = logging.getLogger(__name__)


async def analyze_competitor(company_name: str) -> str:
    """
    Analyze a competitor's online presence, messaging, and strategy.
    Inspired by awesome-claude-skills/competitive-ads-extractor.
    """
    logger.info(f"[COMPETITIVE INTEL] Analyzing: {company_name}")

    report = f"# Competitive Analysis: {company_name}\n\n"
    sections = []

    # ── Search for competitor info ───────────────────────────────────
    queries = [
        f"{company_name} company overview",
        f"{company_name} ads marketing strategy",
        f"{company_name} reviews ratings",
    ]

    for query in queries:
        try:
            result = await find_leads(count=5, query=query)
            if result and "no results" not in result.lower():
                sections.append(f"### Search: {query}\n{result}\n")
        except Exception as e:
            logger.warning(f"[COMPETITIVE INTEL] Search failed: {e}")

    # ── Try to read competitor website ───────────────────────────────
    try:
        site_result = await find_leads(count=3, query=f"{company_name} official website")
        if site_result:
            import re
            urls = re.findall(r'https?://[^\s\)\"\']+', str(site_result))
            for url in urls[:2]:
                try:
                    page = await browse_and_extract(url=url)
                    if page:
                        sections.append(f"### Website Content: {url}\n{page[:1500]}\n")
                except Exception:
                    pass
    except Exception:
        pass

    if sections:
        report += "\n".join(sections)
    else:
        report += f"No competitive data found for '{company_name}'. Try a more specific company name."

    report += "\n## OROVA Differentiation Opportunities\n"
    report += "- Analyze the above data to identify gaps in their offering\n"
    report += "- Look for service areas they don't cover\n"
    report += "- Note their pricing strategy and positioning\n"

    return report


async def compare_competitors(companies: str) -> str:
    """
    Compare multiple competitors side-by-side.
    Pass company names as comma-separated string.
    """
    company_list = [c.strip() for c in companies.split(",") if c.strip()]
    logger.info(f"[COMPETITIVE INTEL] Comparing: {company_list}")

    if not company_list:
        return "Please provide company names separated by commas."

    report = "# Competitor Comparison\n\n"

    for company in company_list[:5]:  # Max 5 companies
        try:
            analysis = await analyze_competitor(company)
            report += f"\n---\n{analysis}\n"
        except Exception as e:
            report += f"\n## {company}\nAnalysis failed: {e}\n"

    report += "\n---\n## Summary\n"
    report += f"Compared {len(company_list)} competitors. Review above for OROVA positioning opportunities."

    return report
