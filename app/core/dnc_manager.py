# -*- coding: utf-8 -*-
"""
OROVA DNC Manager — Do Not Contact List
=========================================
Manages the Do Not Contact list. Auto-triggered on hostile replies,
"unsubscribe", "stop", "remove" keywords. Zero tolerance.

SOP: DNC response window is IMMEDIATE. No exceptions.
"""

import logging
import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# DNC trigger keywords (case-insensitive)
DNC_KEYWORDS = [
    "unsubscribe", "remove", "stop", "opt out", "opt-out",
    "take me off", "don't contact", "do not contact",
    "not interested", "leave me alone", "spam",
    "remove me", "stop emailing", "stop calling",
    "take me off your list", "no thanks",
]


class DNCManager:
    """Manages the Do Not Contact list with 90-day cooldown enforcement."""

    @staticmethod
    def init_table():
        """Create the DNC table if it doesn't exist."""
        try:
            from app.core.database import DatabaseManager
            DatabaseManager.query("""
                CREATE TABLE IF NOT EXISTS dnc (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT,
                    phone TEXT,
                    reason TEXT,
                    source TEXT DEFAULT 'auto',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("[DNC] Table initialized")
        except Exception as e:
            logger.error(f"[DNC] Table init failed: {e}")

    @staticmethod
    def add(email: str = None, phone: str = None, reason: str = "Unsubscribe request"):
        """
        Add an email or phone to the DNC list.
        Also updates lead status to 'DNC' in the leads table.
        """
        if not email and not phone:
            return

        try:
            from app.core.database import DatabaseManager

            # Check for duplicates
            if email:
                existing = DatabaseManager.query(
                    "SELECT id FROM dnc WHERE LOWER(email) = LOWER(?) LIMIT 1",
                    (email,), fetchone=True
                )
                if existing:
                    logger.info(f"[DNC] {email} already on DNC list")
                    return

            if phone:
                existing = DatabaseManager.query(
                    "SELECT id FROM dnc WHERE phone = ? LIMIT 1",
                    (phone,), fetchone=True
                )
                if existing:
                    logger.info(f"[DNC] {phone} already on DNC list")
                    return

            # Add to DNC
            DatabaseManager.query(
                "INSERT INTO dnc (email, phone, reason) VALUES (?, ?, ?)",
                (email, phone, reason)
            )

            # Update lead status
            if email:
                DatabaseManager.query(
                    "UPDATE leads SET status = 'DNC' WHERE LOWER(email) = LOWER(?)",
                    (email,)
                )
            if phone:
                DatabaseManager.query(
                    "UPDATE leads SET status = 'DNC' WHERE phone = ?",
                    (phone,)
                )

            logger.info(f"[DNC] Added: email={email}, phone={phone}, reason={reason}")

        except Exception as e:
            logger.error(f"[DNC] Failed to add: {e}")

    @staticmethod
    def is_dnc(email: str = None, phone: str = None) -> bool:
        """Check if an email or phone is on the DNC list."""
        try:
            from app.core.database import DatabaseManager

            if email:
                result = DatabaseManager.query(
                    "SELECT id FROM dnc WHERE LOWER(email) = LOWER(?) LIMIT 1",
                    (email,), fetchone=True
                )
                if result:
                    return True

            if phone:
                result = DatabaseManager.query(
                    "SELECT id FROM dnc WHERE phone = ? LIMIT 1",
                    (phone,), fetchone=True
                )
                if result:
                    return True

            return False
        except Exception:
            return False

    @staticmethod
    def check_90_day_cooldown(email: str = None, phone: str = None) -> bool:
        """
        Check if a lead has been contacted within the last 90 days.
        Returns True if the lead is within cooldown (should NOT be contacted).
        """
        try:
            from app.core.database import DatabaseManager

            if email:
                result = DatabaseManager.query(
                    """SELECT MAX(sent_at) as last_sent FROM email_tracking et
                       JOIN leads l ON et.lead_id = l.id
                       WHERE LOWER(l.email) = LOWER(?)""",
                    (email,), fetchone=True
                )
                if result and result["last_sent"]:
                    last_sent = datetime.datetime.fromisoformat(str(result["last_sent"]))
                    days_since = (datetime.datetime.now() - last_sent).days
                    if days_since < 90:
                        logger.info(f"[DNC] {email} within 90-day cooldown ({days_since} days)")
                        return True

            return False
        except Exception:
            return False

    @staticmethod
    def check_reply_for_dnc(sender: str, reply_text: str) -> bool:
        """
        Check if a reply contains DNC keywords.
        If yes, automatically adds to DNC list.
        Returns True if DNC was triggered.
        """
        lower_text = reply_text.lower()
        for keyword in DNC_KEYWORDS:
            if keyword in lower_text:
                logger.info(f"[DNC] Keyword '{keyword}' detected from {sender}")
                DNCManager.add(email=sender, reason=f"Reply contained '{keyword}'")
                return True
        return False

    @staticmethod
    def get_dnc_list(limit: int = 100) -> list:
        """Get the full DNC list."""
        try:
            from app.core.database import DatabaseManager
            rows = DatabaseManager.query(
                "SELECT * FROM dnc ORDER BY created_at DESC LIMIT ?",
                (limit,), fetchall=True
            )
            return [dict(r) for r in rows] if rows else []
        except Exception:
            return []

    @staticmethod
    def get_count() -> int:
        """Get the total number of DNC entries."""
        try:
            from app.core.database import DatabaseManager
            result = DatabaseManager.query(
                "SELECT COUNT(*) as count FROM dnc", fetchone=True
            )
            return result["count"] if result else 0
        except Exception:
            return 0
