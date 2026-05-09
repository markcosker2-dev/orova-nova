"""
Nova — Core Persona Definition.
Phase 5: Hardened negative constraints. AI-isms purged.
Limp Mode inherits the same voice ceiling.
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

# ── Voice QC Validator ────────────────────────────────────────────────────────
AI_ISM_PATTERNS = [
    r"\bgreat\b", r"\babsolutely\b", r"\bcertainly\b", r"\bsure\b",
    r"\bof course\b", r"\bi apologize\b", r"\bi'm sorry\b", r"\bunfortunately\b",
    r"\bas an ai\b", r"\blanguage model\b", r"\bi think\b", r"\bi believe\b",
]

def voice_qc(text: str) -> str:
    """Scan output for prohibited patterns and log violations."""
    violations = [p for p in AI_ISM_PATTERNS if re.search(p, text, re.IGNORECASE)]
    if violations:
        logger.warning(f"[Soul.QC] Voice violations detected: {violations}")
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
