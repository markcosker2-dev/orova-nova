"""
Cal.com Booking Integration - Auto Meeting Follow-up
Handles webhooks from Cal.com when a meeting is booked or rescheduled.
This enables "Closer" sub-agent to trigger follow-up sequences.
"""

import os
import logging
import json
from typing import Dict, Any
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)


async def handle_cal_booking_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process incoming Cal.com webhook (meeting booked, rescheduled, cancelled).
    
    Webhook Structure from Cal.com:
    {
        "triggerEvent": "BOOKING_CREATED|BOOKING_CANCELLED|BOOKING_RESCHEDULED",
        "createdAt": "2024-05-14T10:30:00Z",
        "data": {
            "eventTypeId": 12345,
            "eventSlug": "initial-consultation",
            "uid": "booking_uuid",
            "confirmed": true,
            "attendees": [
                {
                    "email": "prospect@company.com",
                    "name": "John Doe",
                    "timeZone": "America/New_York"
                }
            ],
            "organizer": {
                "email": "your-calendar@company.com",
                "name": "Your Name",
                "timeZone": "America/New_York"
            },
            "startTime": "2024-05-20T14:00:00Z",
            "endTime": "2024-05-20T14:30:00Z",
            "title": "Initial Consultation"
        }
    }
    
    Returns:
        {"success": bool, "action": "store_meeting|send_confirmation|trigger_followup|cancel"}
    """
    try:
        trigger_event = payload.get("triggerEvent", "")
        event_data = payload.get("data", {})
        
        attendee = event_data.get("attendees", [{}])[0]
        
        if trigger_event == "BOOKING_CREATED":
            return await _handle_booking_created(event_data, attendee)
        elif trigger_event == "BOOKING_CANCELLED":
            return await _handle_booking_cancelled(event_data, attendee)
        elif trigger_event == "BOOKING_RESCHEDULED":
            return await _handle_booking_rescheduled(event_data, attendee)
        else:
            logger.warning(f"[Cal.com] Unknown trigger event: {trigger_event}")
            return {"success": False, "error": f"Unknown event: {trigger_event}"}
    
    except Exception as e:
        logger.error(f"[Cal.com] Webhook processing error: {e}")
        return {"success": False, "error": str(e)}


async def _handle_booking_created(event_data: Dict, attendee: Dict) -> Dict[str, Any]:
    """
    When a prospect books a meeting, store it and trigger Closer's confirmation sequence.
    """
    prospect_email = attendee.get("email")
    prospect_name = attendee.get("name")
    start_time = event_data.get("startTime")
    title = event_data.get("title", "Meeting")
    
    logger.info(f"[Cal.com] Booking created: {prospect_name} <{prospect_email}> at {start_time}")
    
    # In production, this would:
    # 1. Store meeting in database (app/models/core.py::Meeting)
    # 2. Send confirmation email via "Closer"
    # 3. Schedule follow-up reminder (Nova task)
    # 4. Log in Telegram
    
    return {
        "success": True,
        "action": "store_meeting",
        "prospect_email": prospect_email,
        "prospect_name": prospect_name,
        "scheduled_time": start_time,
        "title": title,
        "next_steps": [
            "Store meeting record in database",
            "Send confirmation email",
            "Schedule pre-meeting research task",
            "Alert CEO via Telegram"
        ]
    }


async def _handle_booking_cancelled(event_data: Dict, attendee: Dict) -> Dict[str, Any]:
    """
    When a prospect cancels, mark meeting as cancelled and flag for follow-up outreach.
    """
    prospect_email = attendee.get("email")
    prospect_name = attendee.get("name")
    
    logger.info(f"[Cal.com] Booking cancelled: {prospect_name} <{prospect_email}>")
    
    # In production:
    # 1. Mark meeting as "cancelled"
    # 2. Trigger "Hawk" (Lead Hunter) to follow up with a re-engagement email
    
    return {
        "success": True,
        "action": "cancel",
        "prospect_email": prospect_email,
        "next_steps": [
            "Mark meeting as cancelled",
            "Trigger Hawk's re-engagement sequence"
        ]
    }


async def _handle_booking_rescheduled(event_data: Dict, attendee: Dict) -> Dict[str, Any]:
    """
    When a prospect reschedules, update the meeting time and send updated calendar invite.
    """
    prospect_email = attendee.get("email")
    new_start_time = event_data.get("startTime")
    
    logger.info(f"[Cal.com] Booking rescheduled: {prospect_email} → {new_start_time}")
    
    return {
        "success": True,
        "action": "reschedule",
        "prospect_email": prospect_email,
        "new_time": new_start_time,
        "next_steps": [
            "Update meeting in database",
            "Send updated calendar invite",
            "Reschedule pre-meeting research task"
        ]
    }


def generate_cal_booking_link(
    event_slug: str = "initial-consultation",
    cal_username: str = None,
    prefill_email: str = None,
    prefill_name: str = None
) -> str:
    """
    Generate a Cal.com booking link for embedding in emails or proposals.
    
    Args:
        event_slug: The Cal.com event type slug
        cal_username: Your Cal.com username (e.g., "yourname")
        prefill_email: Pre-fill prospect email
        prefill_name: Pre-fill prospect name
    
    Returns:
        Full Cal.com booking URL
    """
    if not cal_username:
        cal_username = os.getenv("CAL_USERNAME", "unknown")
    
    base = f"https://cal.com/{cal_username}/{event_slug}"
    
    params = []
    if prefill_email:
        params.append(f"email={prefill_email}")
    if prefill_name:
        params.append(f"name={prefill_name}")
    
    if params:
        base += "?" + "&".join(params)
    
    return base


def format_meeting_for_telegram(meeting_dict: Dict) -> str:
    """
    Format a meeting record for Telegram notification.
    
    Returns:
        Markdown-formatted message for CEO alert
    """
    return f"""
📅 **Meeting Booked!**

👤 {meeting_dict.get('prospect_name', 'Unknown')}
📧 {meeting_dict.get('prospect_email', 'N/A')}
🕐 {meeting_dict.get('scheduled_time', 'TBD')}
📝 {meeting_dict.get('title', 'Consultation')}

*Next Steps:*
- Pre-meeting research queued
- Confirmation sent
- Ready for meeting
"""
