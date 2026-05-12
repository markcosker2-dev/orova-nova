# -*- coding: utf-8 -*-
"""
OROVA Cipher Agent — Competitive Intelligence (Elite Feature 3)
================================================================
Monitors competitive landscape in real time, delivering actionable
intelligence that keeps OROVA's outreach sharper than any human
competitor can match.

Daily Tasks:
1. Monitor target vertical keywords for competitor positioning shifts
2. Track pricing signals from competing agencies
3. Flag when an OROVA lead is being targeted by a competitor
4. Generate weekly Competitive Edge Report
"""

import logging
import asyncio
import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# KNOWN COMPETITORS (seed list — expands via discovery)
# ═══════════════════════════════════════════════════════════════════════════════

KNOWN_COMPETITORS = [
    "homeadvisor",
    "angi",
    "thumbtack",
    "bark.com",
    "taskrabbit",
    "networx",
    "porch.com",
    "houzz",
    "buildzoom",
    "modernize",
]

# Keywords to monitor for competitor positioning shifts
MONITOR_KEYWORDS = [
    "AI lead generation agency",
    "automated lead generation",
    "AI appointment setting",
    "contractor lead generation",
    "HVAC lead generation",
    "roofing lead generation",
    "home renovation leads",
    "exclusive leads contractors",
]


