# -*- coding: utf-8 -*-
"""
Proposal Generator Skill for OROVA (Closer Agent)
Creates Grand Slam Offer proposals from audit/research data.
"""

import logging
import os
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.units import inch

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


async def generate_proposal_pdf(
    company: str,
    contact_name: str,
    industry: str,
    tier: str = "growth",
    pain_points: list = None,
    audit_findings: str = None,
) -> str:
    """
    Generate a professional PDF proposal.
    Returns: Path to the generated PDF file.
    """
    # 1. Setup Paths
    from app.main import DATA_DIR
    proposal_dir = os.path.join(DATA_DIR, "proposals")
    os.makedirs(proposal_dir, exist_ok=True)
    
    filename = f"Proposal_{company.replace(' ', '_')}_{tier}_{datetime.now().strftime('%Y%m%d')}.pdf"
    filepath = os.path.join(proposal_dir, filename)
    
    logger.info(f"[CLOSER] Generating PDF proposal for {company} at {filepath}")

    # 2. Setup Document
    doc = SimpleDocTemplate(filepath, pagesize=LETTER, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle(
        'OrovaTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.black,
        alignment=1, # Center
        spaceAfter=30
    )
    
    header_style = ParagraphStyle(
        'OrovaHeader',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor("#B8860B"), # Dark Goldenrod
        spaceBefore=20,
        spaceAfter=10
    )
    
    sub_header_style = ParagraphStyle(
        'OrovaSubHeader',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.black,
        spaceBefore=12,
        spaceAfter=6
    )
    
    body_style = styles['Normal']
    body_style.fontSize = 11
    body_style.leading = 14
    
    # 3. Content
    story = []
    
    # Header Branding
    story.append(Paragraph("OROVA", title_style))
    story.append(Paragraph("CLIENT PROPOSAL", ParagraphStyle('Sub', parent=title_style, fontSize=14, spaceAfter=40)))
    
    # Prepared For
    story.append(Paragraph(f"<b>Prepared For:</b> {contact_name} at {company}", body_style))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}", body_style))
    story.append(Paragraph(f"<b>Package:</b> {PRICING_TIERS.get(tier, PRICING_TIERS['growth'])['name']}", body_style))
    story.append(Spacer(1, 0.5 * inch))
    
    # Problem Section
    story.append(Paragraph("THE PROBLEM", header_style))
    story.append(Paragraph(f"After analyzing {company}'s current position in the {industry} space, we've identified these critical gaps that are costing you revenue:", body_style))
    
    pain_points = pain_points or ["Low online visibility", "Inconsistent lead flow", "No structured follow-up system"]
    for i, pain in enumerate(pain_points, 1):
        story.append(Paragraph(f"• {pain}", body_style))
    
    if audit_findings:
        story.append(Paragraph("Audit Findings", sub_header_style))
        story.append(Paragraph(audit_findings, body_style))
        
    story.append(Spacer(1, 0.3 * inch))
    
    # Solution Section
    package = PRICING_TIERS.get(tier, PRICING_TIERS["growth"])
    story.append(Paragraph(f"THE SOLUTION: {package['name'].upper()}", header_style))
    story.append(Paragraph(f"<b>Investment:</b> {package['price']} | <b>Duration:</b> {package['duration']}", body_style))
    story.append(Spacer(1, 0.1 * inch))
    
    story.append(Paragraph("What's Included:", sub_header_style))
    for item in package["includes"]:
        story.append(Paragraph(f"✓ {item}", body_style))
        
    story.append(Spacer(1, 0.3 * inch))
    
    # Guarantee Section
    story.append(Paragraph("THE GUARANTEE", header_style))
    story.append(Paragraph(f"<i>{package['guarantee']}</i>", ParagraphStyle('G', parent=body_style, leftIndent=20, rightIndent=20)))
    story.append(Spacer(1, 0.3 * inch))
    
    # Why OROVA
    story.append(Paragraph("WHY OROVA?", header_style))
    whys = [
        "<b>AI-Powered Agency</b>: 8 specialized AI agents working 24/7 for your business.",
        "<b>Hormozi-Grade Strategy</b>: Grand Slam Offers that make saying 'no' harder than saying 'yes'.",
        "<b>Proven System</b>: Our outreach-to-appointment pipeline delivers results, not promises.",
        "<b>Zero Risk</b>: Every package comes with a performance guarantee."
    ]
    for why in whys:
        story.append(Paragraph(f"• {why}", body_style))
        
    story.append(Spacer(1, 0.5 * inch))
    
    # Signature
    story.append(Paragraph("Mark Cosker", ParagraphStyle('Sig', parent=body_style, fontSize=12, alignment=2)))
    story.append(Paragraph("Founder, OROVA", ParagraphStyle('SigSub', parent=body_style, fontSize=10, alignment=2)))
    
    # 4. Build
    doc.build(story)
    
    return filepath
