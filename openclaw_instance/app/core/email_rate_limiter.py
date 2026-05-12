# -*- coding: utf-8 -*-
"""
OROVA Email Rate Limiter — Domain Protection & Warmup
======================================================
Enforces MSI rate limits to protect email domain reputation.

Week 1: 20 emails/day maximum
Week 2: 35 emails/day maximum
Week 3+: 50 emails/day maximum
Inter-send delay: 60-120 seconds (random, mimics human behavior)
"""

import logging
import datetime
import time
import random
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMIT CONFIGURATION (from MSI)
# ═══════════════════════════════════════════════════════════════════════════════

WARMUP_SCHEDULE = {
    1: 20,   # Week 1: 20 emails/day
    2: 35,   # Week 2: 35 emails/day
    3: 50,   # Week 3+: 50 emails/day (permanent cap)
}

# Inter-send delay range (seconds)
MIN_DELAY = 60
MAX_DELAY = 120


class EmailRateLimiter:
    """
    Enforces email sending rate limits per the MSI warmup schedule.
    Tracks sends per day and enforces inter-send delays.
    """

    @staticmethod
    def init_table():
        """Create the email_rate_tracking table if it doesn't exist."""
        try:
            from app.core.database import DatabaseManager
            DatabaseManager.query("""
                CREATE TABLE IF NOT EXISTS email_rate_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sent_date DATE DEFAULT (date('now')),
                    email_to TEXT,
                    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Track when the system first started sending (for warmup week calculation)
            DatabaseManager.query("""
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Set first_email_date if not already set
            existing = DatabaseManager.query(
                "SELECT value FROM system_config WHERE key = 'first_email_date'",
                fetchone=True
            )
            if not existing:
                DatabaseManager.query(
                    "INSERT OR IGNORE INTO system_config (key, value) VALUES (?, ?)",
                    ("first_email_date", datetime.datetime.now().strftime("%Y-%m-%d"))
                )

            logger.info("[RATE LIMITER] Tables initialized")
        except Exception as e:
            logger.error(f"[RATE LIMITER] Table init failed: {e}")

    @staticmethod
    def get_warmup_week() -> int:
        """
        Calculate the current warmup week based on when the first email was sent.
        Returns 1, 2, or 3+ (capped at 3).
        """
        try:
            from app.core.database import DatabaseManager
            result = DatabaseManager.query(
                "SELECT value FROM system_config WHERE key = 'first_email_date'",
                fetchone=True
            )
            if result:
                first_date = datetime.datetime.strptime(result["value"], "%Y-%m-%d")
                days_elapsed = (datetime.datetime.now() - first_date).days
                week = (days_elapsed // 7) + 1
                return min(week, 3)  # Cap at week 3
        except Exception:
            pass
        return 1  # Default to most restrictive

    @staticmethod
    def get_daily_limit() -> int:
        """Get the email limit for today based on warmup week."""
        week = EmailRateLimiter.get_warmup_week()
        return WARMUP_SCHEDULE.get(week, WARMUP_SCHEDULE[3])

    @staticmethod
    def get_sends_today() -> int:
        """Count how many emails have been sent today."""
        try:
            from app.core.database import DatabaseManager
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            result = DatabaseManager.query(
                "SELECT COUNT(*) as count FROM email_rate_tracking WHERE sent_date = ?",
                (today,), fetchone=True
            )
            return result["count"] if result else 0
        except Exception:
            return 0

    @staticmethod
    def get_remaining_today() -> int:
        """Get how many emails can still be sent today."""
        limit = EmailRateLimiter.get_daily_limit()
        sent = EmailRateLimiter.get_sends_today()
        return max(0, limit - sent)

    @staticmethod
    def can_send() -> bool:
        """Check if we are allowed to send another email right now."""
        remaining = EmailRateLimiter.get_remaining_today()
        if remaining <= 0:
            logger.info(
                f"[RATE LIMITER] Daily cap reached. "
                f"Sent: {EmailRateLimiter.get_sends_today()}, "
                f"Limit: {EmailRateLimiter.get_daily_limit()} "
                f"(Week {EmailRateLimiter.get_warmup_week()})"
            )
            return False
        return True

    @staticmethod
    def record_send(email_to: str):
        """Record an email send for rate tracking."""
        try:
            from app.core.database import DatabaseManager
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            DatabaseManager.query(
                "INSERT INTO email_rate_tracking (sent_date, email_to) VALUES (?, ?)",
                (today, email_to)
            )
            remaining = EmailRateLimiter.get_remaining_today()
            logger.info(
                f"[RATE LIMITER] Email recorded to {email_to}. "
                f"Remaining today: {remaining}"
            )
        except Exception as e:
            logger.error(f"[RATE LIMITER] Failed to record send: {e}")

    @staticmethod
    def get_inter_send_delay() -> float:
        """
        Get a random delay between emails (60-120 seconds).
        Mimics human sending behavior to avoid spam detection.
        """
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        logger.info(f"[RATE LIMITER] Inter-send delay: {delay:.0f}s")
        return delay

    @staticmethod
    def wait_between_sends():
        """
        Block execution for the inter-send delay.
        Call this between consecutive email sends.
        """
        delay = EmailRateLimiter.get_inter_send_delay()
        time.sleep(delay)

    @staticmethod
    def get_status() -> dict:
        """Get rate limiter status for dashboard/reporting."""
        week = EmailRateLimiter.get_warmup_week()
        limit = EmailRateLimiter.get_daily_limit()
        sent = EmailRateLimiter.get_sends_today()
        remaining = max(0, limit - sent)

        return {
            "warmup_week": week,
            "daily_limit": limit,
            "sent_today": sent,
            "remaining_today": remaining,
            "can_send": remaining > 0,
            "inter_send_delay": f"{MIN_DELAY}-{MAX_DELAY}s",
        }
