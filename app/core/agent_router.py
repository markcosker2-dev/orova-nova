# -*- coding: utf-8 -*-
"""
OROVA Sub-Agent Dispatcher
Routes tasks to the correct specialized agent based on intent.
Tracks live agent status for the Mission Control Digital Office.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

STATUS_FILE = Path(__file__).parent.parent / "agent_status.json"

# ── Agent Definitions ────────────────────────────────────────────
AGENTS = {
    "nova": {
        "name": "Nova",
        "role": "CEO & Director",
        "dept": "Leadership",
        "skills": ["planner", "router"],
        "keywords": ["orchestrate", "strategy", "plan", "status", "report"],
        "model": "deepseek/deepseek-r1:free",
    },
    "atlas": {
        "name": "Atlas",
        "role": "Lead Developer",
        "dept": "Engineering",
        "skills": ["arsenal_skills", "browser_ops", "browser_skill"],
        "keywords": ["build", "code", "deploy", "fix", "api", "tool", "scrape"],
        "model": "qwen/qwen-2.5-coder-32b:free",
    },
    "pixel": {
        "name": "Pixel",
        "role": "Creative Director",
        "dept": "Creative",
        "skills": ["image_gen", "instagram_skill"],
        "keywords": ["image", "instagram", "post", "design", "visual", "content calendar", "brand"],
        "model": "mistralai/mistral-small:free",
    },
    "quill": {
        "name": "Quill",
        "role": "Content Strategist",
        "dept": "Creative",
        "skills": ["content_writer", "orova_sales_core", "follow_up_sequences"],
        "keywords": ["write", "email", "copy", "blog", "script", "sequence", "follow-up", "followup", "newsletter"],
        "model": "google/gemini-2.0-flash-lite-preview-02-05:free",
    },
    "hawk": {
        "name": "Hawk",
        "role": "Lead Hunter",
        "dept": "Sales",
        "skills": ["lead_finder", "deep_research", "meta_ads_audit", "competitive_intel"],
        "keywords": ["lead", "find", "search", "hunt", "research", "meta", "facebook", "instagram", "ads", "advertising", "competitor", "prospect"],
        "model": "meta-llama/llama-3.1-70b-instruct:free",
    },
    "closer": {
        "name": "Closer",
        "role": "Sales Director",
        "dept": "Sales",
        "skills": ["agentmail_skill", "outbound_dialer", "calendar_skill", "proposal_gen"],
        "keywords": ["call", "dial", "outreach", "send", "proposal", "appointment", "book", "meeting", "calendar", "close"],
        "model": "meta-llama/llama-3.1-8b-instruct:free",
    },
    "sentinel": {
        "name": "Sentinel",
        "role": "Operations Manager",
        "dept": "Operations",
        "skills": ["scheduler_skill", "sheets_skill", "approval_workflow", "notes_skill", "perf_dashboard"],
        "keywords": ["schedule", "sheet", "crm", "approve", "note", "task", "metric", "dashboard", "performance", "report"],
        "model": "google/gemini-2.0-flash-lite-preview-02-05:free",
    },
    "echo": {
        "name": "Echo",
        "role": "Client Success",
        "dept": "Operations",
        "skills": ["gmail_skill"],
        "keywords": ["reply", "inbox", "client", "respond", "nurture", "gmail", "support"],
        "model": "deepseek/deepseek-chat:free",
    },
    "oracle": {
        "name": "Oracle",
        "role": "Data Intelligence",
        "dept": "Analytics",
        "skills": ["analytics_skill", "perf_dashboard", "meta_ads_skill"],
        "keywords": ["data", "analytics", "metrics", "roi", "funnel", "conversion", "trend", "a/b", "kpi", "report data", "numbers", "ads", "meta", "facebook", "cpl", "spend"],
        "model": "deepseek/deepseek-r1:free",
    },
    "viper": {
        "name": "Viper",
        "role": "Stealth Ops",
        "dept": "Intelligence",
        "skills": ["scrapling_scraper", "browser_ops"],
        "keywords": ["stealth", "extract", "proxy", "bypass", "crawl", "anti-bot", "bulk scrape", "scrape site", "blocked"],
        "model": "google/gemini-2.0-flash-lite-preview-02-05:free",
    },
}


def classify_agent(task_description: str) -> str:
    """
    Determine which agent should handle a task based on keyword matching.
    Returns the agent ID.
    """
    task_lower = task_description.lower()
    scores = {}

    for agent_id, agent in AGENTS.items():
        score = sum(1 for kw in agent["keywords"] if kw in task_lower)
        if score > 0:
            scores[agent_id] = score

    if not scores:
        return "nova"  # Default to CEO for unclassified tasks

    return max(scores, key=scores.get)


def get_agent_info(agent_id: str) -> dict:
    """Get full info about an agent."""
    return AGENTS.get(agent_id, AGENTS.get("nova"))


def update_agent_status(agent_id: str, status: str = "working", current_task: str = ""):
    """
    Update an agent's live status for the Digital Office.

    Args:
        agent_id: Agent identifier
        status: 'working', 'idle', or 'offline'
        current_task: Description of what they're doing
    """
    statuses = _load_statuses()
    statuses[agent_id] = {
        "status": status,
        "current_task": current_task,
        "last_updated": datetime.now().isoformat(),
    }
    _save_statuses(statuses)
    logger.info(f"[DISPATCH] {AGENTS.get(agent_id, {}).get('name', agent_id)} → {status}: {current_task}")


def get_all_statuses() -> dict:
    """Get the live status of all agents."""
    statuses = _load_statuses()
    result = {}
    for agent_id, agent in AGENTS.items():
        s = statuses.get(agent_id, {"status": "idle", "current_task": "", "last_updated": ""})
        result[agent_id] = {**agent, **s}
    return result


def dispatch_task(task_description: str) -> dict:
    """
    Route a task to the correct agent and update status.

    Returns:
        dict with assigned_agent, agent_info, and recommended_skills
    """
    agent_id = classify_agent(task_description)
    agent = AGENTS[agent_id]

    update_agent_status(agent_id, "working", task_description[:80])

    logger.info(f"[DISPATCH] Task routed to {agent['name']} ({agent['role']}): {task_description[:60]}...")

    return {
        "assigned_agent": agent_id,
        "agent_name": agent["name"],
        "agent_role": agent["role"],
        "department": agent["dept"],
        "recommended_skills": agent["skills"],
        "task": task_description,
    }


def _load_statuses() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_statuses(statuses: dict):
    STATUS_FILE.write_text(json.dumps(statuses, indent=2))