# ═══════════════════════════════════════════════════════════════════════════════
# CIPHER AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class CipherAgent:
    """
    Competitive Intelligence Agent.
    Monitors competitors, tracks pricing signals, and flags threats.
    """

    @staticmethod
    async def run_daily_sweep() -> Dict:
        """
        Daily competitive intelligence sweep.
        Called by scheduler at 08:05 ET.

        Returns:
            Dict with findings summary
        """
        logger.info("[CIPHER] Running daily competitive intelligence sweep...")
        findings = {
            "timestamp": datetime.datetime.now().isoformat(),
            "competitor_mentions": [],
            "pricing_signals": [],
            "lead_conflicts": [],
            "summary": "",
        }

        try:
            # Search for competitor activity
            for keyword in MONITOR_KEYWORDS[:3]:  # Limit to avoid rate limits
                results = await _search_competitors(keyword)
                if results:
                    findings["competitor_mentions"].extend(results)
                await asyncio.sleep(2)  # Rate limit

            # Check if any of our leads are being targeted
            lead_conflicts = await _check_lead_conflicts()
            findings["lead_conflicts"] = lead_conflicts

            # Generate summary
            total_mentions = len(findings["competitor_mentions"])
            total_conflicts = len(findings["lead_conflicts"])
            findings["summary"] = (
                f"Sweep complete. {total_mentions} competitor mentions detected. "
                f"{total_conflicts} lead conflicts flagged."
            )

            logger.info(f"[CIPHER] {findings['summary']}")

        except Exception as e:
            logger.error(f"[CIPHER] Daily sweep failed: {e}")
            findings["summary"] = f"Sweep failed: {str(e)}"

        return findings

    @staticmethod
    async def check_lead_competitor_overlap(lead_company: str) -> Optional[Dict]:
        """
        Check if a specific lead company is being targeted by a known competitor.
        Cross-references DuckDuckGo searches on the lead company name.

        Args:
            lead_company: Company name to check

        Returns:
            Dict with competitor info if overlap found, None otherwise
        """
        try:
            results = await _search_competitors(
                f'"{lead_company}" lead generation marketing agency'
            )
            if results:
                return {
                    "company": lead_company,
                    "competitors_found": results,
                    "action": "accelerate_sequence",
                    "recommendation": (
                        f"{lead_company} is being targeted by competitors. "
                        "Accelerate sequence by 48 hours and upgrade to "
                        "Autonomous Appointment Setting flow immediately."
                    ),
                }
        except Exception as e:
            logger.warning(f"[CIPHER] Competitor check failed for {lead_company}: {e}")

        return None

    @staticmethod
    def generate_weekly_report(findings_history: List[Dict] = None) -> str:
        """
        Generate the weekly Competitive Edge Report for Monday MISSION PULSE.

        Args:
            findings_history: List of daily sweep results from the past week

        Returns:
            Formatted report string
        """
        now = datetime.datetime.now()
        week_start = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        week_end = now.strftime("%Y-%m-%d")

        report = (
            f"COMPETITIVE EDGE REPORT\n"
            f"────────────────────────────────────────\n"
            f"Period: {week_start} to {week_end}\n"
            f"Agent: Cipher\n"
            f"────────────────────────────────────────\n\n"
        )

        if findings_history:
            total_sweeps = len(findings_history)
            total_mentions = sum(
                len(f.get("competitor_mentions", [])) for f in findings_history
            )
            total_conflicts = sum(
                len(f.get("lead_conflicts", [])) for f in findings_history
            )

            report += f"Sweeps Completed: {total_sweeps}\n"
            report += f"Competitor Mentions: {total_mentions}\n"
            report += f"Lead Conflicts: {total_conflicts}\n\n"

            # Top competitors by mention count
            competitor_counts = {}
            for f in findings_history:
                for mention in f.get("competitor_mentions", []):
                    name = mention.get("competitor", "Unknown")
                    competitor_counts[name] = competitor_counts.get(name, 0) + 1

            if competitor_counts:
                report += "Top Competitor Activity:\n"
                for comp, count in sorted(
                    competitor_counts.items(), key=lambda x: x[1], reverse=True
                )[:5]:
                    report += f"  — {comp}: {count} mentions\n"
                report += "\n"
        else:
            report += "No sweep data available for this period.\n"
            report += "Cipher sweeps will begin accumulating data this week.\n\n"

        report += (
            "────────────────────────────────────────\n"
            "Recommendation: Monitor lead pipeline for competitor overlap.\n"
            "When overlap detected, accelerate sequence by 48 hours.\n"
            "────────────────────────────────────────\n"
            "Prepared by Cipher — OROVA Competitive Intelligence"
        )

        return report


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL SEARCH FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def _search_competitors(query: str) -> List[Dict]:
    """
    Search DuckDuckGo for competitor mentions.
    AUDIT FIX: Uses DDGS library with built-in rate-limit handling.
    """
    results_out = []
    
    def _do_search():
        from duckduckgo_search import DDGS
        import time
        for attempt in range(3):
            try:
                # We do a basic text search
                with DDGS() as ddgs:
                    # Request up to 5 results
                    return list(ddgs.text(query, max_results=5))
            except Exception as e:
                err = str(e).lower()
                if "ratelimit" in err or "202" in err:
                    wait = (attempt + 1) * 15
                    logger.warning(f"[CIPHER] DDG rate limited, waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"[CIPHER] Search failed (attempt {attempt+1}): {e}")
                    if attempt == 2:
                        return []
                    time.sleep(5)
        return []

    try:
        raw_results = await asyncio.to_thread(_do_search)
        
        # Parse results for competitor mentions
        for r in raw_results:
            text = (r.get("body", "") + " " + r.get("title", "")).lower()
            for competitor in KNOWN_COMPETITORS:
                if competitor in text:
                    results_out.append({
                        "competitor": competitor,
                        "query": query,
                        "detected_in": "search_results",
                        "timestamp": datetime.datetime.now().isoformat(),
                    })
    except ImportError:
        logger.warning("[CIPHER] duckduckgo-search not available. Please install ddgs.")
    except Exception as e:
        logger.warning(f"[CIPHER] Search failed: {e}")

    return results_out


async def _check_lead_conflicts() -> List[Dict]:
    """
    Check if any active OROVA leads are being targeted by competitors.
    Cross-references lead company names against competitor search results.
    """
    conflicts = []
    try:
        from app.core.database import DatabaseManager

        # Get active high-score leads
        leads = DatabaseManager.query(
            """SELECT business, vertical FROM leads 
               WHERE score >= 70 
               AND status NOT IN ('DNC', 'Archived', 'Closed Won')
               LIMIT 10""",
            fetchall=True,
        )

        if not leads:
            return conflicts

        for lead in leads:
            lead_dict = dict(lead)
            company = lead_dict.get("business", "")
            if not company or len(company) < 3:
                continue

            # Quick check — just look for the company name near competitor names
            overlap = await CipherAgent.check_lead_competitor_overlap(company)
            if overlap:
                conflicts.append(overlap)

            await asyncio.sleep(1)  # Rate limit

    except Exception as e:
        logger.warning(f"[CIPHER] Lead conflict check failed: {e}")

    return conflicts
