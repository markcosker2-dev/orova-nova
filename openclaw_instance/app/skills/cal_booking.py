"""
OROVA Nova — Cal.com Free Booking Integration
Auto-books discovery calls when prospects show interest.
Cal.com is 100% free and open-source (no limits on free tier).
"""
import os
import json
import logging
import httpx
from datetime import datetime, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
CALCOM_BASE_URL = os.getenv("CALCOM_BASE_URL", "https://api.cal.com/v2")
CALCOM_EVENT_TYPE_ID = os.getenv("CALCOM_EVENT_TYPE_ID", "")


class CalBooking:
    """
    Free booking integration using Cal.com.
    When a prospect says "let's talk," Nova instantly sends a booking link.
    """

    def __init__(self):
        self.api_key = CALCOM_API_KEY
        self.base_url = CALCOM_BASE_URL
        self.event_type_id = CALCOM_EVENT_TYPE_ID

    def is_configured(self) -> bool:
        return bool(self.api_key and self.event_type_id)

    def get_booking_link(self, prospect_name: str = "", prospect_email: str = "") -> str:
        """
        Generate a booking link for a prospect.
        If Cal.com is configured, returns a personalized link.
        Otherwise returns a placeholder.
        """
        if not self.is_configured():
            return "https://cal.com/orova/discovery-call"

        # Cal.com supports pre-filling via URL params
        link = f"https://cal.com/orova/discovery-call"
        params = []
        if prospect_name:
            params.append(f"name={prospect_name.replace(' ', '+')}")
        if prospect_email:
            params.append(f"email={prospect_email}")
        if params:
            link += "?" + "&".join(params)

        return link

    def list_bookings(self, status: str = "upcoming") -> List[Dict]:
        """List upcoming bookings."""
        if not self.is_configured():
            return []

        try:
            with httpx.Client() as client:
                resp = client.get(
                    f"{self.base_url}/bookings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"status": status, "take": 20},
                    timeout=15
                )
                if resp.status_code == 200:
                    return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"[CAL.COM] Failed to list bookings: {e}")

        return []

    def create_booking(self, start_time: str, name: str, email: str,
                       notes: str = "") -> Optional[Dict]:
        """
        Create a booking on behalf of a prospect.
        start_time: ISO format (e.g., "2026-04-05T14:00:00Z")
        """
        if not self.is_configured():
            logger.warning("[CAL.COM] Not configured — returning booking link instead")
            return {
                "status": "link_only",
                "link": self.get_booking_link(name, email)
            }

        try:
            with httpx.Client() as client:
                resp = client.post(
                    f"{self.base_url}/bookings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "eventTypeId": int(self.event_type_id),
                        "start": start_time,
                        "name": name,
                        "email": email,
                        "notes": notes,
                        "timeZone": "America/New_York",
                        "language": "en",
                        "metadata": {"source": "OROVA-Nova"}
                    },
                    timeout=15
                )

                if resp.status_code in [200, 201]:
                    booking = resp.json()
                    logger.info(f"[CAL.COM] Booking created: {booking.get('id')} for {name}")
                    return booking
                else:
                    logger.error(f"[CAL.COM] Booking failed: {resp.status_code} {resp.text}")
                    return {"status": "error", "message": resp.text}

        except Exception as e:
            logger.error(f"[CAL.COM] Booking error: {e}")
            return {"status": "error", "message": str(e)}

    def get_next_available_slots(self, days_ahead: int = 5) -> List[Dict]:
        """Get available time slots from Cal.com."""
        if not self.is_configured():
            return []

        try:
            start = datetime.utcnow().strftime("%Y-%m-%d")
            end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

            with httpx.Client() as client:
                resp = client.get(
                    f"{self.base_url}/slots",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={
                        "eventTypeId": self.event_type_id,
                        "startTime": start,
                        "endTime": end
                    },
                    timeout=15
                )

                if resp.status_code == 200:
                    return resp.json().get("data", [])

        except Exception as e:
            logger.error(f"[CAL.COM] Slots error: {e}")

        return []

    def generate_booking_response(self, prospect_name: str,
                                   prospect_email: str = "") -> str:
        """
        Generate a ready-to-send message when a prospect wants to book.
        Uses owner's availability from smart_calling.
        """
        link = self.get_booking_link(prospect_name, prospect_email)

        # Get available slots for the message
        try:
            from app.core.smart_calling import calling_hours
            slots = calling_hours.get_available_slots(days_ahead=7)
            if slots:
                slot_text = "\n".join([f"  • {s['display']}" for s in slots[:3]])
                return (
                    f"{prospect_name}—\n\n"
                    f"I'd be glad to set up a brief technical alignment.\n\n"
                    f"Available slots:\n{slot_text}\n\n"
                    f"Or book directly here: {link}\n\n"
                    f"Looking forward to it.\n"
                    f"— Nova\nExecutive Director, OROVA"
                )
        except Exception:
            pass

        return (
            f"{prospect_name}—\n\n"
            f"I'd be glad to set up a brief technical alignment. "
            f"Book a time that works for you: {link}\n\n"
            f"Looking forward to it.\n"
            f"— Nova\nExecutive Director, OROVA"
        )


# Global instance
cal_booking = CalBooking()
