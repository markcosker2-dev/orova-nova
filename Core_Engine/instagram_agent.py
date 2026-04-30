"""
Core_Engine/instagram_agent.py
Fixed version — adds missing `import os`.
"""

import os
import json
import logging
from typing import Dict, Any

from google import genai

logger = logging.getLogger("nova.instagram")


class InstagramAgent:
    """Manages social media strategy and content generation for Nova/OROVA."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("[INSTAGRAM] GOOGLE_API_KEY not set")
        self.client = genai.Client(api_key=api_key)

    def generate_calendar(self, niche: str = "luxury lead-gen agency") -> str:
        """Generate a 30-day B&W luxury aesthetic content calendar."""
        prompt = f"""
Create a 30-day Instagram content calendar for a {niche}.

Format each day as:
Day [N]: [Content type] — [Hook/caption idea] — [Hashtag theme]

Aesthetic: B&W minimalist. High contrast. Professional authority.
Mix: 40% educational, 30% social proof/results, 20% behind-the-scenes, 10% direct offer.
Keep each entry under 20 words.
"""
        response = self.client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        logger.info("[INSTAGRAM] 30-day calendar generated")
        return response.text

    def generate_caption(self, post_type: str, context: str = "") -> Dict[str, str]:
        """Generate a single post caption with hooks and hashtags."""
        prompt = f"""
Write an Instagram caption for a luxury B2B agency.

Post type: {post_type}
Context: {context or 'General agency content'}

Return JSON only:
{{"hook": "...", "body": "...", "cta": "...", "hashtags": "..."}}

Rules:
- Hook: 1 punchy sentence (under 10 words), no emojis
- Body: 2-3 sentences max, premium tone, specific result if possible
- CTA: one direct action ("DM me CLIENTS", "Link in bio", etc.)
- Hashtags: 5-8 relevant tags as a single string
"""
        response = self.client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"hook": "", "body": raw, "cta": "", "hashtags": ""}
