import uuid
import logging
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

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
        uuid_str = await DatabaseManager.get_state("OROVA_CORE_UUID", "UNKNOWN")
        mission = await DatabaseManager.get_state("ACTIVE_MISSION_TOKEN", "Awaiting directives.")
        return f"=== OROVA CORE ===\nUUID: {uuid_str}\nMISSION: {mission}\nCONSTRAINTS: $0 cost, strict JSON, 512MB RAM limit.\n=================="
