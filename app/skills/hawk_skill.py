"""
HAWK Skill - Lead Qualification & Outreach Operations
Integrates HAWK persona into the OpenClaw agent system.
"""

import logging
from typing import Dict, Any, Optional
from app.core.hawk import HAWK

logger = logging.getLogger(__name__)

hawk_instance = HAWK()

async def hawk_lead_scoring(lead_data: Dict[str, Any]) -> str:
    """
    HAWK skill: Evaluate lead luxury alignment and scoring.
    Only processes leads with >85 luxury alignment score.
    """
    try:
        evaluation = await hawk_instance.evaluate_lead_quality(lead_data)

        score = evaluation.get("score", 0)
        justification = evaluation.get("justification", "")
        indicators = evaluation.get("luxury_indicators", [])

        if score >= 85:
            result = f"✅ HAWK APPROVED: Lead score {score}/100\n"
            result += f"Justification: {justification}\n"
            result += f"Luxury Indicators: {', '.join(indicators)}\n"
            result += "🚀 Moving to Google Sheets HUNT tab and preparing outreach."
        else:
            result = f"❌ HAWK REJECTED: Lead score {score}/100 (below 85 threshold)\n"
            result += f"Justification: {justification}"

        return result

    except Exception as e:
        logger.error(f"HAWK lead scoring failed: {e}")
        return f"❌ HAWK evaluation error: {str(e)}"

async def hawk_outreach(lead_data: Dict[str, Any]) -> str:
    """
    HAWK skill: Craft and execute high-status outreach email.
    """
    try:
        email_content = await hawk_instance.craft_hawk_outreach(lead_data)

        # TODO: Integrate with AgentMail for actual sending
        result = "📧 HAWK OUTREACH CRAFTED:\n\n"
        result += email_content
        result += "\n\n✅ Ready for AgentMail delivery"

        return result

    except Exception as e:
        logger.error(f"HAWK outreach crafting failed: {e}")
        return f"❌ HAWK outreach error: {str(e)}"

async def hawk_insights(lead_data: Dict[str, Any]) -> str:
    """
    HAWK skill: Generate strategic insights about qualified leads.
    """
    try:
        insights = await hawk_instance.generate_lead_insights(lead_data)

        result = "🎯 HAWK STRATEGIC INSIGHTS:\n\n"
        result += insights

        return result

    except Exception as e:
        logger.error(f"HAWK insights generation failed: {e}")
        return f"❌ HAWK insights error: {str(e)}"