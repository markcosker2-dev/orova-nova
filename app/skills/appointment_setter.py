# -*- coding: utf-8 -*-
"""
OROVA Autonomous Appointment Setter — Elite Feature 2
======================================================
When a lead replies positively (Interested status) or reaches Elite Score 85+,
Nova autonomously prepares a premium Pre-Alignment Brief and offers
specific calendar slots — without waiting for Owner intervention.

The Sequence (fully automated):
1. Lead triggers Interested status (via email reply or call sentiment)
2. Nova generates a Pre-Alignment Brief (1 page, luxury formatted)
3. Nova emails the Brief within 15 minutes of the trigger
4. Nova sends [REVENUE ALERT] to Owner
5. If lead books: Nova logs Appointment, notifies Owner, generates Meeting Intelligence Package
"""

import logging
import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Close signal keywords — trigger appointment setting immediately (SOP 004)
CLOSE_SIGNALS = [
    "how does it work",
    "what does it cost",
    "tell me more",
    "send me information",
    "let's talk",
    "let's chat",
    "sounds interesting",
    "i'm interested",
    "interested",
    "how much",
    "pricing",
    "what's the cost",
    "set up a call",
    "schedule a call",
    "let's do it",
    "sign me up",
    "i'm in",
    "count me in",
]


def detect_close_signal(reply_text: str) -> bool:
    """Check if a reply contains any close signal keywords (SOP 004)."""
    lower = reply_text.lower()
    return any(signal in lower for signal in CLOSE_SIGNALS)


async def generate_pre_alignment_brief(
    lead: Dict,
    ai_client=None,
) -> str:
    """
    Generate a Pre-Alignment Brief for a high-intent lead.
    Follows the MSI template exactly.

    Args:
        lead: Lead dict with business, contact, vertical, email, etc.
        ai_client: UnifiedAIClient for AI generation

    Returns:
        Formatted brief text ready to email
    """
    name = (lead.get("contact") or "").split()[0] if lead.get("contact") else "there"
    company = lead.get("business", "your company")
    vertical = lead.get("vertical", "home services")
    email = lead.get("email", "")

    # Generate calendar slot options based on YOUR availability
    from app.core.smart_calling import calling_hours
    available = calling_hours.get_available_slots(days_ahead=10)

    if len(available) >= 2:
        slot1_display = available[0]["display"]
        slot2_display = available[1]["display"]
        day1 = slot1_display
        day2 = slot2_display
    else:
        # Fallback
        now = datetime.datetime.now()
        days_ahead = 1
        slot1 = now + datetime.timedelta(days=days_ahead)
        while slot1.weekday() >= 5:
            days_ahead += 1
            slot1 = now + datetime.timedelta(days=days_ahead)
        slot2 = slot1 + datetime.timedelta(days=1)
        while slot2.weekday() >= 5:
            slot2 += datetime.timedelta(days=1)
        day1 = slot1.strftime("%A, %B %d") + " at 11:00 PM"
        day2 = slot2.strftime("%A, %B %d") + " at 11:00 AM"

    # Use AI to generate the brief if available, otherwise use template
    if ai_client:
        try:
            prompt = f"""Generate a Pre-Alignment Brief for a high-intent lead. Follow these rules EXACTLY:

LEAD CONTEXT:
- Name: {name}
- Company: {company}
- Vertical: {vertical}

RULES:
- Greeting: "{name}—" (em-dash, no "Hi" or "Dear")
- No exclamation marks. No emojis.
- Two sentences about who OROVA is (outcome-focused)
- What OROVA delivers for {vertical} specifically
- One relevant case study with specific numbers
- 3-bullet proposed meeting agenda
- Two specific calendar slot options: {day1} and {day2}
- Closing: "— Nova\\nExecutive Director, OROVA"
- Max 150 words total
- No "help", "affordable", "cheap", "quick chat"

Return ONLY the brief text. No commentary."""

            brief = await ai_client.write(prompt)
            if brief and len(brief.strip()) > 50:
                return brief.strip()
        except Exception as e:
            logger.warning(f"[APPOINTMENT] AI brief generation failed: {e}")

    # Fallback: Template-based brief
    brief = f"""{name}—

Following your response, I have prepared a brief context document
for our alignment.

OROVA engineers AI-powered acquisition systems for {vertical} businesses.
Our current focus is on operators running $500k+ annual revenue who want
to systematize their lead flow without adding headcount.

What we achieved for a comparable operator:
47 qualified {vertical} consultations sourced in 30 days. No shared leads.
No agency markup on ad spend.

Our proposed agenda (15 minutes):
  — Your current acquisition model and primary constraint
  — Where OROVA's system would integrate
  — Whether a pilot engagement makes sense

Two options for a brief technical alignment:
  {day1}
  {day2}

— Nova
  Executive Director, OROVA"""

    return brief


