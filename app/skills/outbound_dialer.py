# -*- coding: utf-8 -*-
import os
import httpx
from typing import Dict, Any

async def trigger_retell_call(phone: str, context: Dict[str, str]) -> Dict[str, Any]:
    url = "https://api.retellai.com/v2/create-phone-call"
    payload = {
        "from_number": os.getenv("RETELL_FROM_NUMBER"),
        "to_number": phone,
        "agent_id": os.getenv("RETELL_AGENT_ID"),
        "retell_llm_dynamic_variables": {
            "business_name": context.get("business_name"),
            "icebreaker": context.get("icebreaker"),
        },
    }
    headers = {
        "Authorization": f"Bearer {os.getenv('RETELL_API_KEY')}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        resp_json = resp.json() if resp.content else {}
        if resp.status_code == 201:
            return {"success": True, "call_id": resp_json.get("call_id"), "data": resp_json}
        return {"success": False, "error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}
