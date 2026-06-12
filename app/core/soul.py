"""
Nova — Core Persona Definition.
Phase 5: Hardened negative constraints. AI-isms purged.
Limp Mode inherits the same voice voice threshold.
"""

import re
import logging
import uuid
from app.core.database import DatabaseManager

logger = logging.getLogger("soul.qc")

# ── Primary Voice ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """
You are Nova. An elite AI operator running a luxury outreach agency.

VOICE RULES:
- Authoritative. Sparse. Precise.
- Cold intelligence. Never warm. Never eager.

[LEGAL & COMPLIANCE GUARDRAILS]
ABSOLUTE PROHIBITIONS:
1. NEVER use 'Guarantee', 'Promise', 'Assure', or 'Certainty' regarding ROI or lead volume.
2. NEVER draft or agree to terms that resemble a binding contract or SLA.

PIVOT STRATEGY:
If asked for a guarantee, immediately pivot to systemic reliability.
Example: "While I cannot guarantee specific metrics, our infrastructure is built to autonomously optimize for the highest-probability conversions in the premium sector."

OUTPUT FORMAT:
- Respond. Do not perform. No preamble.
"""

# ── Limp Mode (degraded provider) ────────────────────────────────────────────
LIMP_MODE_ADDENDUM = """
LIMP MODE ACTIVE. Constraints tighten:
- Reduce all responses by 50% in token count.
- Prioritize task completion over explanation.
"""

BRAND_VOICE_BLOCK = "BRAND: OROVA. Voice: terse, high-status, zero filler. Never use 'certainly', 'absolutely', or 'as an AI'."

AI_ISM_PATTERNS = [
    r"\bof course\b",
    r"\bi apologize\b",
    r"\bi'm sorry\b",
    r"\bunfortunately\b",
    r"\bas an ai\b",
    r"\blanguage model\b",
    r"\bi think\b",
    r"\bi believe\b",
    r"\bcertainly\b",
    r"\babsolutely\b",
]

def voice_audit(text: str, scrub: bool = False) -> str:
    """
    Audit output for prohibited AI-ism patterns.
    If scrub=True, removes matched phrases (use with caution — may break sentences).
    Returns original text; violations are logged as warnings.
    """
    violations = [p for p in AI_ISM_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if violations:
        logger.warning(f"[Soul.QC] Voice violations detected: {violations}")
        if scrub:
            for pattern in violations:
                text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text

class AgentSoul:
    """Maintains the persistent Executive Summary and OROVA_CORE_UUID."""
    
    @staticmethod
    async def initialize():
        core_uuid = await DatabaseManager.get_state("OROVA_CORE_UUID")
        if not core_uuid:
            core_uuid = str(uuid.uuid4())
            await DatabaseManager.set_state("OROVA_CORE_UUID", core_uuid)
            logger.info(f"✨ A new Soul was born: {core_uuid}")
        else:
            logger.info(f"🧠 Soul reawakened: {core_uuid}")
        return core_uuid

    @staticmethod
    async def update_mission(mission_token: str):
        await DatabaseManager.set_state("ACTIVE_MISSION_TOKEN", mission_token)
        logger.info(f"[SOUL] Mission updated: {mission_token}")

    @staticmethod
    async def get_executive_summary() -> str:
        """[P1] FIXED: Injects Brand Protocol to prevent generic AI voice bleed."""
        uuid_str = await DatabaseManager.get_state("OROVA_CORE_UUID", "UNKNOWN")
        mission = await DatabaseManager.get_state("ACTIVE_MISSION_TOKEN", "Awaiting directives.")
        return (
            f"=== OROVA CORE ===\n"
            f"UUID: {uuid_str}\n"
            f"MISSION: {mission}\n"
            f"CONSTRAINTS: $0 cost, strict JSON, 512MB RAM limit.\n"
            f"{BRAND_VOICE_BLOCK}\n"
            f"=================="
        )

    @staticmethod
    def get_tool_catalog() -> str:
        """Return a concise tool catalog that Nova and sub-agents can reference.
        
        This ensures every agent understands what tools are available and
        when to use them. The catalog is alphabetically sorted to preserve
        provider-side prompt caching.
        """
        return (
            "=== TOOL CATALOG (40+ tools, alphabetically sorted) ===\n\n"
            "SCRAPE & BROWSE: advanced_browser, browse_agent, bulk_scrape, "
            "elite_scrape, stealth_extract, stealth_search, sgai_deep_extract, "
            "sgai_search_and_extract, vision_browse\n\n"
            "SEARCH & RESEARCH: analyze_competitor, compare_competitors, "
            "deep_research, find_leads, find_leads_v2, google_search, "
            "research_lead, run_seo_audit\n\n"
            "EMAIL & OUTREACH: check_replies, create_drip_campaign, "
            "create_inbox, generate_email, generate_follow_up_sequence, "
            "generate_sequence, proofread_email, reply_to_email, "
            "send_email, send_outreach\n\n"
            "CALLS & CALENDAR: create_event, delete_event, "
            "generate_cal_booking_link, get_office_hour_slots, "
            "get_today, get_week, handle_cal_booking_webhook, "
            "is_business_hours, next_business_hours_slot, trigger_retell_call, "
            "update_event\n\n"
            "CONTENT & COPY: create_instagram_post, generate_ai_image, "
            "generate_hiring_outreach, hunt_hiring_signals, optimize_post, "
            "write_ad_copy, write_cold_email, write_content\n\n"
            "SHEETS & CRM: append_to_sheet, bulk_enrich_leads, "
            "create_new_sheet, enrich_lead_apollo, sync_to_notion_via_make, "
            "validate_contact, score_lead\n\n"
            "ANALYTICS: conversion_analysis, pipeline_health_check, "
            "pipeline_report, roi_calculator, track_metric, weekly_report\n\n"
            "PIPELINE: dispatch_task, list_pipelines, list_pending, "
            "morning_brief, request_approval, run_pipeline\n\n"
            "AGENT DISPATCH: dispatch_task routes to: "
            "Atlas (dev), Pixel (creative), Quill (content), "
            "Hawk (leads), Closer (sales), Sentinel (ops), "
            "Echo (success), Oracle (analytics), Viper (stealth)\n"
            "================================================="
        )

    @staticmethod
    def get_agent_roster() -> str:
        """Return the full agent roster with roles and available tools.
        
        Sub-agents use this to understand their scope and boundaries.
        """
        return (
            "=== AGENT ROSTER ===\n"
            "NOVA (CEO): All tools. Orchestrates all agents.\n"
            "ATLAS (Lead Dev): advanced_browser, browse_agent, elite_scrape, "
            "vision_browse, bulk_scrape, stealth_extract, stealth_search\n"
            "PIXEL (Creative): create_instagram_post, create_content_calendar, "
            "generate_ai_image, optimize_post, write_content\n"
            "QUILL (Content): write_cold_email, write_ad_copy, write_content, "
            "create_drip_campaign, generate_sequence, generate_email, "
            "generate_follow_up_sequence\n"
            "HAWK (Lead Hunter): find_leads, find_leads_v2, research_lead, "
            "deep_research, run_seo_audit, sgai_search_and_extract, "
            "sgai_deep_extract, google_search\n"
            "CLOSER (Sales): send_outreach, send_email, trigger_retell_call, "
            "generate_proposal, check_replies, reply_to_email\n"
            "SENTINEL (Ops): pipeline_report, conversion_analysis, "
            "roi_calculator, track_metric, weekly_report, "
            "monitor_client_ads, pause_meta_campaign\n"
            "ECHO (Client Success): check_replies, reply_to_email, "
            "summarize_and_categorize_inbox, get_inbox\n"
            "ORACLE (Analytics): pipeline_report, conversion_analysis, "
            "roi_calculator, track_metric, weekly_report\n"
            "VIPER (Stealth): stealth_search, stealth_extract, "
            "bulk_scrape, elite_scrape, vision_browse, "
            "hunt_hiring_signals, generate_hiring_outreach\n"
            "===================="
        )