async def generate_meeting_intel_package(lead: Dict, ai_client=None) -> str:
    """
    Generate a Meeting Intelligence Package for the Owner.
    Sent T-24 hours before the meeting (SOP 003).

    Returns:
        Formatted intel package text
    """
    company = lead.get("business", "Unknown Company")
    vertical = lead.get("vertical", "Unknown")
    contact = lead.get("contact", "Unknown")
    score = lead.get("score", 0)
    notes = lead.get("notes", "No additional intel")

    # Determine recommended proposal tier
    if score >= 85:
        tier = "Elite"
        value_range = "$5,000 - $15,000/month"
    elif score >= 70:
        tier = "Growth"
        value_range = "$2,500 - $5,000/month"
    else:
        tier = "Starter"
        value_range = "$1,500 - $2,500/month"

    package = f"""MEETING INTELLIGENCE PACKAGE
────────────────────────────────────────

Company: {company}
Contact: {contact}
Vertical: {vertical}
Elite Score: {score}/100

Company Overview:
  — {vertical.title()} operator
  — Identified via OROVA pipeline
  — Intel: {notes[:200]}

Estimated Contract Value: {value_range}

Primary Pain Point:
  — Reliance on shared leads (HomeAdvisor/Angi fatigue)
  — No systematized acquisition process
  — Growth constrained by referral dependency

Recommended Proposal Tier: {tier}

Suggested Opening Question:
  "What does your current lead acquisition process look like,
   and where are you seeing the most friction?"

────────────────────────────────────────
Prepared by Nova — OROVA Central Intelligence"""

    return package


async def run_appointment_setter(lead_id: int, trigger: str = "score_threshold"):
    """
    Main entry point: Trigger the autonomous appointment setting flow.

    Args:
        lead_id: Database lead ID
        trigger: "score_threshold" (85+), "reply_interested", "close_signal"
    """
    try:
        from app.core.database import DatabaseManager
        from app.core.ai_client import UnifiedAIClient
        from app.core.signal_protocol import send_revenue_alert
        from app.skills.agentmail_skill import send_outreach

        # Get lead data
        lead = DatabaseManager.query(
            "SELECT * FROM leads WHERE id = ?", (lead_id,), fetchone=True
        )
        if not lead:
            logger.warning(f"[APPOINTMENT] Lead {lead_id} not found")
            return

        lead_dict = dict(lead)
        email = lead_dict.get("email")
        if not email:
            logger.warning(f"[APPOINTMENT] Lead {lead_id} has no email — cannot send brief")
            return

        company = lead_dict.get("business", "Unknown")
        score = lead_dict.get("score", 0)

        logger.info(f"[APPOINTMENT] Triggering for {company} (score={score}, trigger={trigger})")

        # 1. Generate Pre-Alignment Brief
        ai_client = UnifiedAIClient()
        brief = await generate_pre_alignment_brief(lead_dict, ai_client)

        # 2. Run through Luxury Filter
        from app.core.luxury_filter import critique_and_rewrite
        final_brief, critique = await critique_and_rewrite(
            brief, content_type="email", ai_client=ai_client
        )

        # 3. Send the brief
        subject = f"OROVA — Technical alignment for {company}"
        result = send_outreach(to=email, subject=subject, body=final_brief)

        if result.get("status") in ("success", "sent"):
            logger.info(f"[APPOINTMENT] Pre-Alignment Brief sent to {email}")

            # Update lead status
            DatabaseManager.query(
                "UPDATE leads SET status = 'Brief Sent', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (lead_id,)
            )

            # Update metrics
            metrics = DatabaseManager.get_metrics(0)
            DatabaseManager.update_metrics(
                {"proposals_sent": metrics.get("proposals_sent", 0) + 1}
            )

            # 4. Signal Protocol: REVENUE ALERT
            send_revenue_alert(
                client_name=company,
                vertical=lead_dict.get("vertical", "Unknown"),
                elite_score=score,
                status="Pre-Alignment Brief Sent",
                projected_value="$2,500 - $15,000/month",
                next_action="Monitoring for booking confirmation. Meeting Intel Package on standby.",
            )
        else:
            logger.error(f"[APPOINTMENT] Brief send failed: {result.get('message')}")

    except Exception as e:
        logger.error(f"[APPOINTMENT] Appointment setter failed: {e}")
