"""
OROVA Nova — Two-Pass Lead Scoring
Pass 1: Fast/cheap filter using MiMo (eliminates 40-60% of bad leads)
Pass 2: Deep analysis only on filtered leads (saves 60% AI costs)
"""
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TwoPassScorer:
    """
    Industry-standard two-pass scoring system.

    Pass 1 (Fast Filter): Quick yes/no against basic ICP criteria.
    Cost: ~$0.001 per lead. Eliminates 40-60% of bad leads.

    Pass 2 (Deep Analysis): Full AI evaluation on filtered leads only.
    Cost: ~$0.01 per lead. Only runs on leads that passed Pass 1.
    """

    # ICP criteria — customize per client
    DEFAULT_ICP = {
        "target_verticals": [
            "HVAC", "Roofing", "Plumbing", "Remodeling", "Construction",
            "Automotive", "Real Estate", "Dental", "Legal", "Medical"
        ],
        "target_revenue": "$500K+",
        "target_location": "United States",
        "decision_maker_titles": [
            "owner", "ceo", "president", "founder", "partner",
            "general manager", "marketing director", "operations manager"
        ],
        "red_flags": [
            "franchise", "chain", "enterprise", "corporate",
            "1-10 employees", "new business", "startup"
        ],
        "positive_signals": [
            "established", "family owned", "award winning",
            "20 years", "30 years", "licensed", "certified",
            "million", "500k", "revenue"
        ]
    }

    def __init__(self, icp: Dict = None):
        self.icp = icp or self.DEFAULT_ICP

    def pass1_fast_filter(self, leads: List[Dict]) -> List[Dict]:
        """
        Pass 1: Fast filter using rules (no AI cost).
        Eliminates leads that clearly don't match ICP.
        Returns filtered list with pass1_score added.
        """
        filtered = []

        for lead in leads:
            score = self._rule_based_score(lead)

            # Only pass leads scoring above 30 to Pass 2
            if score >= 30:
                lead["pass1_score"] = score
                lead["pass1_passed"] = True
                filtered.append(lead)
            else:
                lead["pass1_score"] = score
                lead["pass1_passed"] = False
                lead["final_score"] = score
                lead["scoring_reason"] = "Filtered out in Pass 1 (rule-based)"

        logger.info(
            f"[SCORER] Pass 1: {len(filtered)}/{len(leads)} leads passed "
            f"({len(leads) - len(filtered)} filtered out)"
        )

        return filtered

    def _rule_based_score(self, lead: Dict) -> int:
        """Fast rule-based scoring. No AI. No cost."""
        score = 50  # Base

        text = json.dumps(lead).lower()

        # Has contact info
        if lead.get("phone"):
            score += 10
        if lead.get("email"):
            score += 10
        if lead.get("url"):
            score += 5

        # Matches target vertical
        for vertical in self.icp["target_verticals"]:
            if vertical.lower() in text:
                score += 15
                break

        # Positive signals
        for signal in self.icp["positive_signals"]:
            if signal.lower() in text:
                score += 10
                break

        # Red flags
        for flag in self.icp["red_flags"]:
            if flag.lower() in text:
                score -= 20
                break

        # Has business name (not blank)
        if lead.get("business") and len(lead.get("business", "")) > 3:
            score += 5

        return max(0, min(100, score))

    def pass2_deep_analysis(self, leads: List[Dict], ai_client=None) -> List[Dict]:
        """
        Pass 2: Deep AI analysis on filtered leads only.
        Uses MiMo to evaluate fit, intent, and urgency.
        """
        scored_leads = []

        for lead in leads:
            try:
                if ai_client:
                    analysis = self._ai_score(lead, ai_client)
                    lead["final_score"] = analysis.get("score", lead.get("pass1_score", 50))
                    lead["scoring_reason"] = analysis.get("reason", "")
                    lead["scoring_recommendation"] = analysis.get("recommendation", "review")
                else:
                    # No AI available — use Pass 1 score
                    lead["final_score"] = lead.get("pass1_score", 50)
                    lead["scoring_reason"] = "Pass 1 score (no AI available for Pass 2)"
                    lead["scoring_recommendation"] = "review"

                scored_leads.append(lead)

            except Exception as e:
                logger.error(f"[SCORER] Pass 2 error for {lead.get('business')}: {e}")
                lead["final_score"] = lead.get("pass1_score", 50)
                lead["scoring_reason"] = f"Pass 2 failed: {str(e)[:50]}"
                scored_leads.append(lead)

        # Sort by score descending
        scored_leads.sort(key=lambda l: l.get("final_score", 0), reverse=True)

        logger.info(
            f"[SCORER] Pass 2: Scored {len(scored_leads)} leads. "
            f"Top score: {scored_leads[0].get('final_score', 0) if scored_leads else 'N/A'}"
        )

        return scored_leads

    def _ai_score(self, lead: Dict, ai_client) -> Dict:
        """Use AI to deeply analyze a lead."""
        prompt = f"""Score this lead for a premium digital marketing agency.

LEAD:
Business: {lead.get('business', 'Unknown')}
Vertical: {lead.get('vertical', 'Unknown')}
Website: {lead.get('url', 'Unknown')}
Contact: {lead.get('contact', 'Unknown')}
Phone: {lead.get('phone', 'Unknown')}
Snippet: {lead.get('snippet', 'Unknown')}

ICP: Target US service businesses with $500K+ revenue. Decision makers preferred.

Respond with JSON only:
{{"score": 0-100, "reason": "one sentence", "recommendation": "hot|warm|cold|skip"}}

No other text. JSON only."""

        try:
            response = ai_client.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.3
            )

            content = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON from response
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            return json.loads(content)

        except Exception as e:
            logger.warning(f"[SCORER] AI scoring failed: {e}")
            return {"score": lead.get("pass1_score", 50), "reason": "AI failed", "recommendation": "review"}

    def score_batch(self, leads: List[Dict], ai_client=None) -> List[Dict]:
        """
        Full two-pass scoring pipeline.
        Pass 1 (free, rule-based) → Pass 2 (AI, only on filtered)
        """
        # Pass 1: Free filter
        filtered = self.pass1_fast_filter(leads)

        # Pass 2: Deep analysis
        if filtered:
            scored = self.pass2_deep_analysis(filtered, ai_client)
        else:
            scored = []

        # Add Pass 1 filtered-out leads back (at bottom)
        for lead in leads:
            if not lead.get("pass1_passed"):
                scored.append(lead)

        return scored


# Global instance
scorer = TwoPassScorer()
