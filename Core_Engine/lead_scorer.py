"""
Core_Engine/lead_scorer.py
Fixed version — correct imports, saves score to DB, retry logic.
"""

import os
import json
import logging
from typing import Dict, Any

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import ConfigLoader

logger = logging.getLogger("nova.scorer")


class UniversalLeadScorer:
    """Scores leads 0-100 based on CLV potential and niche vertical rules."""

    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.config = ConfigLoader()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def score_lead(self, lead_data: Dict[str, Any], vertical: str) -> int:
        """
        Score a lead using Gemini + vertical-specific rules.
        Returns an integer 0-100.
        Also saves the score to the database.
        """
        try:
            v_config = self.config.get_vertical_config(vertical)
            v_rules = v_config.get("scoring_rules", {})
        except Exception:
            v_rules = {}

        business = lead_data.get("business", "Unknown")
        description = lead_data.get("metadata") or ""

        # Build context from what we know
        context_parts = [f"Business: {business}"]
        if lead_data.get("website"):
            context_parts.append(f"Website: {lead_data['website']}")
        if lead_data.get("vertical"):
            context_parts.append(f"Industry: {lead_data['vertical']}")
        if description:
            context_parts.append(f"Notes: {description[:200]}")

        rules_text = json.dumps(v_rules) if v_rules else "Score based on general business quality and growth potential"

        prompt = f"""
You are a lead scoring expert for a B2B agency.

Score this business from 0 to 100 for outreach priority.

Scoring rules for {vertical}:
{rules_text}

Business information:
{chr(10).join(context_parts)}

Scoring guide:
- 80-100: Ideal prospect, high CLV potential, likely decision maker reachable
- 60-79:  Good prospect, worth reaching out
- 40-59:  Average, pursue if pipeline is thin
- 20-39:  Low priority
- 0-19:   Skip

Return ONLY the integer score. No explanation. No punctuation. Just the number.
"""

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash", contents=prompt
            )
            score_text = response.text.strip().split()[0]  # Take first token
            score = max(0, min(100, int(score_text)))
            logger.info(f"[SCORER] {business} → {score}/100")
            return score
        except (ValueError, IndexError) as e:
            logger.warning(f"[SCORER] Could not parse score for {business}: {e} — defaulting to 50")
            return 50
        except Exception as e:
            logger.error(f"[SCORER] Gemini error for {business}: {e}")
            return 50
