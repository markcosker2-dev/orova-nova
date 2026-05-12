"""
OROVA Nova — Retell AI Dynamic Script Generator
Generates personalized cold call scripts per prospect using AI.
Each call gets a unique script based on the lead's business, pain points, and vertical.
"""
import os
import json
import logging
import httpx
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

RETELL_API_KEY = os.getenv("RETELL_API_KEY", "")
RETELL_BASE_URL = "https://api.retellai.com"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")


class RetellScriptGenerator:
    """
    Generates dynamic cold call scripts per prospect.
    Uses AI to personalize the script based on lead data.
    """

    SYSTEM_PROMPT = """You are a world-class cold call script writer for high-ticket service businesses.
Your scripts are concise, natural, and conversational — never robotic or salesy.

Write scripts that:
1. Open with a pattern interrupt (reference something specific about their business)
2. Identify a pain point within 15 seconds
3. Offer a specific, tangible value proposition
4. Use a soft close — suggest a meeting, don't push for the sale
5. Handle the 3 most common objections naturally

Keep the script under 200 words. Write it as if a confident, friendly expert is speaking — not a telemarketer.
The caller represents a premium digital marketing agency (OROVA) that helps service businesses get more high-value clients."""

    def generate_script(self, lead_data: Dict) -> str:
        """
        Generate a personalized cold call script for a specific lead.

        Args:
            lead_data: Dict with business, vertical, url, phone, contact, snippet, notes

        Returns:
            Personalized script text
        """
        business = lead_data.get("business", "your business")
        vertical = lead_data.get("vertical", "service business")
        url = lead_data.get("url", "")
        contact = lead_data.get("contact", "")
        snippet = lead_data.get("snippet", "")
        notes = lead_data.get("notes", "")

        user_prompt = f"""Write a cold call script for calling this prospect:

BUSINESS: {business}
VERTICAL: {vertical}
WEBSITE: {url}
CONTACT: {contact}
ABOUT: {snippet}
NOTES: {notes}

Create a script that feels like a real conversation, not a pitch. The caller is from OROVA, a premium agency that helps {vertical} businesses get more high-ticket clients through digital marketing and lead generation."""

        try:
            if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == "demo-key":
                return self._fallback_script(lead_data)

            from openai import OpenAI
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=OPENROUTER_API_KEY
            )

            response = client.chat.completions.create(
                model="google/gemini-2.0-flash-lite:free",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )

            script = response.choices[0].message.content
            logger.info(f"[RETELL SCRIPT] Generated script for {business}")
            return script

        except Exception as e:
            logger.error(f"[RETELL SCRIPT] AI generation failed: {e}")
            return self._fallback_script(lead_data)

    def _fallback_script(self, lead_data: Dict) -> str:
        """Fallback script when AI is unavailable."""
        business = lead_data.get("business", "your business")
        vertical = lead_data.get("vertical", "service business")

        return f"""Hi, this is [Name] from OROVA. I'm reaching out because I was looking at {business} and noticed you're in the {vertical} space.

Quick question — are you currently getting enough high-quality leads through your online presence, or is most of your business coming from referrals and word of mouth?

[LISTEN]

Got it. The reason I'm calling is we specialize in helping {vertical} businesses like yours fill their pipeline with pre-qualified prospects — without the guesswork of traditional marketing.

Would it make sense to hop on a quick 15-minute call this week to see if we can help?

[IF OBJECTION: "Not interested"]
Totally understand. A lot of our best clients said the same thing initially. Can I send you a quick case study of a similar {vertical} business we helped? No pressure at all.

[IF OBJECTION: "Too expensive"]
Fair enough. We actually work on a performance basis for most of our clients — meaning we only win when you win. Would that change things?

[IF OBJECTION: "Send me an email"]
Absolutely. What's the best email? I'll send over a case study and some info. If it looks interesting, we can chat. If not, no hard feelings."""

    def create_retell_agent(self, lead_data: Dict, script: str) -> Optional[Dict]:
        """
        Create a Retell AI agent with the personalized script.
        Returns the agent_id if successful.
        """
        if not RETELL_API_KEY:
            logger.warning("[RETELL] No API key configured")
            return None

        business = lead_data.get("business", "Prospect")
        vertical = lead_data.get("vertical", "business")

        agent_config = {
            "agent_name": f"OROVA Caller - {business[:30]}",
            "voice_id": "11labs-Adrian",  # Natural male voice
            "language": "en-US",
            "response_engine": "retell-llm",
            "general_prompt": f"""You are a friendly, professional sales representative from OROVA, a premium digital marketing agency.

You are calling {business}, a {vertical} company. Your goal is to book a 15-minute discovery call.

SCRIPT:
{script}

RULES:
- Be natural and conversational, never pushy
- Listen more than you talk
- If they're interested, offer to book a meeting
- If they say no, respect it and offer to send info
- Keep calls under 3 minutes
- Use their business name naturally in conversation""",
            "begin_message": f"Hi, this is calling from OROVA. Is this the right person to speak with about marketing at {business}?",
            "general_tools": [
                {
                    "type": "end_call",
                    "name": "end_call",
                    "description": "End the call when the conversation is complete"
                }
            ],
            "max_duration_seconds": 180,
            "backchanneling_enabled": True,
            "interruption_sensitivity": 0.7,
            "ambient_sound": "office",
            "responsiveness": 0.8
        }

        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{RETELL_BASE_URL}/create-agent",
                    headers={
                        "Authorization": f"Bearer {RETELL_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=agent_config,
                    timeout=30
                )

                if resp.status_code == 201:
                    agent = resp.json()
                    logger.info(f"[RETELL] Created agent: {agent.get('agent_id')}")
                    return agent
                else:
                    logger.error(f"[RETELL] Agent creation failed: {resp.status_code} {resp.text}")
                    return None

        except Exception as e:
            logger.error(f"[RETELL] Agent creation error: {e}")
            return None

    def make_call(self, phone: str, lead_data: Dict) -> Dict:
        """
        Full pipeline: generate script -> create agent -> make call.
        """
        from app.core.kill_switch import kill_switch
        from app.core.audit_trail import audit
        from app.core.phone_utils import to_e164

        # Kill switch check
        if not kill_switch.check_before_action("RetellScriptGenerator", "make_call"):
            return {"status": "blocked", "reason": "kill switch active"}

        # Normalize phone
        e164 = to_e164(phone)
        if not e164:
            return {"status": "error", "reason": f"invalid phone: {phone}"}

        # Generate personalized script
        script = self.generate_script(lead_data)

        # Create Retell agent with script
        agent = self.create_retell_agent(lead_data, script)
        if not agent:
            # Fallback: use existing agent
            agent_id = os.getenv("RETELL_AGENT_ID", "")
            if not agent_id:
                return {"status": "error", "reason": "no Retell agent available"}
        else:
            agent_id = agent.get("agent_id")

        # Make the call
        if not RETELL_API_KEY:
            logger.info(f"[RETELL] Demo mode: would call {e164} with personalized script")
            audit.log("RetellScriptGenerator", "make_call_demo",
                      input_data={"phone": e164, "business": lead_data.get("business")},
                      output_data={"status": "demo", "script_preview": script[:200]})
            return {
                "status": "demo",
                "phone": e164,
                "agent_id": agent_id,
                "script": script,
                "message": "Retell not configured — demo mode"
            }

        from_number = os.getenv("RETELL_FROM_NUMBER", "")

        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{RETELL_BASE_URL}/v2/create-phone-call",
                    headers={
                        "Authorization": f"Bearer {RETELL_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from_number": from_number,
                        "to_number": e164,
                        "agent_id": agent_id,
                        "metadata": {
                            "lead_id": lead_data.get("id"),
                            "business": lead_data.get("business"),
                            "script_generated": True
                        }
                    },
                    timeout=30
                )

                if resp.status_code in [200, 201]:
                    result = resp.json()
                    call_id = result.get("call_id")
                    logger.info(f"[RETELL] Call initiated: {call_id} -> {e164}")

                    audit.log("RetellScriptGenerator", "make_call",
                              input_data={"phone": e164, "business": lead_data.get("business")},
                              output_data={"call_id": call_id, "status": "initiated"})

                    return {
                        "status": "success",
                        "call_id": call_id,
                        "phone": e164,
                        "agent_id": agent_id,
                        "script": script
                    }
                else:
                    logger.error(f"[RETELL] Call failed: {resp.status_code} {resp.text}")
                    return {"status": "error", "reason": resp.text}

        except Exception as e:
            logger.error(f"[RETELL] Call error: {e}")
            return {"status": "error", "reason": str(e)}


# Global instance
retell = RetellScriptGenerator()
