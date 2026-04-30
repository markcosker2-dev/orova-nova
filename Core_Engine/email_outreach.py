"""
Core_Engine/email_outreach.py
Fixed version — generates subject + body as JSON, proper imports, retry logic.
"""

import os
import json
import logging
from typing import Dict, Any

import yagmail
from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import ConfigLoader

logger = logging.getLogger("nova.email")


class UniversalEmailAgent:
    """Generates and sends personalised cold emails using Gemini."""

    def __init__(self):
        self.user = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASS")
        if not self.user or not self.password:
            logger.warning("[EMAIL] EMAIL_USER or EMAIL_PASS not set — sending disabled")
        self.config = ConfigLoader()

    def _get_yag(self):
        """Lazy-init yagmail so class can be instantiated without credentials."""
        if not self.user or not self.password:
            raise RuntimeError("EMAIL_USER and EMAIL_PASS must be set in .env")
        return yagmail.SMTP(self.user, self.password)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def draft_email(self, lead_data: Dict[str, Any], vertical: str) -> Dict[str, str]:
        """
        Use Gemini to generate a subject line AND body for a cold email.
        Returns: { "subject": "...", "body": "..." }
        """
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        try:
            v_config = self.config.get_vertical_config(vertical)
            value_prop = v_config.get("email_templates", {}).get(
                "value_proposition", "grow your business with AI-powered marketing"
            )
        except Exception:
            value_prop = "grow your business with AI-powered marketing"

        business = lead_data.get("business", "your business")
        contact = lead_data.get("contact") or "there"

        prompt = f"""
Write a short cold email to {contact} at {business} in the {vertical} space.

Value proposition: {value_prop}

Rules:
- Subject line: punchy, personalised, under 8 words, no spam triggers
- Body: max 3 sentences, casual and direct, no corporate jargon, no "I hope this email finds you well"
- Sound like a successful peer reaching out, not a sales robot
- End with one simple call-to-action (a question works best)

Return ONLY valid JSON in this exact format, no markdown, no preamble:
{{"subject": "...", "body": "..."}}
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        raw = response.text.strip()

        # Strip markdown code fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(raw)
            if "subject" not in parsed or "body" not in parsed:
                raise ValueError("Missing keys")
            logger.info(f"[EMAIL] Drafted for {business}: subject='{parsed['subject']}'")
            return parsed
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[EMAIL] JSON parse failed ({e}), extracting from raw text")
            # Fallback: use the whole response as the body
            return {
                "subject": f"Quick question about {business}",
                "body": raw[:500],
            }

    async def send_to_lead(self, lead_data: Dict[str, Any]) -> Dict[str, str]:
        """
        High-level method: draft + send in one call.
        Returns the drafted email dict { subject, body }.
        """
        recipient = lead_data.get("email")
        if not recipient:
            raise ValueError(f"No email address for lead: {lead_data.get('business')}")

        vertical = lead_data.get("vertical", "General")
        email_content = await self.draft_email(lead_data, vertical)

        await self.send_email(
            recipient=recipient,
            subject=email_content["subject"],
            body=email_content["body"],
        )
        return email_content

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=5, max=30))
    async def send_email(self, recipient: str, subject: str, body: str):
        """Send the actual email via yagmail / Gmail SMTP."""
        yag = self._get_yag()
        yag.send(to=recipient, subject=subject, contents=body)
        logger.info(f"[EMAIL] Sent → {recipient} | '{subject}'")
