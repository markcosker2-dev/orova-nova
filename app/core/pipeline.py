# -*- coding: utf-8 -*-
"""
OROVA Pipeline Engine — Multi-Step Workflow Orchestration
Inspired by OpenClaw's Lobster macro engine.

Chains multiple skills into autonomous pipelines:
  find leads → research each → draft emails → queue for approval

Each step feeds output to the next, with logging to Mission Control.
"""

import logging
import asyncio
import json
import os
import time
from datetime import datetime

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

PIPELINES = {
    "full_outreach": {
        "name": "Full Outreach Pipeline",
        "description": "Find leads → Research top picks → Draft emails → Queue for CEO approval",
        "steps": [
            {
                "id": "hunt",
                "name": "Hunt Leads",
                "skill": "find_leads",
                "default_args": {"count": 5, "query": "luxury home remodel California"},
                "description": "Search for new business leads"
            },
            {
                "id": "research",
                "name": "Deep Research",
                "skill": "deep_research",
                "uses_previous": True,
                "default_args": {"depth": "standard"},
                "description": "Research the top leads found"
            },
            {
                "id": "draft",
                "name": "Draft Emails",
                "skill": "write_cold_email",
                "uses_previous": True,
                "default_args": {"framework": "pas"},
                "description": "Draft personalized outreach emails"
            },
        ]
    },
    "morning_report": {
        "name": "Morning Report Pipeline",
        "description": "Check replies → Analyze metrics → Generate CEO report",
        "steps": [
            {
                "id": "replies",
                "name": "Check Replies",
                "skill": "check_replies",
                "default_args": {"limit": 20},
                "description": "Check for new prospect replies"
            },
            {
                "id": "analytics",
                "name": "Pipeline Analytics",
                "skill": "pipeline_report",
                "default_args": {},
                "description": "Generate pipeline analytics"
            },
            {
                "id": "report",
                "name": "CEO Report",
                "skill": "weekly_report",
                "default_args": {},
                "description": "Compile the CEO pulse report"
            },
        ]
    },
    "competitor_blitz": {
        "name": "Competitor Blitz Pipeline",
        "description": "Search competitors → SEO audit each → Side-by-side comparison → Strategy report",
        "steps": [
            {
                "id": "find",
                "name": "Find Competitors",
                "skill": "find_leads",
                "default_args": {"count": 5, "query": "top digital marketing agencies California"},
                "description": "Find competing agencies"
            },
            {
                "id": "audit",
                "name": "SEO Audit",
                "skill": "run_seo_audit",
                "uses_previous": True,
                "default_args": {},
                "description": "Audit competitor websites"
            },
            {
                "id": "compare",
                "name": "Compare",
                "skill": "compare_competitors",
                "uses_previous": True,
                "default_args": {},
                "description": "Side-by-side competitor comparison"
            },
        ]
    },
    "lead_enrich": {
        "name": "Lead Enrichment Pipeline",
        "description": "Stealth extract contact info → Score leads → Add to Google Sheet",
        "steps": [
            {
                "id": "extract",
                "name": "Stealth Extract",
                "skill": "stealth_extract",
                "default_args": {},
                "description": "Extract contact info with anti-bot bypass"
            },
            {
                "id": "research",
                "name": "Research Lead",
                "skill": "research_lead",
                "uses_previous": True,
                "default_args": {},
                "description": "Deep-dive and score the lead"
            },
            {
                "id": "save",
                "name": "Save to Sheet",
                "skill": "append_to_sheet",
                "uses_previous": True,
                "default_args": {"sheet_name": "OROVA_Leads"},
                "description": "Append enriched lead to Google Sheet"
            },
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

# Global state for tracking running pipelines
_active_pipelines = {}


async def run_pipeline(pipeline_name: str, params: str = "") -> str:
    """
    Execute a multi-step pipeline by name.

    Args:
        pipeline_name: One of: full_outreach, morning_report, competitor_blitz, lead_enrich
        params: Optional JSON string of parameter overrides

    Returns:
        Combined pipeline output report
    """
    pipeline = PIPELINES.get(pipeline_name)
    if not pipeline:
        available = ", ".join(PIPELINES.keys())
        return f"⚠️ Unknown pipeline '{pipeline_name}'. Available: {available}"

    # Parse optional params
    try:
        overrides = json.loads(params) if params else {}
    except json.JSONDecodeError:
        overrides = {}

    logger.info(f"[PIPELINE] Starting: {pipeline['name']} ({len(pipeline['steps'])} steps)")

    run_id = f"pipeline_{int(time.time())}"
    _active_pipelines[run_id] = {
        "name": pipeline_name,
        "status": "running",
        "started": datetime.now().isoformat(),
        "current_step": 0,
        "total_steps": len(pipeline["steps"]),
        "results": []
    }

    report = f"# 🔄 Pipeline: {pipeline['name']}\n"
    report += f"**Description:** {pipeline['description']}\n"
    report += f"**Steps:** {len(pipeline['steps'])}\n"
    report += f"**Run ID:** `{run_id}`\n\n"

    previous_output = ""

    for i, step in enumerate(pipeline["steps"]):
        step_num = i + 1
        _active_pipelines[run_id]["current_step"] = step_num

        report += f"---\n"
        report += f"## Step {step_num}/{len(pipeline['steps'])}: {step['name']}\n"
        report += f"*{step['description']}*\n\n"

        try:
            # Build arguments
            args = {**step.get("default_args", {}), **overrides.get(step["id"], {})}

            # If step uses previous output, inject it
            if step.get("uses_previous") and previous_output:
                # Smart injection: use previous output as the primary argument
                if "topic" in _get_skill_args(step["skill"]):
                    args["topic"] = previous_output[:500]
                elif "query" in _get_skill_args(step["skill"]):
                    args["query"] = previous_output[:200]
                elif "url" in _get_skill_args(step["skill"]):
                    # Extract first URL from previous output
                    import re
                    urls = re.findall(r'https?://[^\s\)]+', previous_output)
                    if urls:
                        args["url"] = urls[0]
                elif "prospect" in _get_skill_args(step["skill"]):
                    args["prospect"] = previous_output[:300]
                elif "companies" in _get_skill_args(step["skill"]):
                    args["companies"] = previous_output[:300]

            # Execute the skill
            result = await _execute_skill(step["skill"], args)
            previous_output = str(result)

            report += f"✅ **Completed**\n\n"
            # Include truncated result
            result_preview = str(result)[:500]
            report += f"```\n{result_preview}\n```\n\n"

            _active_pipelines[run_id]["results"].append({
                "step": step["id"],
                "status": "success",
                "output_length": len(str(result))
            })

        except Exception as e:
            logger.error(f"[PIPELINE] Step {step_num} failed: {e}")
            report += f"❌ **Failed:** {str(e)}\n\n"
            _active_pipelines[run_id]["results"].append({
                "step": step["id"],
                "status": "error",
                "error": str(e)
            })
            # Continue to next step even on failure

    # Mark complete
    _active_pipelines[run_id]["status"] = "completed"
    _active_pipelines[run_id]["completed"] = datetime.now().isoformat()

    report += "---\n"
    report += f"## ✅ Pipeline Complete\n"
    successes = sum(1 for r in _active_pipelines[run_id]["results"] if r["status"] == "success")
    report += f"**Results:** {successes}/{len(pipeline['steps'])} steps succeeded\n"

    logger.info(f"[PIPELINE] Completed: {pipeline['name']} ({successes}/{len(pipeline['steps'])} OK)")
    return report


def _get_skill_args(skill_name: str) -> list:
    """Get expected argument names for a skill function."""
    # Known argument patterns for routing
    arg_map = {
        "find_leads": ["query", "count"],
        "deep_research": ["topic", "depth"],
        "research_lead": ["url"],
        "stealth_search": ["query", "count"],
        "stealth_extract": ["url", "selectors"],
        "write_cold_email": ["prospect", "framework"],
        "run_seo_audit": ["url"],
        "analyze_competitor": ["company_name"],
        "compare_competitors": ["companies"],
        "check_replies": ["limit"],
        "pipeline_report": [],
        "weekly_report": [],
        "append_to_sheet": ["sheet_name", "rows"],
        "bulk_scrape": ["urls", "objective"],
    }
    return arg_map.get(skill_name, [])


async def _execute_skill(skill_name: str, args: dict):
    """Dynamic skill executor — imports and calls the skill function."""
    # Skill registry mapping names to import paths
    skill_map = {
        "find_leads": ("app.skills.lead_finder", "find_leads"),
        "deep_research": ("app.skills.deep_research", "deep_research"),
        "research_lead": ("app.skills.lead_finder", "research_lead"),
        "stealth_search": ("app.skills.scrapling_scraper", "stealth_search"),
        "stealth_extract": ("app.skills.scrapling_scraper", "stealth_extract"),
        "bulk_scrape": ("app.skills.scrapling_scraper", "bulk_scrape"),
        "write_cold_email": ("app.skills.copywriting_skill", "write_cold_email"),
        "run_seo_audit": ("app.skills.seo_audit", "run_seo_audit"),
        "analyze_competitor": ("app.skills.competitive_intel", "analyze_competitor"),
        "compare_competitors": ("app.skills.competitive_intel", "compare_competitors"),
        "check_replies": ("app.skills.agentmail_skill", "check_replies"),
        "pipeline_report": ("app.skills.analytics_skill", "pipeline_report"),
        "weekly_report": ("app.skills.perf_dashboard", "generate_weekly_report"),
        "append_to_sheet": ("app.skills.sheets_skill", "append_to_sheet"),
    }

    if skill_name not in skill_map:
        raise ValueError(f"Unknown skill: {skill_name}")

    module_path, func_name = skill_map[skill_name]

    import importlib
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)

    # Execute (handle both sync and async)
    if asyncio.iscoroutinefunction(func):
        return await func(**args)
    else:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(**args))


async def list_pipelines() -> str:
    """List all available pipelines with their descriptions."""
    report = "# 🔄 Available Pipelines\n\n"
    for key, pipeline in PIPELINES.items():
        steps = " → ".join(s["name"] for s in pipeline["steps"])
        report += f"### `{key}` — {pipeline['name']}\n"
        report += f"*{pipeline['description']}*\n"
        report += f"Steps: {steps}\n\n"
    return report


def get_pipeline_status() -> dict:
    """Get status of all active/recent pipelines (for Dashboard API)."""
    return _active_pipelines
