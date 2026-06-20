# -*- coding: utf-8 -*-
"""
OROVA Email Sequence Skill — Multi-Step Drip Campaigns
Inspired by OpenClaw Master Skills: email-sequence

Creates automated, multi-step follow-up sequences with configurable
delays and conditions. All emails are queued for CEO approval.
"""

import logging
import json
import os
import re
from datetime import datetime, timedelta
import asyncio

from app.core.database import DatabaseManager

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
                    "— Mark, CEO of OROVA"
                ),
                "purpose": "Initial introduction"
            },
            {
                "delay_days": 2,
                "subject_template": "Re: Quick question about {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Just circling back — I know you're busy. "
                    "We recently helped a {industry} company increase their qualified leads by 340% in 60 days.\n\n"
                    "Happy to share the playbook if you're interested.\n\n"
                    "— Mark"
                ),
                "purpose": "Social proof follow-up"
            },
            {
                "delay_days": 4,
                "subject_template": "Free audit for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I ran a quick analysis on {company}'s online presence and found a few opportunities "
                    "that could significantly boost your lead flow.\n\n"
                    "Would you like me to send over the findings? No strings attached.\n\n"
                    "— Mark"
                ),
                "purpose": "Value-first offer"
            },
            {
                "delay_days": 6,
                "subject_template": "Last thought for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I don't want to be that person who keeps emailing, so this will be my last note.\n\n"
                    "If lead generation is ever a priority for {company}, we'd love to help. "
                    "Our AI-powered system runs 24/7 so you don't have to.\n\n"
                    "Here when you're ready.\n\n"
                    "— Mark, OROVA"
                ),
                "purpose": "Break-up email"
            },
            {
                "delay_days": 8,
                "subject_template": "Update from OROVA",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "It's been a month since I reached out. We've since launched some new AI capabilities "
                    "that are getting incredible results for {industry} businesses.\n\n"
                    "If you're open to a quick 10-min call, I'd love to show you what's possible.\n\n"
                    "— Mark"
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
                    "— Mark"
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
                    "— Mark"
                ),
                "purpose": "Case study / social proof"
            },
            {
                "delay_days": 4,
                "subject_template": "Proposal ready for {company}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "I put together a custom proposal for {company} based on our conversation. "
                    "It includes specific strategies for the {industry} market in {location}.\n\n"
                    "When's a good time to walk through it? I'm flexible this week.\n\n"
                    "— Mark"
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
                    "— Mark"
                ),
                "purpose": "Warm re-engagement"
            },
            {
                "delay_days": 2,
                "subject_template": "New results in {industry}",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "Quick update: one of our {industry} clients just hit their best month ever — "
                    "67 qualified leads, 12 meetings booked, 3 new clients. All automated.\n\n"
                    "If {company} is looking to grow this quarter, I'd love to help.\n\n"
                    "— Mark"
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
                    "— Mark"
                ),
                "purpose": "Meeting recap + next steps"
            },
            {
                "delay_days": 2,
                "subject_template": "Your {company} audit results",
                "body_template": (
                    "Hi {first_name},\n\n"
                    "As promised, we ran the initial analysis on {company}. "
                    "Found some quick wins that could boost your lead flow significantly.\n\n"
                    "Shall I walk you through the findings on a quick call?\n\n"
                    "— Mark"
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
    Generate a complete drip campaign preview for a prospect.

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

    report = f"# 📧 Drip Campaign: {sequence['name']}\n"
    report += f"**Prospect:** {first_name} at {company}\n"
    report += f"**Sequence:** {sequence['description']}\n"
    report += f"**Total emails:** {len(sequence['emails'])}\n\n"

    today = datetime.now()

    for i, email_template in enumerate(sequence["emails"], 1):
        send_date = today + timedelta(days=2 * (i - 1))
        subject = email_template["subject_template"].format(
            first_name=first_name, company=company, industry=industry, location=location
        )
        body = email_template["body_template"].format(
            first_name=first_name, company=company, industry=industry, location=location
        )

        report += f"---\n"
        report += f"### Email {i}/{len(sequence['emails'])} — {email_template['purpose']}\n"
        report += f"**Estimated Send:** {send_date.strftime('%b %d, %Y')} (Day +{2 * (i - 1)})\n"
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


async def start_drip_campaign(lead_id: int, sequence_type: str = "cold_intro_drip") -> dict:
    """
    Start an automated drip campaign for a lead.
    Inserts record into drip_campaigns table and triggers the first send.
    """
    # Check if lead exists
    lead_row = await DatabaseManager.fetchone("SELECT * FROM leads WHERE id = ?", (lead_id,))
    if not lead_row:
        return {"status": "error", "message": f"Lead with ID {lead_id} not found."}
        
    lead = dict(lead_row)
    
    # Check if active campaign already exists
    existing = await DatabaseManager.fetchone("SELECT id FROM drip_campaigns WHERE lead_id = ? AND status = 'active'", (lead_id,))
    if existing:
        return {"status": "error", "message": f"Active drip campaign already exists for lead {lead_id}."}
        
    now = datetime.now()
    # Schedule first send for right now
    await DatabaseManager.query(
        """INSERT OR REPLACE INTO drip_campaigns (lead_id, sequence_type, status, current_step, last_sent_at, next_send_at, client_id)
           VALUES (?, ?, 'active', 0, NULL, ?, ?)""",
        (lead_id, sequence_type, now.isoformat(), lead.get("client_id", 0))
    )
    
    logger.info(f"[DRIP] Drip campaign '{sequence_type}' started for lead {lead_id} ({lead.get('business')})")
    
    # Process pending drip campaigns immediately to send the first email
    await send_pending_drip_emails()
    
    return {"status": "success", "message": f"Drip campaign started and first step processed."}


async def send_pending_drip_emails():
    """
    Finds active drip campaigns due to send and sends their next email.
    Schedules next emails exactly 2 days apart (cadence constraint).
    """
    from app.skills.agentmail_skill import send_outreach
    
    # Get active campaigns that are due
    rows = await DatabaseManager.fetchall(
        """SELECT dc.id as campaign_id, dc.lead_id, dc.sequence_type, dc.current_step, dc.client_id,
                  l.email, l.business, l.owner, l.vertical
           FROM drip_campaigns dc 
           JOIN leads l ON dc.lead_id = l.id 
           WHERE dc.status = 'active' AND (dc.next_send_at IS NULL OR datetime(dc.next_send_at) <= datetime('now'))"""
    )
    
    for row in rows:
        lead_id = row["lead_id"]
        campaign_id = row["campaign_id"]
        seq_type = row["sequence_type"]
        step = row["current_step"]
        email = row["email"]
        business = row["business"]
        owner = row["owner"]
        vertical = row["vertical"]
        client_id = row["client_id"]
        
        if not email:
            logger.warning(f"[DRIP] Lead {lead_id} ({business}) has no email address. Skipping.")
            await DatabaseManager.query(
                "UPDATE drip_campaigns SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,)
            )
            continue
            
        sequence = SEQUENCES.get(seq_type)
        if not sequence or step >= len(sequence["emails"]):
            await DatabaseManager.query(
                "UPDATE drip_campaigns SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,)
            )
            continue
            
        email_template = sequence["emails"][step]
        
        first_name = owner.split(" ")[0] if owner else "there"
        
        # Consult learned strategy for optimal email framework if any exists
        # This will be integrated into the self-improvement loop
        framework_row = await DatabaseManager.fetchone(
            "SELECT strategy_value FROM learned_strategies WHERE strategy_type = 'email_framework' AND active = 1 ORDER BY win_rate DESC LIMIT 1"
        )
        framework = framework_row["strategy_value"] if framework_row else "pas"
        
        subject = email_template["subject_template"].format(
            first_name=first_name, company=business, industry=vertical or "your space", location="California"
        )
        body = email_template["body_template"].format(
            first_name=first_name, company=business, industry=vertical or "your space", location="California"
        )
        
        logger.info(f"[DRIP] Sending step {step+1}/{len(sequence['emails'])} of {seq_type} to {email}")
        
        try:
            send_res = await send_outreach(
                to=email,
                subject=subject,
                body=body,
                recipient_context=f"Lead: {owner} at {business}. Vertical: {vertical}.",
                lead_id=lead_id,
                strategy=email_template.get("purpose", "intro"),
                niche=vertical,
                client_id=client_id
            )
            
            if send_res.get("status") == "rejected":
                logger.warning(f"[DRIP] Drip email rejected for lead {lead_id}. Pausing campaign.")
                await DatabaseManager.query(
                    "UPDATE drip_campaigns SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (campaign_id,)
                )
                continue
                
            next_step = step + 1
            last_sent = datetime.now().isoformat()
            
            if next_step >= len(sequence["emails"]):
                await DatabaseManager.query(
                    """UPDATE drip_campaigns 
                       SET status = 'completed', current_step = ?, last_sent_at = ?, next_send_at = NULL, updated_at = CURRENT_TIMESTAMP 
                       WHERE id = ?""",
                    (next_step, last_sent, campaign_id)
                )
                await DatabaseManager.query(
                    "UPDATE leads SET status = 'Contacted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (lead_id,)
                )
                await update_sheets_lead_status(business, "Contacted")
            else:
                # Drip sequence constraint: Space exactly 2 days (48 hours) apart
                next_send = (datetime.now() + timedelta(days=2)).isoformat()
                await DatabaseManager.query(
                    """UPDATE drip_campaigns 
                       SET current_step = ?, last_sent_at = ?, next_send_at = ?, updated_at = CURRENT_TIMESTAMP 
                       WHERE id = ?""",
                    (next_step, last_sent, next_send, campaign_id)
                )
                await DatabaseManager.query(
                    "UPDATE leads SET status = 'Contacted', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (lead_id,)
                )
                await update_sheets_lead_status(business, "Contacted")
                
        except Exception as e:
            logger.error(f"[DRIP] Failed to send drip email to {email}: {e}")


async def check_drip_replies_and_process():
    """
    Checks inbox replies, cross-references with active drip campaign leads.
    If a reply is found:
      1. Stops the campaign sequence (status='stopped_by_reply')
      2. Updates lead status to 'Replied'
      3. Generates suggested AI response
      4. Notifies CEO via Telegram with details + draft response.
    """
    from app.skills.agentmail_skill import check_replies, _send_telegram_alert
    
    logger.info("[DRIP] Scanning for replies and processing active sequences...")
    res = check_replies(limit=20)
    if res.get("status") != "success":
        return
    
    messages = res.get("messages", [])
    if not messages:
        return
        
    rows = await DatabaseManager.fetchall(
        """SELECT dc.id as campaign_id, dc.lead_id, l.email, l.business, l.owner, l.status as lead_status 
           FROM drip_campaigns dc 
           JOIN leads l ON dc.lead_id = l.id 
           WHERE dc.status = 'active'"""
    )
    if not rows:
        return
        
    active_by_email = {row["email"].strip().lower(): row for row in rows if row["email"]}
    
    for msg in messages:
        sender = msg.get("from", "").strip().lower()
        email_match = re.search(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", sender)
        sender_email = email_match.group(0).lower() if email_match else sender
            
        if sender_email in active_by_email:
            campaign = active_by_email[sender_email]
            lead_id = campaign["lead_id"]
            campaign_id = campaign["campaign_id"]
            business = campaign["business"]
            owner = campaign["owner"]
            
            logger.info(f"[DRIP] Lead {business} replied! Stopping sequence.")
            
            # Stop drip campaign
            await DatabaseManager.query(
                "UPDATE drip_campaigns SET status = 'stopped_by_reply', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (campaign_id,)
            )
            # Update lead status in DB
            await DatabaseManager.query(
                "UPDATE leads SET status = 'Replied', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (lead_id,)
            )
            
            # Update CRM Sheets
            await update_sheets_lead_status(business, "Replied")
            
            # Record replied outcome for self-improvement
            try:
                now = datetime.now()
                # Update metrics
                await DatabaseManager.aupdate_metrics({"replies_received": 1}, client_id=0)
                await DatabaseManager.query(
                    """INSERT INTO outreach_outcomes (action, strategy, niche, recipient, lead_id, result, quality_score, send_hour, send_day, metadata, client_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("email_reply", "drip", "", sender_email, lead_id, "replied", 100.0, now.hour, now.weekday(), json.dumps({"snippet": msg.get("snippet")}), 0)
                )
            except Exception as db_err:
                logger.error(f"Failed to log reply outcome: {db_err}")
            
            # Generate suggestion reply
            snippet = msg.get("snippet", "")
            ai_reply_draft = await generate_reply_suggestion(snippet, owner, business)
            
            alert_msg = (
                f"📬 **Prospect Replied! Sequence Stopped**\n\n"
                f"**Lead:** {owner} at **{business}** ({sender_email})\n"
                f"**Snippet:** \"{snippet}...\"\n\n"
                f"💡 **Suggested AI Reply:**\n"
                f"```\n{ai_reply_draft}\n```"
            )
            _send_telegram_alert(alert_msg)


async def update_sheets_lead_status(company_name: str, new_status: str):
    """Update lead status in CRM Sheets."""
    try:
        from app.worker import _get_sheets_client, COL_IDX_COMPANY, COL_SHEET_STATUS
        loop = asyncio.get_event_loop()
        client_auth = await loop.run_in_executor(None, _get_sheets_client)
        sheet_name = os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")
        sheet = await loop.run_in_executor(None, lambda: client_auth.open(sheet_name).sheet1)
        rows = await loop.run_in_executor(None, sheet.get_all_values)
        
        for idx, row in enumerate(rows[1:], start=2):
            company = row[COL_IDX_COMPANY] if len(row) > COL_IDX_COMPANY else ""
            if company.lower() == company_name.lower():
                await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, new_status))
                logger.info(f"[DRIP] Sheets status updated to '{new_status}' for '{company_name}'")
                break
    except Exception as e:
        logger.error(f"[DRIP] Sheets status update failed for {company_name}: {e}")


async def generate_reply_suggestion(incoming_message: str, prospect_name: str, company: str) -> str:
    """Generate email response suggestions."""
    from app.core.ai_client import UnifiedAIClient
    prompt = f"""
    A lead has replied to our outreach. Draft a polite, professional reply to keep the conversation going and book a meeting.
    
    PROSPECT: {prospect_name}
    COMPANY: {company}
    INCOMING MESSAGE:
    "{incoming_message}"
    
    Keep the reply under 150 words. Focus on finding a time for a 15-minute meeting.
    Do not include email headers (To/Subject). Just the body.
    """
    ai = UnifiedAIClient()
    try:
        suggestion = await ai.write(prompt)
        return suggestion.strip()
    except Exception as e:
        return f"Error generating suggestion: {e}"
