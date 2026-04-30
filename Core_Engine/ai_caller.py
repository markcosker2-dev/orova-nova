"""
Core_Engine/ai_caller.py
Fixed version — correct Retell API params (from_number/to_number),
stores call_id on the lead record so webhook can match it.
"""

import os
import json
import logging
from typing import Dict, Any

from retell import Retell
from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .db_manager import DatabaseManager
from .config import ConfigLoader

logger = logging.getLogger("nova.caller")


class UniversalAICaller:
    """Handles voice calling via Retell AI with Gemini-driven call scripts."""

    def __init__(self):
        self.api_key = os.getenv("RETELL_API_KEY")
        if not self.api_key:
            logger.warning("[CALLER] RETELL_API_KEY not set — calling disabled")
        self.retell = Retell(api_key=self.api_key) if self.api_key else None
        self.db = DatabaseManager()
        self.config = ConfigLoader()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def generate_script(self, lead_data: Dict[str, Any], vertical: str) -> str:
        """Generate a personalised, punchy call script using Gemini."""
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        try:
            v_config = self.config.get_vertical_config(vertical)
            value_prop = v_config.get("email_templates", {}).get(
                "value_proposition", "help you get more clients using AI"
            )
        except Exception:
            value_prop = "help you get more clients using AI"

        business = lead_data.get("business", "your business")

        prompt = f"""
Write a 30-second cold call opening script for {business} in the {vertical} industry.

Value prop: {value_prop}

Rules:
- Conversational, human, not robotic
- State who you are and why you're calling in the first 10 words
- One specific pain point they likely have
- End with a yes/no question that's easy to answer
- Max 60 words total

Script only, no stage directions, no labels.
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        script = response.text.strip()
        logger.info(f"[CALLER] Script generated for {business}")
        return script

    async def initiate_call(self, lead_id: int) -> Dict[str, Any]:
        """
        Generate a script and trigger a Retell AI call to the lead.
        Stores the call_id on the lead record for webhook matching.
        """
        if not self.retell:
            return {"status": "error", "message": "RETELL_API_KEY not configured"}

        from_number = os.getenv("RETELL_FROM_NUMBER")
        agent_id = os.getenv("RETELL_AGENT_ID")

        if not from_number:
            return {"status": "error", "message": "RETELL_FROM_NUMBER not set in .env"}
        if not agent_id:
            return {"status": "error", "message": "RETELL_AGENT_ID not set in .env"}

        lead = self.db.get_lead(lead_id)
        if not lead:
            return {"status": "error", "message": f"Lead {lead_id} not found"}
        if not lead.get("phone"):
            return {"status": "error", "message": f"Lead {lead_id} has no phone number"}

        vertical = lead.get("vertical", "General")

        try:
            script = await self.generate_script(lead, vertical)

            call = self.retell.call.create_phone_call(
                from_number=from_number,
                to_number=lead["phone"],
                agent_id=agent_id,
                retell_llm_dynamic_variables={
                    "lead_name": lead.get("contact") or lead.get("business", ""),
                    "business_name": lead.get("business", ""),
                    "script": script,
                    "vertical": vertical,
                },
            )

            call_id = call.call_id
            self.db.update_lead_status(lead_id, "Called")
            self.db.update_lead_call_id(lead_id, call_id)

            logger.info(f"[CALLER] Call initiated → {lead['phone']} ({lead['business']}) call_id={call_id}")
            return {"status": "ok", "call_id": call_id, "script": script}

        except Exception as e:
            logger.error(f"[CALLER] Call failed for lead {lead_id}: {e}")
            return {"status": "error", "message": str(e)}
