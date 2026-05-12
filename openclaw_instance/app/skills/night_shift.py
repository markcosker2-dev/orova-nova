"""
OROVA Nova — Night Shift Agent
Handles incoming leads, emails, and calls while the owner is asleep.
Philippines timezone targeting US businesses.

Key insight: When it's 3am in Manila, it's 3pm in New York.
This agent ensures OROVA never misses a lead during US business hours.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PHT = ZoneInfo("Asia/Manila")
US_ET = ZoneInfo("America/New_York")

NIGHT_SHIFT_LOG = os.getenv("OROVA_NIGHT_SHIFT_LOG", "/opt/orova/data/night_shift.json")


class NightShiftAgent:
    """
    Autonomous agent that operates during Philippine nighttime
    (US business hours). Handles leads, replies to emails,
    qualifies prospects, and queues actions for owner review.
    """

    def __init__(self):
        self.log_file = NIGHT_SHIFT_LOG
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        self._load_log()

    def _load_log(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                self.shift_log = json.load(f)
        else:
            self.shift_log = {"shifts": [], "actions_taken": []}

    def _save_log(self):
        with open(self.log_file, "w") as f:
            json.dump(self.shift_log, f, indent=2)

    def is_night_shift(self) -> bool:
        """Is it currently night shift? (Owner asleep, US awake)"""
        now_pht = datetime.now(PHT)
        hour = now_pht.hour
        # Night shift: 11pm - 10am PHT (covers US 11am-10pm ET)
        return hour >= 23 or hour < 10

    def is_owner_asleep(self) -> bool:
        """Based on owner availability, is the owner likely asleep?"""
        from app.core.smart_calling import calling_hours
        return not calling_hours.is_owner_available()

    def handle_incoming_lead(self, lead_data: Dict) -> Dict:
        """
        Process a new lead that came in during night shift.
        Auto-qualifies, scores, and queues for action.
        """
        business = lead_data.get("business", "Unknown")
        phone = lead_data.get("phone", "")
        email = lead_data.get("email", "")
        vertical = lead_data.get("vertical", "")

        logger.info(f"[NIGHT SHIFT] New lead: {business} ({vertical})")

        action = {
            "timestamp": datetime.now(PHT).isoformat(),
            "type": "new_lead",
            "business": business,
            "phone": phone,
            "email": email,
            "vertical": vertical,
            "actions_taken": []
        }

        # Step 1: Auto-qualify
        score = self._quick_score(lead_data)
        action["score"] = score

        # Step 2: If high-value, prepare for immediate outreach
        if score >= 70 and email:
            action["actions_taken"].append("queued_for_email_outreach")
            logger.info(f"[NIGHT SHIFT] High-value lead queued: {business} (score: {score})")

        # Step 3: Save to database
        try:
            from app.core.database import DatabaseManager
            result = DatabaseManager.save_lead(lead_data)
            action["db_result"] = result
        except Exception as e:
            action["db_error"] = str(e)

        # Step 4: Log the action
        self.shift_log["actions_taken"].append(action)
        self._save_log()

        return action

    def handle_email_reply(self, email_data: Dict) -> Dict:
        """
        Process an email reply that came in during night shift.
        Auto-detects intent and prepares appropriate response.
        """
        sender = email_data.get("from", "")
        subject = email_data.get("subject", "")
        body = email_data.get("body", "")

        logger.info(f"[NIGHT SHIFT] Email reply from: {sender}")

        # Detect intent
        intent = self._detect_intent(body)

        action = {
            "timestamp": datetime.now(PHT).isoformat(),
            "type": "email_reply",
            "from": sender,
            "subject": subject,
            "intent": intent,
            "actions_taken": []
        }

        if intent == "interested":
            action["actions_taken"].append("queued_for_appointment_setting")
            # Get next available slot
            try:
                from app.core.smart_calling import calling_hours
                slot = calling_hours.get_next_available_slot()
                action["suggested_slot"] = slot
            except Exception:
                pass

        elif intent == "question":
            action["actions_taken"].append("queued_for_owner_review")

        elif intent == "objection":
            action["actions_taken"].append("queued_for_owner_with_objection_context")

        elif intent == "not_interested":
            action["actions_taken"].append("marked_as_not_interested")

        elif intent == "meeting_request":
            action["actions_taken"].append("queued_for_calendar_booking")

        self.shift_log["actions_taken"].append(action)
        self._save_log()

        return action

    def handle_missed_call(self, call_data: Dict) -> Dict:
        """Process a missed call during night shift."""
        phone = call_data.get("from", "")
        duration = call_data.get("duration", 0)

        action = {
            "timestamp": datetime.now(PHT).isoformat(),
            "type": "missed_call",
            "phone": phone,
            "duration": duration,
            "actions_taken": []
        }

        # If call lasted > 5 seconds (not a robocall), queue callback
        if duration > 5:
            action["actions_taken"].append("queued_for_callback")

        # If phone matches a known lead, link it
        try:
            from app.core.database import DatabaseManager
            leads = DatabaseManager.get_leads(0)
            for lead in leads:
                if lead.get("phone") == phone:
                    action["matched_lead"] = lead.get("business", "Unknown")
                    action["actions_taken"].append("linked_to_existing_lead")
                    break
        except Exception:
            pass

        self.shift_log["actions_taken"].append(action)
        self._save_log()

        return action

    def _quick_score(self, lead: Dict) -> int:
        """Fast lead scoring (0-100) for night shift decisions."""
        score = 50  # Base

        # Has phone = +10
        if lead.get("phone"):
            score += 10

        # Has email = +10
        if lead.get("email"):
            score += 10

        # Has website = +5
        if lead.get("url"):
            score += 5

        # Luxury keywords = +15
        text = json.dumps(lead).lower()
        luxury_words = ["luxury", "premium", "high-end", "custom", "bespoke", "exclusive", "elite"]
        for word in luxury_words:
            if word in text:
                score += 15
                break

        # Revenue indicators = +10
        revenue_words = ["million", "500k", "revenue", "established", "20 years", "award"]
        for word in revenue_words:
            if word in text:
                score += 10
                break

        return min(score, 100)

    def _detect_intent(self, text: str) -> str:
        """Detect email intent from text."""
        text_lower = text.lower()

        # Interested signals
        interested = ["interested", "tell me more", "how does it work", "what does it cost",
                       "let's talk", "let's chat", "schedule", "book", "meeting", "demo"]
        for w in interested:
            if w in text_lower:
                return "interested"

        # Meeting request
        meeting = ["available", "when can we", "set up a call", "hop on", "zoom", "calendar"]
        for w in meeting:
            if w in text_lower:
                return "meeting_request"

        # Objection
        objection = ["too expensive", "not right now", "already have", "happy with",
                      "budget", "can't afford", "not in the budget"]
        for w in objection:
            if w in text_lower:
                return "objection"

        # Not interested
        not_int = ["not interested", "no thanks", "stop", "remove me", "unsubscribe", "don't contact"]
        for w in not_int:
            if w in text_lower:
                return "not_interested"

        # Default: question
        return "question"

    def get_shift_summary(self) -> Dict:
        """Get summary of what happened during this shift."""
        today = datetime.now(PHT).strftime("%Y-%m-%d")
        today_actions = [
            a for a in self.shift_log.get("actions_taken", [])
            if a.get("timestamp", "").startswith(today)
        ]

        return {
            "is_night_shift": self.is_night_shift(),
            "owner_asleep": self.is_owner_asleep(),
            "actions_today": len(today_actions),
            "leads_handled": len([a for a in today_actions if a["type"] == "new_lead"]),
            "emails_processed": len([a for a in today_actions if a["type"] == "email_reply"]),
            "missed_calls": len([a for a in today_actions if a["type"] == "missed_call"]),
            "queued_for_owner": len([a for a in today_actions if "queued" in str(a.get("actions_taken", []))]),
            "current_pht": datetime.now(PHT).strftime("%Y-%m-%d %H:%M"),
            "current_et": datetime.now(US_ET).strftime("%Y-%m-%d %H:%M ET")
        }


# Global instance
night_shift = NightShiftAgent()
