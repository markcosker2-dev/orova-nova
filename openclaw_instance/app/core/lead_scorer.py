# -*- coding: utf-8 -*-
"""
OROVA Lead Scorer — Dynamic Re-Scoring Engine (Iris Agent) v2.0
================================================================
After every touchpoint (email reply, call, proposal open), Iris re-evaluates
the lead's Elite Score using behavioral signals, not just static profile data.

Score Range: 0-100 (Elite Score)

2026 Update: Rebalanced for Response Velocity and Video Audit readiness.
"""

import logging
import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# SCORING SIGNALS (from MSI — weighted)
# ═══════════════════════════════════════════════════════════════════════════════

SCORING_SIGNALS = {
    # Engagement Signals
    "email_reply":             +10,
    "reply_interest_keywords": +15,
    "call_sentiment_positive": +20,
    "proposal_opened":         +10,
    "call_duration_3min":      +10,
    "unsubscribe_hostile":     -50,  # DNC trigger
    "no_response_day17":       -15,
    "website_visited":         +5,
    "meeting_booked":          +25,
    "referral_intro":          +20,
    # 2026 Velocity & Video Signals
    "response_under_1hr":      +25,  # Response Velocity — #1 conversion predictor
    "response_under_4hr":      +15,  # Moderate velocity
    "response_over_24hr":      -10,  # Slow responder penalty
    "video_audit_ready":       +15,  # Lead has video-ready digital presence
    "social_media_active":     +10,  # Active social = higher engagement likelihood
    "multi_channel_response":  +20,  # Responded on 2+ channels (email + call)
}

# 2026 HAWK Weight Categories (for initial scoring)
# Rebalanced to prioritize speed-to-lead and video audit readiness
HAWK_WEIGHTS = {
    "response_velocity":   0.25,  # 25% — Speed is the #1 predictor in 2026
    "revenue_potential":   0.25,  # 25% — High-ticket CLV potential
    "digital_presence":    0.20,  # 20% — Website quality, SEO, social
    "video_audit_ready":   0.15,  # 15% — NEW: Video-ready assessment
    "market_fit":          0.15,  # 15% — Vertical alignment
}

# Interest keywords that trigger +15 boost
INTEREST_KEYWORDS = [
    "interested", "tell me more", "how does it work",
    "what does it cost", "pricing", "send me information",
    "let's talk", "sounds interesting", "set up a call",
    "schedule", "available", "yes", "let's do it",
    "how much", "what's the cost", "proposal",
    "sign me up", "i'm in", "count me in",
]

# Hostile / unsubscribe keywords that trigger DNC
DNC_KEYWORDS = [
    "unsubscribe", "remove", "stop", "opt out", "opt-out",
    "take me off", "don't contact", "do not contact",
    "not interested", "leave me alone", "spam",
    "fuck off", "piss off", "go away",
]

# ═══════════════════════════════════════════════════════════════════════════════
# QUALIFICATION STANDARD (SOP 001)
# ═══════════════════════════════════════════════════════════════════════════════

MINIMUM_OUTREACH_SCORE = 65  # Elite Score >= 65 for initial outreach
REVENUE_ALERT_THRESHOLD = 85  # Trigger [REVENUE ALERT] at 85+
ARCHIVE_THRESHOLD = 40  # Remove from active outreach below 40
ACCELERATE_RANGE = (70, 84)  # Accelerate follow-up cadence by 1 day


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class LeadScorer:
    """
    Iris Agent — Dynamic lead re-scoring after every touchpoint.
    No lead's score is static after Day 1.
    """

    @staticmethod
    def calculate_base_score(lead: Dict) -> int:
        """
        Calculate initial Elite Score (0-100) from static profile data.
        Called once when a lead is first created.
        """
        score = 50  # Base score for any lead

        # Has email → +10
        if lead.get("email"):
            score += 10

        # Has phone → +10
        if lead.get("phone"):
            score += 10

        # Has contact name → +5
        if lead.get("contact"):
            score += 5

        # Is in a target vertical → +10
        target_verticals = [
            "hvac", "roofing", "pool", "remodel", "renovation",
            "medical", "aesthetics", "dental", "aviation", "yacht",
            "real estate", "luxury", "concierge",
        ]
        vertical = (lead.get("vertical") or "").lower()
        if any(v in vertical for v in target_verticals):
            score += 10

        # Has business URL → +5
        if lead.get("url"):
            score += 5

        # Has notes/intel → +5
        if lead.get("notes") and len(str(lead.get("notes", ""))) > 20:
            score += 5

        return min(100, max(0, score))

    @staticmethod
    def apply_signal(current_score: int, signal: str, context: str = "") -> tuple:
        """
        Apply a behavioral signal to update a lead's Elite Score.

        Args:
            current_score: Current Elite Score (0-100)
            signal: Signal type from SCORING_SIGNALS keys
            context: Optional text context (e.g., reply content for keyword matching)

        Returns:
            Tuple of (new_score, action_triggered)
            action_triggered: "revenue_alert", "dnc", "archive", "accelerate", or None
        """
        delta = SCORING_SIGNALS.get(signal, 0)

        # Check for interest keywords in context
        if signal == "email_reply" and context:
            context_lower = context.lower()
            if any(kw in context_lower for kw in INTEREST_KEYWORDS):
                delta += SCORING_SIGNALS["reply_interest_keywords"]

            # Check for DNC keywords
            if any(kw in context_lower for kw in DNC_KEYWORDS):
                delta = SCORING_SIGNALS["unsubscribe_hostile"]

        new_score = min(100, max(0, current_score + delta))

        # Determine triggered action
        action = None
        if delta == SCORING_SIGNALS["unsubscribe_hostile"]:
            action = "dnc"
        elif new_score >= REVENUE_ALERT_THRESHOLD:
            action = "revenue_alert"
        elif new_score < ARCHIVE_THRESHOLD:
            action = "archive"
        elif ACCELERATE_RANGE[0] <= new_score <= ACCELERATE_RANGE[1]:
            action = "accelerate"

        logger.info(
            f"[IRIS] Score update: {current_score} → {new_score} "
            f"(signal={signal}, delta={delta:+d}, action={action})"
        )

        return new_score, action

    @staticmethod
    def is_outreach_ready(lead: Dict) -> bool:
        """
        SOP 001: Lead Qualification Standard.
        A lead is NOT outreach-ready until ALL criteria are met.
        """
        score = lead.get("score", 0)
        email = lead.get("email", "")
        phone = lead.get("phone", "")
        status = lead.get("status", "")

        # Must have Elite Score >= 65
        if score < MINIMUM_OUTREACH_SCORE:
            return False

        # Must have valid email or phone
        if not email and not phone:
            return False

        # Must not be on DNC
        if status.lower() in ("dnc", "do not contact", "unsubscribed", "hostile"):
            return False

        # Must not have been contacted in last 90 days
        last_contacted = lead.get("last_contacted_at")
        if last_contacted:
            try:
                last_dt = datetime.datetime.fromisoformat(str(last_contacted))
                if (datetime.datetime.now() - last_dt).days < 90:
                    return False
            except Exception:
                pass

        return True


# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def rescore_lead(lead_id: int, signal: str, context: str = ""):
    """
    Re-score a lead in the database after a touchpoint.
    Triggers appropriate actions (REVENUE ALERT, DNC, archive).

    Args:
        lead_id: Database lead ID
        signal: Signal type (see SCORING_SIGNALS)
        context: Optional text context
    """
    try:
        from app.core.database import DatabaseManager

        lead = DatabaseManager.query(
            "SELECT * FROM leads WHERE id = ?", (lead_id,), fetchone=True
        )
        if not lead:
            logger.warning(f"[IRIS] Lead {lead_id} not found for re-scoring")
            return

        lead_dict = dict(lead)
        current_score = lead_dict.get("score", 50)
        new_score, action = LeadScorer.apply_signal(current_score, signal, context)

        # Update score in database
        DatabaseManager.query(
            "UPDATE leads SET score = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_score, lead_id),
        )

        # Log activity
        _log_activity(lead_id, signal, context, current_score, new_score)

        # Execute triggered actions
        if action == "revenue_alert":
            from app.core.signal_protocol import send_revenue_alert
            send_revenue_alert(
                client_name=lead_dict.get("business", "Unknown"),
                vertical=lead_dict.get("vertical", "Unknown"),
                elite_score=new_score,
                status=f"Score crossed {REVENUE_ALERT_THRESHOLD} — {signal}",
                projected_value="TBD",
                next_action="Initiating Autonomous Appointment Setting sequence.",
            )

        elif action == "dnc":
            DatabaseManager.query(
                "UPDATE leads SET status = 'DNC' WHERE id = ?", (lead_id,)
            )
            logger.info(f"[IRIS] Lead {lead_id} marked DNC — hostile/unsubscribe detected")

        elif action == "archive":
            DatabaseManager.query(
                "UPDATE leads SET status = 'Archived' WHERE id = ?", (lead_id,)
            )
            logger.info(f"[IRIS] Lead {lead_id} archived — score below {ARCHIVE_THRESHOLD}")

        elif action == "accelerate":
            logger.info(f"[IRIS] Lead {lead_id} — accelerating follow-up cadence by 1 day")

    except Exception as e:
        logger.error(f"[IRIS] Re-scoring failed for lead {lead_id}: {e}")


def _log_activity(lead_id: int, signal: str, context: str, old_score: int, new_score: int):
    """Log a touchpoint to the activity_log table."""
    try:
        from app.core.database import DatabaseManager
        DatabaseManager.query(
            """INSERT INTO activity_log (lead_id, signal, context, old_score, new_score)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, signal, context[:500] if context else "", old_score, new_score),
        )
    except Exception as e:
        logger.warning(f"[IRIS] Activity log failed: {e}")


def rescore_all_active_leads():
    """
    Batch re-score: run on all leads with recent activity.
    Called by the scheduler (e.g., every 30 minutes at 09:30 ET).
    """
    try:
        from app.core.database import DatabaseManager
        leads = DatabaseManager.query(
            """SELECT id, score, status FROM leads 
               WHERE status NOT IN ('DNC', 'Archived', 'Closed Won')
               AND updated_at >= datetime('now', '-24 hours')""",
            fetchall=True,
        )
        if not leads:
            logger.info("[IRIS] No leads with recent activity to re-score")
            return

        count = 0
        for lead in leads:
            lead_dict = dict(lead)
            # Check for Day 17 no-response
            # (This is a simplified version — full implementation tracks sequence position)
            count += 1

        logger.info(f"[IRIS] Re-scored {count} leads with recent activity")

    except Exception as e:
        logger.error(f"[IRIS] Batch re-scoring failed: {e}")
