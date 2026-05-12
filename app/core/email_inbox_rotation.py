# -*- coding: utf-8 -*-
"""
app/core/email_inbox_rotation.py
Multi-domain inbox rotation for email deliverability at scale.

AUDIT FIX: Sending 50 emails/day from one domain for weeks causes silent
Gmail/Microsoft sandboxing. Distributing sends across 2-3 domains maintains
each domain's reputation well below the danger threshold.

Setup: Add multiple sending accounts to .env:
  EMAIL_ACCOUNTS=[
    {"user":"nova@orova.co","pass":"xxxx","label":"orova.co"},
    {"user":"nova@orova.io","pass":"xxxx","label":"orova.io"},
    {"user":"hello@getorova.com","pass":"xxxx","label":"getorova.com"}
  ]

Each domain's daily cap = EMAIL_DAILY_CAP / number_of_domains.
Nova rotates through them round-robin, ensuring no single domain exceeds safe volume.
"""

import os
import json
import logging
import random
from typing import Optional, Dict, Any, List
from datetime import date

try:
    import yagmail
except ImportError:
    yagmail = None

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)


class InboxRotationManager:
    """
    Manages multiple sending email accounts for deliverability protection.
    Falls back to single-account mode if EMAIL_ACCOUNTS is not configured.
    """

    def __init__(self):
        self._accounts = self._load_accounts()
        self._daily_cap_per_domain = self._compute_cap()

    def _load_accounts(self) -> List[Dict[str, str]]:
        """Load sending accounts from environment."""
        raw = os.getenv("EMAIL_ACCOUNTS", "")
        if raw:
            try:
                accounts = json.loads(raw)
                if isinstance(accounts, list) and accounts:
                    logger.info(
                        f"[ROTATION] Loaded {len(accounts)} sending accounts: "
                        + ", ".join(a.get("label", a.get("user", "?")) for a in accounts)
                    )
                    return accounts
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"[ROTATION] EMAIL_ACCOUNTS JSON parse failed: {e}")

        # Fallback: single account from EMAIL_USER / EMAIL_PASS
        user = os.getenv("EMAIL_USER", "")
        passwd = os.getenv("EMAIL_PASS", "")
        if user and passwd:
            logger.info(f"[ROTATION] Single-domain mode: {user}")
            return [{"user": user, "pass": passwd, "label": user.split("@")[-1]}]

        logger.warning("[ROTATION] No email accounts configured")
        return []

    def _compute_cap(self) -> int:
        """Daily send cap per domain."""
        total_cap = int(os.getenv("EMAIL_DAILY_CAP", 50))
        if not self._accounts:
            return total_cap
        per_domain = max(1, total_cap // len(self._accounts))
        logger.info(
            f"[ROTATION] Daily cap: {total_cap} total / "
            f"{len(self._accounts)} domains = {per_domain}/domain"
        )
        return per_domain

    def _get_sends_today_for_domain(self, domain_label: str) -> int:
        """Count emails sent today from a specific domain using the phase 3 rate tracking."""
        today = date.today().isoformat()
        try:
            r = DatabaseManager.query(
                """SELECT COUNT(*) as count FROM email_rate_tracking
                   WHERE sent_date=? AND email_to LIKE ?""",
                (today, f"%__from_domain_{domain_label}%"), fetchone=True
            )
            return r["count"] if r else 0
        except Exception:
            return 0

    def get_available_sender(self) -> Optional[Dict[str, str]]:
        """
        Return the best available sending account for the next email.

        Selection logic:
          1. Filter to accounts below their daily cap
          2. Among those, pick the one with the fewest sends today
             (balances load evenly across domains)
          3. If all accounts are at cap: return None (hard stop)
        """
        if not self._accounts:
            return None

        available = []
        for account in self._accounts:
            label   = account.get("label", account.get("user", ""))
            sent    = self._get_sends_today_for_domain(label)
            remaining = self._daily_cap_per_domain - sent
            if remaining > 0:
                available.append({
                    **account,
                    "_sent_today": sent,
                    "_remaining": remaining,
                    "_label": label,
                })

        if not available:
            logger.warning(
                f"[ROTATION] All {len(self._accounts)} accounts at daily cap. "
                f"No emails can be sent today."
            )
            return None

        # Pick account with most remaining capacity
        available.sort(key=lambda a: -a["_remaining"])
        selected = available[0]
        logger.debug(
            f"[ROTATION] Selected sender: {selected['_label']} "
            f"({selected['_sent_today']}/{self._daily_cap_per_domain} today, "
            f"{selected['_remaining']} remaining)"
        )
        return selected

    def get_yag(self, account: Dict[str, str]):
        """Create a yagmail SMTP connection for the given account."""
        if not yagmail:
            raise ImportError("yagmail is required for SMTP operations. Please pip install yagmail.")
        user   = account.get("user", "")
        passwd = account.get("pass", "")
        if not user or not passwd:
            raise RuntimeError(
                f"Email account '{account.get('label','')}' is missing user or pass"
            )
        return yagmail.SMTP(user, passwd)

    def record_send(self, account: Dict[str, str], recipient: str):
        """Record a send against the specific domain's quota and global rate limiter."""
        label = account.get("label", account.get("user", ""))
        from app.core.email_rate_limiter import EmailRateLimiter
        # We append a hidden marker to the email_to field in rate tracking to count domain sends
        marker = f"__from_domain_{label}__"
        EmailRateLimiter.record_send(f"{recipient}{marker}")

    def can_send(self) -> bool:
        """Quick check — is any domain available?"""
        from app.core.email_rate_limiter import EmailRateLimiter
        if not EmailRateLimiter.can_send():
            return False
        return self.get_available_sender() is not None

    def daily_stats(self) -> List[Dict[str, Any]]:
        """Return send stats per domain for dashboard/Telegram."""
        stats = []
        for account in self._accounts:
            label = account.get("label", account.get("user", ""))
            sent  = self._get_sends_today_for_domain(label)
            stats.append({
                "domain":    label,
                "sent_today":sent,
                "cap":       self._daily_cap_per_domain,
                "remaining": max(0, self._daily_cap_per_domain - sent),
            })
        return stats
