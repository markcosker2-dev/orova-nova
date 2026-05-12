# -*- coding: utf-8 -*-
"""
OROVA Email Sequence Skill — Multi-Step Drip Campaigns
Inspired by OROVA Master Skills: email-sequence

Creates automated, multi-step follow-up sequences with configurable
delays and conditions. All emails are queued for CEO approval.
"""

import logging
import json
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SEQUENCE TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════

SEQUENCES = {
    "cold_intro_drip": {
        "name": "Cold Intro Drip (5-Touch)",
        "description": "5-email cold outreach sequence with increasing urgency",
        "emails": [
            {
                "delay_days": 0,
                "subject_template": "Quick question about {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I noticed {company} is doing great work in {industry}. "
                    "We help businesses like yours generate 3-5x more qualified leads using AI-powered outreach.\n\n"
                    "Would it make sense to chat for 10 minutes this week?\n\n"
                    "— Mark, CEO of OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Initial introduction"
            },
            {
                "delay_days": 3,
                "subject_template": "Re: Quick question about {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Just circling back — I know you're busy. "
                    "We recently helped a {industry} company increase their qualified leads by 340% in 60 days.\n\n"
                    "Happy to share the playbook if you're interested.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Social proof follow-up"
            },
            {
                "delay_days": 7,
                "subject_template": "Free audit for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I ran a quick analysis on {company}'s online presence and found a few opportunities "
                    "that could significantly boost your lead flow.\n\n"
                    "Would you like me to send over the findings? No strings attached.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Value-first offer"
            },
            {
                "delay_days": 14,
                "subject_template": "Last thought for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I don't want to be that person who keeps emailing, so this will be my last note.\n\n"
                    "If lead generation is ever a priority for {company}, we'd love to help. "
                    "Our AI-powered system runs 24/7 so you don't have to.\n\n"
                    "Here when you're ready.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Break-up email"
            },
            {
                "delay_days": 30,
                "subject_template": "Update from OROVA",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "It's been a month since I reached out. We've since launched some new AI capabilities "
                    "that are getting incredible results for {industry} businesses.\n\n"
                    "If you're open to a quick 10-min call, I'd love to show you what's possible.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Re-engage after cooling period"
            }
        ]
    },
    "nurture_7day": {
        "name": "7-Day Nurture (Post-Interest)",
        "description": "For leads who showed initial interest but haven't committed",
        "emails": [
            {
                "delay_days": 0,
                "subject_template": "Great connecting, {first_name}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Great chatting with you! As promised, here's a quick overview of how OROVA "
                    "can help {company} scale lead generation.\n\n"
                    "Our 3-tier approach:\n"
                    "1. AI-powered prospecting (finds leads 24/7)\n"
                    "2. Personalized multi-channel outreach\n"
                    "3. Automated follow-up sequences\n\n"
                    "Let me know if you'd like to dive deeper into any of these.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Post-conversation recap"
            },
            {
                "delay_days": 2,
                "subject_template": "Case study: {industry} results",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Thought you'd find this interesting — we helped a {industry} company go from "
                    "12 leads/month to 47 leads/month in just 8 weeks.\n\n"
                    "The best part? It's fully automated. Their team didn't have to lift a finger.\n\n"
                    "Would something like this work for {company}?\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Case study / social proof"
            },
            {
                "delay_days": 5,
                "subject_template": "Proposal ready for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I put together a custom proposal for {company} based on our conversation. "
                    "It includes specific strategies for the {industry} market in {location}.\n\n"
                    "When's a good time to walk through it? I'm flexible this week.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Proposal push"
            }
        ]
    },
    "re_engage_30day": {
        "name": "30-Day Re-Engagement",
        "description": "For cold leads that went silent, bringing them back",
        "emails": [
            {
                "delay_days": 0,
                "subject_template": "Thought of {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "We were reviewing our pipeline and {company} came up. "
                    "I know the timing wasn't right before, but I wanted to check in.\n\n"
                    "We've made some big upgrades to our AI engine — "
                    "results are better than ever for {industry} businesses.\n\n"
                    "Worth a quick call?\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Warm re-engagement"
            },
            {
                "delay_days": 7,
                "subject_template": "New results in {industry}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Quick update: one of our {industry} clients just hit their best month ever — "
                    "67 qualified leads, 12 meetings booked, 3 new clients. All automated.\n\n"
                    "If {company} is looking to grow this quarter, I'd love to help.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Updated social proof"
            }
        ]
    },
    "post_meeting": {
        "name": "Post-Meeting Follow-Up",
        "description": "After a discovery call or meeting",
        "emails": [
            {
                "delay_days": 0,
                "subject_template": "Next steps for {company} + OROVA",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Thanks for the great conversation today! Here are the next steps we discussed:\n\n"
                    "1. I'll send over the custom proposal by end of week\n"
                    "2. Our team will run the initial SEO audit on {company}'s site\n"
                    "3. We'll schedule a follow-up call to review findings\n\n"
                    "Looking forward to working together.\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Meeting recap + next steps"
            },
            {
                "delay_days": 3,
                "subject_template": "Your {company} audit results",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "As promised, we ran the initial analysis on {company}. "
                    "Found some quick wins that could boost your lead flow significantly.\n\n"
                    "Shall I walk you through the findings on a quick call?\n\n"
                    "— Mark, OROVA\nLos Angeles, CA | Reply 'STOP' to opt out"
                ),
                "purpose": "Deliver audit + push for next meeting"
            }
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def create_drip_campaign(
    prospect: dict,
    sequence_type: str = "cold_intro_drip"
) -> str:
    """
    Generate a complete drip campaign for a prospect.

    Args:
        prospect: Dict with keys: first_name, company, industry, location, email
        sequence_type: One of: cold_intro_drip, nurture_7day, re_engage_30day, post_meeting

    Returns:
        Formatted campaign preview with all emails
    """
    sequence = SEQUENCES.get(sequence_type)
    if not sequence:
        available = ", ".join(SEQUENCES.keys())
        return f"⚠️ Unknown sequence type '{sequence_type}'. Available: {available}"

    first_name = prospect.get("first_name", "there")
    company = prospect.get("company", "your company")
    industry = prospect.get("industry", "your industry")
    location = prospect.get("location", "your area")
    email = prospect.get("email", "")

    report = f"# 📧 Drip Campaign: {sequence['name']}\n"
    report += f"**Prospect:** {first_name} at {company}\n"
    report += f"**Sequence:** {sequence['description']}\n"
    report += f"**Total emails:** {len(sequence['emails'])}\n\n"

    today = datetime.now()

    for i, email_template in enumerate(sequence["emails"], 1):
        send_date = today + timedelta(days=email_template["delay_days"])
        subject = email_template["subject_template"].format(
            first_name=first_name, company=company, industry=industry, location=location
        )
        body = email_template["body_template"].format(
            first_name=first_name, company=company, industry=industry, location=location
        )

        report += f"---\n"
        report += f"### Email {i}/{len(sequence['emails'])} — {email_template['purpose']}\n"
        report += f"**Send date:** {send_date.strftime('%b %d, %Y')} (Day +{email_template['delay_days']})\n"
        report += f"**Subject:** {subject}\n\n"
        report += f"```\n{body}\n```\n\n"

    report += "---\n"
    report += "✅ **Campaign ready.** All emails will be queued for CEO approval before sending.\n"

    logger.info(f"[DRIP] Generated '{sequence_type}' campaign for {company} ({len(sequence['emails'])} emails)")
    return report


async def list_sequence_types() -> str:
    """List available drip campaign sequence types."""
    report = "# 📧 Available Email Sequences\n\n"
    for key, seq in SEQUENCES.items():
        report += f"- **`{key}`** — {seq['name']}: {seq['description']} ({len(seq['emails'])} emails)\n"
    return report
