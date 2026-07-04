"""
agent_router.py — OROVA HAWK Lead Scoring & Routing
Calibrated for high-ticket luxury sectors (2026 standards).
"""

import logging

logger = logging.getLogger(__name__)

# ── [P8] HAWK SCORING WEIGHTS ──
# Critical: Aesthetic and networking activity dominate luxury leads.
SCORING_WEIGHTS = {
    "revenue": 0.2,           # Baseline qualification
    "linkedin_activity": 0.3, # Active founders are easier to close
    "aesthetic_score": 0.5    # Luxury brands must look the part
}

def calculate_hawk_score(lead_data: dict) -> dict:
    """Calculates weighted HAWK score with deep reasoning."""
    score = 0.0
    reasons = []

    # 1. Revenue Tier
    if lead_data.get("revenue_tier") == "high":
        score += 10 * SCORING_WEIGHTS["revenue"]

    # 2. LinkedIn Activity
    if lead_data.get("linkedin_active"):
        score += 10 * SCORING_WEIGHTS["linkedin_activity"]
        reasons.append("Founder active on LinkedIn")

    # 3. Aesthetic / Vision Check
    aesthetic_val = lead_data.get("vision_aesthetic_score", 0)
    score += aesthetic_val * SCORING_WEIGHTS["aesthetic_score"]
    
    if aesthetic_val >= 8:
        reasons.append("Premium website aesthetic confirmed")
    elif aesthetic_val < 5:
        reasons.append("Sub-par web presence (Detractor)")

    final_score = round(score, 1)
    reasoning = f"Score {final_score}: Reason - {' + '.join(reasons)}"

    return {
        "score": final_score,
        "reasoning": reasoning,
        "is_qualified": final_score >= 7.0
    }

async def route_task(task_description: str):
    """[P8] New: Surgically route or score tasks."""
    return {"status": "ok", "action": "nova_direct"}

_KNOWN_AGENTS = {"nova", "atlas", "pixel", "quill", "hawk", "closer",
                 "sentinel", "echo", "oracle", "viper"}

async def dispatch_task(task: str = "", agent: str = "nova", client_id: int = 0,
                        task_description: str = ""):
    """Delegate a task to a specialised sub-agent.

    Each sub-agent is a scoped run of the planner: its persona
    (app/personas/<agent>.md) is injected and its toolset is restricted to its
    role (Hawk hunts, Quill/Closer do outreach, Atlas builds). Single-process —
    no extra RAM — so it runs fine on Render free tier. `task_description` is
    accepted as an alias for `task` (older tool schema).
    """
    task = task or task_description
    agent = (agent or "nova").strip().lower()
    if not task:
        return {"status": "error", "agent": agent, "response": "No task provided."}
    if agent not in _KNOWN_AGENTS:
        return {"status": "error", "agent": agent,
                "response": f"Unknown agent '{agent}'. Known: {sorted(_KNOWN_AGENTS)}"}
    logger.info(f"[Router] Dispatching to sub-agent '{agent}': {task[:80]}")
    try:
        from app.core.planner import TaskPlanner
        from app.core.ai_client import UnifiedAIClient
        planner = TaskPlanner(UnifiedAIClient())
        return await planner.execute(task, client_id=client_id, agent_id=agent)
    except Exception as e:
        logger.error(f"[Router] Sub-agent dispatch failed for '{agent}': {e}", exc_info=True)
        return {"status": "error", "agent": agent, "response": "Sub-agent dispatch failed."}

def get_all_statuses():
    """[LEGACY] Compatibility for Planner imports."""
    return {"nova": "online", "swarm": "active"}
