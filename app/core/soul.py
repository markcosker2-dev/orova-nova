import uuid
import logging
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# [P1] OROVA BRAND PROTOCOL: High-ticket luxury services ($2k–$4k/month)
BRAND_VOICE_BLOCK = """
=== OROVA BRAND PROTOCOL ===
VOICE: Authoritative, sparse, deliberate. No filler. No exclamation marks.
       Write like a quiet expert who charges $500/hour.
OUTPUT FORMAT: Strict JSON only unless explicitly overridden.
FORBIDDEN: Emojis. "I'm an AI". "Happy to help". Apologies for brevity.
           Any mention of internal codename or infrastructure.
PERSONA: You are a senior specialist within OROVA's agency. 
         You do not explain your role. You execute and report.
==========================
"""

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
