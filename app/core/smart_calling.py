"""
OROVA Nova — Smart Calling Hours
Calls prospects during THEIR local business hours based on their location.
Also manages YOUR availability for booking discovery calls.
"""
import os
import json
import logging
from datetime import datetime, timedelta, time
from typing import Optional, Dict, List, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

AVAILABILITY_FILE = os.getenv("OROVA_AVAILABILITY_FILE", "/opt/orova/data/owner_availability.json")


# ── US Area Code to Timezone Mapping ────────────────────────

AREA_CODE_TIMEZONES = {
    # Eastern (ET)
    **{str(n): "America/New_York" for n in [
        201, 202, 203, 207, 212, 215, 216, 217, 219,
        224, 229, 231, 234, 239, 240, 248, 252, 256, 267,
        269, 270, 272, 276, 281, 301, 302, 304, 305, 313,
        315, 317, 321, 330, 334, 336, 339, 347, 351, 352,
        386, 401, 404, 407, 410, 412, 413, 419, 423, 434,
        440, 443, 445, 470, 475, 478, 484, 508, 513, 516,
        517, 518, 540, 551, 561, 567, 570, 571, 585, 586,
        603, 606, 607, 609, 610, 614, 615, 616, 617, 631,
        646, 678, 681, 689, 703, 704, 706, 716, 717, 718,
        724, 727, 732, 734, 740, 754, 757, 762, 765, 770,
        772, 774, 781, 786, 803, 804, 810, 813, 814, 828,
        843, 845, 848, 854, 856, 857, 859, 860, 862, 863,
        864, 865, 878, 901, 904, 908, 910, 912, 914, 917,
        919, 937, 941, 947, 954, 959, 973, 980, 984, 989,
    ]},
    # Central (CT)
    **{str(n): "America/Chicago" for n in [
        205, 214, 217, 218, 224, 225, 228, 251, 254, 262,
        270, 281, 309, 312, 314, 316, 318, 319, 320, 325,
        331, 337, 346, 361, 385, 405, 409, 414, 417, 430,
        432, 442, 469, 479, 501, 504, 507, 512, 515, 557,
        563, 573, 574, 580, 601, 605, 608, 612, 618, 620,
        626, 630, 636, 641, 651, 660, 662, 682, 708, 712,
        713, 715, 731, 763, 769, 773, 779, 785, 806, 815,
        816, 817, 830, 832, 847, 850, 870, 872, 903, 913,
        915, 918, 920, 931, 936, 940, 952, 956, 972, 979,
        985,
    ]},
    # Mountain (MT)
    **{str(n): "America/Denver" for n in [
        208, 303, 307, 385, 406, 435, 480, 505, 520, 602,
        623, 719, 720, 801, 928, 970,
    ]},
    # Pacific (PT)
    **{str(n): "America/Los_Angeles" for n in [
        206, 209, 213, 253, 310, 323, 360, 408, 415, 424,
        425, 442, 503, 509, 510, 530, 541, 559, 562, 619,
        626, 628, 650, 657, 661, 669, 702, 707, 714, 747,
        760, 775, 805, 818, 831, 858, 909, 916, 925, 949,
        951,
    ]},
}


