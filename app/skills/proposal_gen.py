# -*- coding: utf-8 -*-
"""
Proposal Generator Skill for OROVA (Closer Agent)
Creates Grand Slam Offer proposals from audit/research data.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Pricing Tiers ────────────────────────────────────────────────
PRICING_TIERS = {
    "starter": {
        "name": "Starter Sprint",
        "price": "$1,500/mo",
        "duration": "30-Day Sprint",
        "includes": [
            "Full SEO & Competitor Audit",
            "5 Targeted Outreach Emails Per Week",
            "1 AI-Generated Social Post Per Day",
            "Weekly Performance Report",
        ],
        "guarantee": "If we don't deliver 5 qualified leads in 30 days, we work free until we do.",
    },
    "growth": {
        "name": "Growth Accelerator",
        "price": "$3,500/mo",
        "duration": "90-Day Program",
        "includes": [
            "Everything in Starter Sprint",
            "AI Voice Outreach (50 calls/week)",
            "Custom Landing Page Build",
            "Multi-Channel Sequences (Email + Voice + Social)",
            "Bi-Weekly Strategy Calls with Mark",
            "CRM Setup & Management",
        ],
        "guarantee": "15 qualified appointments in 90 days or your money back.",
    },
    "empire": {
        "name": "Empire Builder",
        "price": "$7,500/mo",
        "duration": "6-Month Partnership",
        "includes": [
            "Everything in Growth Accelerator",
            "Dedicated AI Agent Team (8 Agents)",
            "Full Content Pipeline Management",
            "Instagram Brand Build (B&W Luxury)",
            "Competitive Intelligence Reports",
            "Priority Response (< 2 hours)",
            "Monthly In-Person Strategy Session",
        ],
        "guarantee": "50 qualified appointments in 6 months. If not, 7th month is free.",
    },
}


async def generate_proposal(
    company: str,
    contact_name: str,
    industry: str,
    tier: str = "growth",
    pain_points: list = None,
    audit_findings: str = None,
) -> str:
    """
    Generate a professional Grand Slam Offer proposal.

    Args:
        company: Target company name
        contact_name: Contact person
        industry: Business vertical
        tier: 'starter', 'growth', or 'empire'
        pain_points: List of identified pain points
        audit_findings: SEO/competitor audit results to include
    """
    logger.info(f"[CLOSER] Generating {tier} proposal for {company}")

    package = PRICING_TIERS.get(tier, PRICING_TIERS["growth"])
    today = datetime.now().strftime("%B %d, %Y")
    pain_points = pain_points or ["Low online visibility", "Inconsistent lead flow", "No structured follow-up system"]

    proposal = f"""
{'═' * 60}
            OROVA — CLIENT PROPOSAL
{'═' * 60}

📋 **Prepared For:** {contact_name} at {company}
📅 **Date:** {today}
🏷️ **Package:** {package['name']}

{'─' * 60}

## THE PROBLEM

After analyzing {company}'s current position in the {industry} space, we've identified these critical gaps:

"""
    for i, pain in enumerate(pain_points, 1):
        proposal += f"  {i}. ❌ {pain}\n"

    if audit_findings:
        proposal += f"\n### Audit Findings\n{audit_findings}\n"

    proposal += f"""
{'─' * 60}

## THE SOLUTION: {package['name'].upper()}

**Investment:** {package['price']} | **Duration:** {package['duration']}

### What's Included:
"""
    for item in package["includes"]:
        proposal += f"  ✅ {item}\n"

    proposal += f"""
{'─' * 60}

## THE GUARANTEE (Our Skin in the Game)

🛡️ **{package['guarantee']}**

This isn't a retainer with vague promises. We put our money where our mouth is.

{'─' * 60}

## WHY OROVA?

• **AI-Powered Agency**: 8 specialized AI agents working 24/7 for your business
• **Hormozi-Grade Strategy**: Grand Slam Offers that make saying "no" harder than saying "yes"
• **Proven System**: Our outreach-to-appointment pipeline has a 12% reply rate (industry avg: 2%)
• **Zero Risk**: Every package comes with a performance guarantee

{'─' * 60}

## NEXT STEPS

1. 📞 **Quick Call**: 15-min strategy call with Mark Cosker
2. 📝 **Custom Plan**: We build your personalized growth roadmap
3. 🚀 **Launch**: Your AI team starts working Day 1

**Ready to start?** Reply to this email or book a call at your convenience.

{'═' * 60}
             Mark Cosker | Founder, OROVA
             Building Empires with AI
{'═' * 60}
"""

    logger.info(f"[CLOSER] Proposal generated for {company} ({tier} tier)")
    return proposal.strip()


async def list_pricing_tiers() -> dict:
    """List available pricing tiers and their details."""
    return {
        "success": True,
        "tiers": {k: {"name": v["name"], "price": v["price"], "duration": v["duration"], "items": len(v["includes"])} for k, v in PRICING_TIERS.items()}
    }
