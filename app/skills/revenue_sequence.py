# -*- coding: utf-8 -*-
"""
OROVA 17-Day Revenue Sequence (SOP 002)
========================================
Every qualified lead follows this exact sequence. No exceptions.
Each step is logged in the database. No step is skipped.

Day 0  — Initial Outreach (Aria)
Day 3  — Loop 1 (Echo — 1-3 sentence bump)
Day 10 — Loop 2 (Echo — Value Add)
Day 14 — AI Voice Call (Rex — Retell)
Day 17 — Loop 3: The Break (Echo — breakup email)

Send window: Tuesday-Thursday, 8:00-10:00 AM local time
"""

import logging
import datetime
import asyncio
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# SEQUENCE DEFINITION (MSI SOP 002)
# ═══════════════════════════════════════════════════════════════════════════════

SEQUENCE_STEPS = [
    {
        "day": 0,
        "agent": "Aria",
        "type": "email",
        "name": "Initial Outreach",
        "description": "Cold email: Timeline hook + one result + one CTA",
        "template": (
            "{name}—\n\n"
            "We sourced {result_count} qualified {vertical} consultations for a "
            "{location} firm in 30 days—no agency fees, no shared leads.\n\n"
            "OROVA engineers AI-powered acquisition systems for {vertical} operators "
            "running $500k+ annual revenue who want to systematize lead flow "
            "without adding headcount.\n\n"
            "My calendar is open {day1} at {time1} ET for a brief technical alignment.\n\n"
            "— Nova\n"
            "Executive Director, OROVA"
        ),
    },
    {
        "day": 3,
        "agent": "Echo",
        "type": "email",
        "name": "Loop 1 — Bump",
        "description": "1-3 sentence bump. No re-pitch. Effortless to reply.",
        "template": (
            "{name}—\n\n"
            "Bumping this up—timing may simply be off. "
            "If sourcing {result_count}+ qualified estimates monthly is a priority "
            "in your current cycle, reply and I will pick it up from there.\n\n"
            "— Nova\n"
            "OROVA"
        ),
    },
    {
        "day": 10,
        "agent": "Echo",
        "type": "email",
        "name": "Loop 2 — Value Add",
        "description": "Industry insight or mini case study (2 sentences max). New angle.",
        "template": (
            "{name}—\n\n"
            "A {vertical} operator in {location} closed $47k in new contracts last month "
            "from leads our system sourced—zero ad spend, zero shared leads.\n\n"
            "Different angle than my last note. If acquisition efficiency is on "
            "your radar this quarter, I am available for a 15-minute alignment.\n\n"
            "— Nova\n"
            "OROVA"
        ),
    },
    {
        "day": 14,
        "agent": "Rex",
        "type": "call",
        "name": "AI Voice Call",
        "description": "Pattern-interrupt opener. AIDA structure + objection handling.",
        "script": (
            "Hi, this is Nova from OROVA. I know this is completely out of the blue, "
            "and I only need 27 seconds—if what I say doesn't apply, I'll hang up. Fair?\n\n"
            "We engineer AI-powered lead systems for {vertical} businesses like {company}. "
            "Last month we sourced {result_count} qualified consultations for a similar operator "
            "in {location}—no shared leads, no agency fees.\n\n"
            "Is systematizing your lead flow something that's on your radar right now, "
            "or is the timing off?"
        ),
    },
    {
        "day": 17,
        "agent": "Echo",
        "type": "email",
        "name": "Loop 3 — The Break",
        "description": "Break-up email. Often gets highest reply rate.",
        "template": (
            "{name}—\n\n"
            "I will stop after this—timing may simply be off.\n\n"
            "If you want to revisit sourcing qualified {vertical} leads "
            "without sharing them with 4 other contractors, "
            "reply yes and I will pick it up from there.\n\n"
            "— Nova\n"
            "OROVA"
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# SEQUENCE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════

class RevenueSequence:
    """
    Manages the 17-Day Revenue Sequence for each lead.
    """

    @staticmethod
    def get_next_step(lead: Dict) -> Optional[Dict]:
        """
        Determine the next step in the sequence for a lead.

        Args:
            lead: Lead dict with sequence_position, created_at, status

        Returns:
            Next step dict or None if sequence is complete
        """
        position = lead.get("sequence_position", 0)
        status = lead.get("status", "New")

        # If lead replied or is DNC, stop sequence
        if status.lower() in ("replied", "interested", "dnc", "archived", "closed won", "closed lost"):
            return None

        # Find next step
        for step in SEQUENCE_STEPS:
            if step["day"] > position or (step["day"] == position and position == 0):
                # Check if it's time for this step
                created = lead.get("created_at", "")
                if created:
                    try:
                        created_dt = datetime.datetime.fromisoformat(str(created).replace("Z", ""))
                        target_date = created_dt + datetime.timedelta(days=step["day"])
                        now = datetime.datetime.now()

                        if now >= target_date:
                            return step
                    except Exception:
                        pass

        return None  # Sequence complete

    @staticmethod
    def format_email(step: Dict, lead: Dict) -> Dict:
        """
        Format an email template with lead-specific data.

        Returns:
            Dict with to, subject, body
        """
        name = lead.get("contact", "").split()[0] if lead.get("contact") else "there"
        company = lead.get("business", "your company")
        vertical = lead.get("vertical", "home services")
        location = lead.get("location", "your area")
        email = lead.get("email", "")

        # Generate dynamic values
        now = datetime.datetime.now()
        day1 = (now + datetime.timedelta(days=2)).strftime("%A")
        time1 = "10:00 AM"
        result_count = "20"

        body = step.get("template", "").format(
            name=name,
            company=company,
            vertical=vertical,
            location=location,
            day1=day1,
            time1=time1,
            result_count=result_count,
        )

        # Subject line varies by step
        subjects = {
            0: f"{vertical.title()} acquisition — {company}",
            3: f"Re: {vertical.title()} acquisition — {company}",
            10: f"New data for {company}",
            17: f"Closing the loop — {company}",
        }
        subject = subjects.get(step["day"], f"OROVA — {company}")

        return {
            "to": email,
            "subject": subject,
            "body": body,
            "step_name": step["name"],
            "step_day": step["day"],
        }

    @staticmethod
    def is_send_window() -> bool:
        """
        Check if current time is within the send window.
        Send window: Tuesday-Thursday, 8:00-10:00 AM local time.
        Returns True during valid window for outreach.
        """
        now = datetime.datetime.now()
        weekday = now.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu

        # Tuesday (1) through Thursday (3)
        if weekday not in (1, 2, 3):
            return False

        # 8:00 AM to 10:00 AM
        hour = now.hour
        if hour < 8 or hour >= 10:
            return False

        return True

    @staticmethod
    def advance_position(lead_id: int, day: int):
        """Update the lead's sequence position after a step is executed."""
        try:
            from app.core.database import DatabaseManager
            DatabaseManager.query(
                "UPDATE leads SET sequence_position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (day, lead_id),
            )
            logger.info(f"[SEQUENCE] Lead {lead_id} advanced to Day {day}")
        except Exception as e:
            logger.error(f"[SEQUENCE] Failed to advance lead {lead_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER JOB: Process Revenue Sequence Queue
# ═══════════════════════════════════════════════════════════════════════════════

async def process_sequence_queue():
    """
    Main scheduler job: check all active leads and execute due sequence steps.
    Called by the scheduler at 09:00 ET daily.
    """
    from app.core.database import DatabaseManager
    from app.core.dnc_manager import DNCManager
    from app.core.lead_scorer import LeadScorer
    from app.core.luxury_filter import critique_and_rewrite
    from app.core.ai_client import UnifiedAIClient

    logger.info("[SEQUENCE] Processing revenue sequence queue...")

    # Only run during send window
    if not RevenueSequence.is_send_window():
        logger.info("[SEQUENCE] Outside send window (Tue-Thu, 8-10 AM). Skipping.")
        return

    # Get all active leads
    leads = DatabaseManager.query(
        """SELECT * FROM leads 
           WHERE status NOT IN ('DNC', 'Archived', 'Closed Won', 'Closed Lost')
           AND score >= ?
           ORDER BY score DESC""",
        (65,),  # SOP 001: Minimum outreach score
        fetchall=True,
    )

    if not leads:
        logger.info("[SEQUENCE] No qualified leads in pipeline.")
        return

    processed = 0
    ai_client = UnifiedAIClient()

    for lead in leads:
        lead_dict = dict(lead)

        # Check DNC
        if DNCManager.is_dnc(email=lead_dict.get("email"), phone=lead_dict.get("phone")):
            continue

        # Check 90-day cooldown
        if DNCManager.check_90_day_cooldown(email=lead_dict.get("email")):
            continue

        # Get next step
        step = RevenueSequence.get_next_step(lead_dict)
        if not step:
            continue

        # Execute step
        if step["type"] == "email":
            email_data = RevenueSequence.format_email(step, lead_dict)

            # Run through Luxury Filter
            final_body, critique = await critique_and_rewrite(
                email_data["body"],
                content_type="email",
                ai_client=ai_client,
                context={"lead_name": lead_dict.get("contact"), "company": lead_dict.get("business")},
            )

            if critique and critique.get("approved", False):
                # Queue for sending (goes through rate limiter)
                email_data["body"] = final_body
                try:
                    from app.core.email_inbox_rotation import InboxRotationManager
                    rotator = InboxRotationManager()
                    
                    if rotator.can_send():
                        sender = rotator.get_available_sender()
                        if sender:
                            yag = rotator.get_yag(sender)
                            yag.send(to=email_data["to"], subject=email_data["subject"], contents=email_data["body"])
                            rotator.record_send(sender, email_data["to"])
                            
                            from app.core.email_rate_limiter import EmailRateLimiter
                            await asyncio.to_thread(EmailRateLimiter.wait_between_sends)
                            
                            logger.info(
                                f"[SEQUENCE] Day {step['day']} email sent to {email_data['to']} via {sender['_label']} "
                                f"({lead_dict.get('business')}) — {step['name']}"
                            )
                            RevenueSequence.advance_position(lead_dict["id"], step["day"])
                            processed += 1
                        else:
                            logger.warning(f"[SEQUENCE] All sending domains at daily cap. Skipping {lead_dict.get('business')}.")
                    else:
                        # Fallback to AgentMail if rotation not configured or cap reached
                        from app.skills.agentmail_skill import send_outreach
                        res = send_outreach(email_data["to"], email_data["subject"], email_data["body"])
                        if res.get("status") in ("success", "sent"):
                            logger.info(f"[SEQUENCE] Day {step['day']} email sent via AgentMail to {email_data['to']}")
                            # Rate limit apply
                            from app.core.email_rate_limiter import EmailRateLimiter
                            EmailRateLimiter.record_send(email_data["to"])
                            await asyncio.to_thread(EmailRateLimiter.wait_between_sends)
                            RevenueSequence.advance_position(lead_dict["id"], step["day"])
                            processed += 1
                        else:
                            logger.error(f"[SEQUENCE] AgentMail fallback failed: {res.get('message')}")
                except Exception as e:
                    logger.error(f"[SEQUENCE] Send failed for {lead_dict.get('business')}: {e}")
            else:
                logger.warning(
                    f"[SEQUENCE] Luxury Filter rejected Day {step['day']} email for "
                    f"{lead_dict.get('business')} after max rewrites"
                )

        elif step["type"] == "call":
            # Queue for Retell AI call (Day 14)
            logger.info(
                f"[SEQUENCE] Day {step['day']} call queued for "
                f"{lead_dict.get('business')} — {step['name']}"
            )
            RevenueSequence.advance_position(lead_dict["id"], step["day"])
            processed += 1

    logger.info(f"[SEQUENCE] Processed {processed} sequence steps.")