class SmartCallingHours:
    """
    Determines when to call a prospect based on their timezone.
    Manages your availability for booking discovery calls.
    """

    # Default business calling hours (prospect's local time)
    PROSPECT_CALL_START = 9   # 9am
    PROSPECT_CALL_END = 17    # 5pm

    def __init__(self):
        self._load_availability()

    def _load_availability(self):
        """Load owner availability from file."""
        if os.path.exists(AVAILABILITY_FILE):
            with open(AVAILABILITY_FILE, "r") as f:
                self.availability = json.load(f)
        else:
            # Default: your preferred slots
            self.availability = {
                "timezone": "Asia/Manila",  # Philippines (+08:00)
                "preferred_slots": [
                    {"name": "Night", "start": "23:00", "end": "02:30", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]},
                    {"name": "Morning", "start": "11:00", "end": "14:30", "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}
                ],
                "blocked_dates": []  # ["2026-04-10", "2026-04-11"] for trips
            }
            self._save_availability()

    def _save_availability(self):
        os.makedirs(os.path.dirname(AVAILABILITY_FILE), exist_ok=True)
        with open(AVAILABILITY_FILE, "w") as f:
            json.dump(self.availability, f, indent=2)

    # ── Prospect Timezone Detection ──────────────────────────

    def get_prospect_timezone(self, phone: str, state: str = None, city: str = None) -> str:
        """
        Detect prospect's timezone from phone area code or location.
        Returns IANA timezone string.
        """
        # Method 1: Area code from phone
        if phone:
            digits = ''.join(filter(str.isdigit, phone))
            if len(digits) == 10:
                area = digits[:3]
            elif len(digits) == 11 and digits[0] == '1':
                area = digits[1:4]
            else:
                area = None

            if area and area in AREA_CODE_TIMEZONES:
                tz = AREA_CODE_TIMEZONES[area]
                logger.info(f"[SMART CALL] Detected timezone {tz} from area code {area}")
                return tz

        # Method 2: State mapping
        state_tz = {
            "CA": "America/Los_Angeles", "WA": "America/Los_Angeles", "OR": "America/Los_Angeles",
            "NV": "America/Los_Angeles",
            "CO": "America/Denver", "UT": "America/Denver", "MT": "America/Denver",
            "WY": "America/Denver", "NM": "America/Denver", "AZ": "America/Phoenix",
            "TX": "America/Chicago", "IL": "America/Chicago", "FL": "America/New_York",
            "NY": "America/New_York", "NJ": "America/New_York", "MA": "America/New_York",
            "PA": "America/New_York", "GA": "America/New_York", "NC": "America/New_York",
        }
        if state and state.upper() in state_tz:
            tz = state_tz[state.upper()]
            logger.info(f"[SMART CALL] Detected timezone {tz} from state {state}")
            return tz

        # Default: US Eastern
        return "America/New_York"

    def is_prospect_calling_hours(self, prospect_tz: str) -> bool:
        """Check if it's business hours in the prospect's timezone RIGHT NOW."""
        try:
            now = datetime.now(ZoneInfo(prospect_tz))
        except Exception:
            now = datetime.now()

        # No weekends
        if now.weekday() >= 5:
            return False

        # Business hours check
        return self.PROSPECT_CALL_START <= now.hour < self.PROSPECT_CALL_END

    def next_calling_window(self, prospect_tz: str) -> Optional[datetime]:
        """When is the next time we can call this prospect?"""
        try:
            now = datetime.now(ZoneInfo(prospect_tz))
        except Exception:
            now = datetime.now()

        # If within hours today and weekday, return now
        if now.weekday() < 5 and self.PROSPECT_CALL_START <= now.hour < self.PROSPECT_CALL_END:
            return now

        # Find next weekday at 9am
        candidate = now.replace(hour=self.PROSPECT_CALL_START, minute=0, second=0, microsecond=0)
        if now.hour >= self.PROSPECT_CALL_END:
            candidate += timedelta(days=1)

        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)

        return candidate

    # ── Your Availability Management ─────────────────────────

    def is_owner_available(self, check_datetime: datetime = None) -> bool:
        """Check if you're available at a given time."""
        if check_datetime is None:
            check_datetime = datetime.now(ZoneInfo(self.availability["timezone"]))

        # Check blocked dates
        date_str = check_datetime.strftime("%Y-%m-%d")
        if date_str in self.availability.get("blocked_dates", []):
            return False

        # Check preferred slots
        day_name = check_datetime.strftime("%a").lower()[:3]  # mon, tue, etc.
        current_time = check_datetime.strftime("%H:%M")

        for slot in self.availability["preferred_slots"]:
            if day_name in slot["days"]:
                if slot["start"] <= current_time <= slot["end"]:
                    return True

        return False

    def get_next_available_slot(self, from_datetime: datetime = None) -> Optional[Dict]:
        """Find the next available discovery call slot."""
        if from_datetime is None:
            from_datetime = datetime.now(ZoneInfo(self.availability["timezone"]))

        # Check up to 14 days out
        for day_offset in range(14):
            check_date = from_datetime + timedelta(days=day_offset)
            date_str = check_date.strftime("%Y-%m-%d")
            day_name = check_date.strftime("%a").lower()[:3]

            if date_str in self.availability.get("blocked_dates", []):
                continue

            for slot in self.availability["preferred_slots"]:
                if day_name in slot["days"]:
                    # Build datetime for this slot
                    start_h, start_m = map(int, slot["start"].split(":"))
                    end_h, end_m = map(int, slot["end"].split(":"))

                    slot_start = check_date.replace(hour=start_h, minute=start_m, second=0)

                    # If slot is in the future
                    if slot_start > from_datetime:
                        return {
                            "date": date_str,
                            "slot_name": slot["name"],
                            "start": slot["start"],
                            "end": slot["end"],
                            "datetime": slot_start.isoformat(),
                            "display": f"{date_str} {slot['start']}–{slot['end']} ({self.availability['timezone']})"
                        }

        return None

    def get_available_slots(self, days_ahead: int = 7) -> List[Dict]:
        """Get all available slots for the next N days."""
        slots = []
        tz = ZoneInfo(self.availability["timezone"])
        now = datetime.now(tz)

        for day_offset in range(days_ahead):
            check_date = now + timedelta(days=day_offset)
            date_str = check_date.strftime("%Y-%m-%d")
            day_name = check_date.strftime("%a").lower()[:3]

            if date_str in self.availability.get("blocked_dates", []):
                continue

            for slot in self.availability["preferred_slots"]:
                if day_name in slot["days"]:
                    slots.append({
                        "date": date_str,
                        "day": day_name,
                        "slot_name": slot["name"],
                        "start": slot["start"],
                        "end": slot["end"],
                        "display": f"{check_date.strftime('%a %b %d')} {slot['start']}–{slot['end']}"
                    })

        return slots

    # ── Block/Unblock Dates ──────────────────────────────────

    def block_dates(self, dates: List[str], reason: str = ""):
        """Block dates (trips, holidays, etc)."""
        for d in dates:
            if d not in self.availability["blocked_dates"]:
                self.availability["blocked_dates"].append(d)
        self._save_availability()
        logger.info(f"[AVAILABILITY] Blocked {len(dates)} dates: {reason}")

    def unblock_dates(self, dates: List[str]):
        """Unblock dates."""
        for d in dates:
            if d in self.availability["blocked_dates"]:
                self.availability["blocked_dates"].remove(d)
        self._save_availability()

    def update_preferences(self, timezone: str = None, slots: List[Dict] = None):
        """Update your availability preferences."""
        if timezone:
            self.availability["timezone"] = timezone
        if slots:
            self.availability["preferred_slots"] = slots
        self._save_availability()

    def get_status(self) -> Dict:
        """Get current availability status."""
        tz = ZoneInfo(self.availability["timezone"])
        now = datetime.now(tz)

        return {
            "timezone": self.availability["timezone"],
            "current_time": now.strftime("%Y-%m-%d %H:%M"),
            "owner_available_now": self.is_owner_available(now),
            "next_slot": self.get_next_available_slot(now),
            "blocked_dates": self.availability.get("blocked_dates", []),
            "preferred_slots": self.availability["preferred_slots"]
        }


# Global instance
calling_hours = SmartCallingHours()
