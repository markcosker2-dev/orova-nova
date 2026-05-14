"""
Intelligent Call Scheduling - Timezone Detection
Prevents Nova from calling prospects at 2 AM.
Uses timezonefinder to detect timezone from company address/coords.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from timezonefinder import TimezoneFinder
import pytz

logger = logging.getLogger(__name__)

tf = TimezoneFinder()


def get_timezone_from_coords(latitude: float, longitude: float) -> Optional[str]:
    """
    Get IANA timezone string from GPS coordinates.
    
    Args:
        latitude: Company latitude
        longitude: Company longitude
    
    Returns:
        Timezone string (e.g., "America/New_York") or None
    """
    try:
        tz = tf.timezone_at(lat=latitude, lng=longitude)
        return tz
    except Exception as e:
        logger.error(f"[TZ] Error getting timezone from coords: {e}")
        return None


def get_timezone_from_state(state_abbr: str = None, country: str = "US") -> Optional[str]:
    """
    Rough timezone estimate from US state abbreviation.
    For international, use get_timezone_from_coords instead.
    
    Args:
        state_abbr: US state abbreviation (e.g., "CA", "NY")
        country: Country code (default "US")
    
    Returns:
        Typical timezone for that state
    """
    # Simple US state → timezone mapping
    us_tz_map = {
        "AK": "America/Anchorage",
        "HI": "Pacific/Honolulu",
        "PT": "America/Los_Angeles", "CA": "America/Los_Angeles", "NV": "America/Los_Angeles", "OR": "America/Los_Angeles", "WA": "America/Los_Angeles",
        "MT": "America/Denver", "CO": "America/Denver", "UT": "America/Denver", "WY": "America/Denver", "ID": "America/Denver", "NM": "America/Denver",
        "CT": "America/Chicago", "TX": "America/Chicago", "OK": "America/Chicago", "KS": "America/Chicago", "NE": "America/Chicago", "SD": "America/Chicago", "ND": "America/Chicago", "MN": "America/Chicago", "IA": "America/Chicago", "MO": "America/Chicago", "AR": "America/Chicago", "LA": "America/Chicago",
        "ET": "America/New_York", "ME": "America/New_York", "VT": "America/New_York", "NH": "America/New_York", "MA": "America/New_York", "RI": "America/New_York", "CT": "America/New_York", "NY": "America/New_York", "PA": "America/New_York", "NJ": "America/New_York", "DE": "America/New_York", "MD": "America/New_York", "VA": "America/New_York", "WV": "America/New_York", "OH": "America/New_York", "MI": "America/New_York", "IN": "America/New_York", "KY": "America/New_York", "TN": "America/New_York", "NC": "America/New_York", "SC": "America/New_York", "GA": "America/New_York", "FL": "America/New_York",
    }
    
    return us_tz_map.get(state_abbr.upper() if state_abbr else "ET", "America/New_York")


def is_business_hours(timezone_str: str, current_utc_time: datetime = None) -> Tuple[bool, str]:
    """
    Check if it's business hours (9 AM - 6 PM) in the prospect's timezone.
    
    Args:
        timezone_str: IANA timezone string (e.g., "America/New_York")
        current_utc_time: UTC time to check (default: now)
    
    Returns:
        (is_business_hours: bool, local_time_str: str)
    """
    try:
        if not current_utc_time:
            current_utc_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        local_time = current_utc_time.astimezone(tz)
        
        # Business hours: 9 AM - 6 PM, Mon-Fri
        is_weekday = local_time.weekday() < 5  # 0-4 = Mon-Fri
        is_business_hour = 9 <= local_time.hour < 18
        
        is_ok = is_weekday and is_business_hour
        local_str = local_time.strftime("%I:%M %p %Z")
        
        return is_ok, local_str
    except Exception as e:
        logger.error(f"[TZ] Error checking business hours: {e}")
        return False, "Unknown"


def next_business_hours_slot(
    timezone_str: str,
    days_ahead: int = 0,
    current_utc_time: datetime = None
) -> Tuple[datetime, str]:
    """
    Find the next business hours slot (9 AM) in the prospect's timezone.
    
    Args:
        timezone_str: IANA timezone string
        days_ahead: How many days to look ahead (0 = today, 1 = tomorrow, etc)
        current_utc_time: Reference UTC time (default: now)
    
    Returns:
        (scheduled_utc_time: datetime, local_time_str: str)
    """
    try:
        if not current_utc_time:
            current_utc_time = datetime.utcnow().replace(tzinfo=pytz.UTC)
        
        tz = pytz.timezone(timezone_str)
        local_now = current_utc_time.astimezone(tz)
        
        # Start from requested day at 9 AM local time
        target_date = local_now.date() + timedelta(days=days_ahead)
        target_local = tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9)))
        
        # If we've passed 9 AM today, move to next business day
        if days_ahead == 0 and local_now.time() >= target_local.time() and local_now.weekday() < 4:
            target_date = local_now.date() + timedelta(days=1)
            target_local = tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9)))
        
        # Skip weekends
        while target_local.weekday() >= 5:
            target_local += timedelta(days=1)
        
        # Convert back to UTC
        target_utc = target_local.astimezone(pytz.UTC)
        local_str = target_local.strftime("%A, %I:%M %p %Z")
        
        return target_utc, local_str
    except Exception as e:
        logger.error(f"[TZ] Error finding next slot: {e}")
        return None, "Unknown"


def format_for_call_script(timezone_str: str) -> str:
    """
    Generate a snippet for the Retell call script mentioning local time respect.
    
    Returns:
        Markdown-formatted string for the call context.
    """
    tz = pytz.timezone(timezone_str)
    local_now = datetime.now(tz).strftime("%I:%M %p %Z")
    
    return f"It's currently {local_now} in the prospect's timezone. Use this context to personalize the opening."
