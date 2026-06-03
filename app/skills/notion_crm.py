import os
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

MAKE_WEBHOOK_URL = os.getenv("MAKE_NOTION_WEBHOOK_URL", "")

async def sync_to_notion_via_make(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends lead information to a Make.com webhook to synchronize with a Notion CRM database.
    
    :param lead_data: Dict representing the lead. Expected keys: business, owner, email, phone, website, url, status, score, notes.
    """
    if not MAKE_WEBHOOK_URL:
        logger.warning("[NotionCRM] MAKE_NOTION_WEBHOOK_URL env var is not set. Sync skipped.")
        return {"status": "skipped", "message": "Make.com webhook URL not configured"}

    payload = {
        "id": lead_data.get("id"),
        "business": lead_data.get("business") or lead_data.get("company") or "Unknown",
        "owner": lead_data.get("owner") or lead_data.get("owner_name") or "",
        "email": lead_data.get("email") or "",
        "phone": lead_data.get("phone") or "",
        "website": lead_data.get("website") or lead_data.get("url") or "",
        "url": lead_data.get("url") or "",
        "status": lead_data.get("status") or "New",
        "score": lead_data.get("score") or 0,
        "notes": lead_data.get("notes") or lead_data.get("snippet") or "",
        "source": lead_data.get("source") or "Nova Engine",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(MAKE_WEBHOOK_URL, json=payload)
            if resp.status_code in (200, 201, 202):
                logger.info(f"[NotionCRM] Successfully synced lead '{payload['business']}' to Make.com")
                return {"status": "success", "message": "Synced successfully"}
            else:
                logger.error(f"[NotionCRM] Make.com returned HTTP {resp.status_code}: {resp.text}")
                return {"status": "error", "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        logger.error(f"[NotionCRM] Failed to sync to Make.com: {e}")
        return {"status": "error", "message": str(e)}
