"""
HAWK Persona - OROVA's Lead Qualification & Outreach Engine
High-status, concise, results-oriented lead handling.
"""

import logging
from typing import Dict, Any, Optional
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

class HAWK:
    """
    HAWK: High-status, results-oriented lead qualification and outreach.
    Only engages with luxury-aligned leads scoring >85.
    """

    def __init__(self):
        self.ai_client = UnifiedAIClient()

    async def evaluate_lead_quality(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate lead luxury alignment using HAWK scoring system.
        Returns score 0-100 based on luxury niche fit.
        """
        prompt = f"""
        Evaluate this lead for luxury {lead_data.get('niche', 'automotive')} business fit.
        Score 0-100 based on luxury alignment, budget capacity, and decision-making authority.

        Lead Data:
        - Name: {lead_data.get('name', '')}
        - Business: {lead_data.get('business', '')}
        - Website: {lead_data.get('website', '')}
        - Description: {lead_data.get('description', '')}
        - Location: {lead_data.get('location', '')}

        Return JSON: {{"score": int, "justification": "brief reason", "luxury_indicators": ["list", "of", "signals"]}}
        """

        try:
            response = await self.ai_client.reason(prompt)
            # Parse JSON response
            import json
            evaluation = json.loads(response)
            return evaluation
        except Exception as e:
            logger.error(f"HAWK evaluation failed: {e}")
            return {"score": 0, "justification": "Evaluation failed", "luxury_indicators": []}

    async def craft_hawk_outreach(self, lead_data: Dict[str, Any]) -> str:
        """
        Craft high-status, concise outreach email in HAWK style.
        No fluff, results-oriented, positions OROVA as strategic partner.
        """
        hawk_score = lead_data.get('hawk_score', 0)

        prompt = f"""
        Craft a high-status, concise outreach email for this luxury lead.
        Style: Results-oriented, no fluff, position as strategic partner.

        Lead: {lead_data.get('name', '')} at {lead_data.get('business', '')}
        HAWK Score: {hawk_score}/100
        Niche: {lead_data.get('niche', 'luxury automotive')}

        Email must:
        - Be under 100 words
        - Reference specific luxury signals
        - Propose strategic partnership
        - Include clear next step
        - End with authority signature

        Write the complete email:
        """

        try:
            email_content = await self.ai_client.write(prompt)
            return email_content.strip()
        except Exception as e:
            logger.error(f"HAWK outreach crafting failed: {e}")
            return "Strategic partnership opportunity identified. Let's discuss alignment."

    async def monitor_roas_safety(self, performance_data: Dict[str, Any]) -> Optional[str]:
        """
        Monitor Meta Ads ROAS and trigger safety measures if below 2.0.
        Returns emergency alert message if triggered.
        """
        roas = performance_data.get('roas', 0)

        if roas < 2.0:
            alert_message = f"""
            🚨 ROAS EMERGENCY ALERT 🚨

            Campaign: {performance_data.get('campaign', 'Unknown')}
            Current ROAS: {roas} (Threshold: 2.0)
            Spend: ${performance_data.get('spend', 0)}
            Leads: {performance_data.get('leads', 0)}

            ACTION REQUIRED: Campaign paused. Review targeting and creative immediately.
            """

            logger.critical(f"ROAS safety triggered: {roas}")
            # TODO: Integrate with webhook for phone alert
            return alert_message

        return None

    async def generate_lead_insights(self, lead_data: Dict[str, Any]) -> str:
        """
        Generate strategic insights about a qualified lead.
        Focus on competitive advantages and partnership opportunities.
        """
        prompt = f"""
        Analyze this luxury lead for strategic partnership opportunities:

        Lead: {lead_data.get('name', '')}
        Business: {lead_data.get('business', '')}
        HAWK Score: {lead_data.get('hawk_score', 0)}/100
        Luxury Signals: {', '.join(lead_data.get('luxury_indicators', []))}

        Provide 3 strategic insights for OROVA partnership:
        1. Competitive advantage we offer
        2. Pain points we can solve
        3. Partnership value proposition

        Keep under 200 words.
        """

        try:
            insights = await self.ai_client.write(prompt)
            return insights.strip()
        except Exception as e:
            logger.error(f"HAWK insights generation failed: {e}")
            return "Strategic partnership opportunity with proven ROI track record."