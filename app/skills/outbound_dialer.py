# -*- coding: utf-8 -*-
import os
import logging
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

async def trigger_retell_call(phone: str, context: Dict[str, str]) -> Dict[str, Any]:
    """
    Trigger a Retell AI cold call. Gracefully skips if no API key is configured.
    Returns {"success": True/False, "call_id"/"error", "skipped": bool}
    """
    # ── Graceful degradation: skip if no API key ──
    api_key = os.getenv("RETELL_API_KEY")
    from_number = os.getenv("RETELL_FROM_NUMBER")
    agent_id = os.getenv("RETELL_AGENT_ID")

    if not api_key or not from_number or not agent_id:
        missing = []
        if not api_key: missing.append("RETELL_API_KEY")
        if not from_number: missing.append("RETELL_FROM_NUMBER")
        if not agent_id: missing.append("RETELL_AGENT_ID")
        logger.warning(f"[Retell] Skipping call — missing env vars: {', '.join(missing)}")
        return {"success": False, "skipped": True, "error": f"Missing env vars: {', '.join(missing)}. Cold calling is disabled — set these to enable."}

    url = "https://api.retellai.com/v2/create-phone-call"
    payload = {
        "from_number": from_number,
        "to_number": phone,
        "agent_id": agent_id,
        "retell_llm_dynamic_variables": {
            "business_name": context.get("business_name"),
            "icebreaker": context.get("icebreaker"),
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        resp_json = resp.json() if resp.content else {}
        if resp.status_code == 201:
            return {"success": True, "call_id": resp_json.get("call_id"), "data": resp_json, "skipped": False}
        return {"success": False, "error": resp.text, "status_code": resp.status_code, "skipped": False}
    except Exception as e:
        return {"success": False, "error": str(e), "skipped": False}
