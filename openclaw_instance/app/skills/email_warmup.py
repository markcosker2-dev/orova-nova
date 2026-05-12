"""
OROVA Nova — Email Warm-up System
Gradually increases daily sending volume to build domain reputation.
Without warm-up, 90% of cold emails land in spam.

Free solution: no paid services needed. Uses your existing SMTP.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

WARMUP_FILE = os.getenv("OROVA_WARMUP_FILE", "/opt/orova/data/email_warmup.json")


class EmailWarmup:
    """
    Manages the warm-up schedule for a new email domain.
    
    Warm-up phases:
    - Week 1: 5 emails/day (reply to warm-up pool)
    - Week 2: 10 emails/day
    - Week 3: 20 emails/day
    - Week 4: 40 emails/day
    - Week 5+: 50-100 emails/day (full volume)
    
    Tracks: sent, opened, replied, bounced, spam complaints
    """

    # Warm-up schedule: (day, max_daily_sends)
    SCHEDULE = [
        (1, 5), (3, 8), (5, 10), (7, 15),
        (9, 20), (11, 25), (14, 30),
        (16, 35), (18, 40), (21, 50),
        (24, 60), (28, 75), (30, 100)
    ]

    def __init__(self):
        self.file = WARMUP_FILE
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            with open(self.file, "r") as f:
                self.data = json.load(f)
        else:
            self.data = {
                "domains": {},
                "warmup_pool": []
            }
            self._save()

    def _save(self):
        with open(self.file, "w") as f:
            json.dump(self.data, f, indent=2)

    def register_domain(self, domain: str, email: str):
        """Register a new domain for warm-up."""
        if domain not in self.data["domains"]:
            self.data["domains"][domain] = {
                "email": email,
                "start_date": datetime.utcnow().isoformat(),
                "day": 1,
                "total_sent": 0,
                "sent_today": 0,
                "last_sent_date": None,
                "stats": {
                    "total_sent": 0,
                    "total_opened": 0,
                    "total_replied": 0,
                    "total_bounced": 0,
                    "total_spam": 0
                },
                "status": "warming"
            }
            self._save()
            logger.info(f"[WARMUP] Registered {domain} for warm-up")
        return self.data["domains"][domain]

    def get_daily_limit(self, domain: str) -> int:
        """Get today's max send volume for a domain."""
        if domain not in self.data["domains"]:
            return 5

        d = self.data["domains"][domain]
        day = d["day"]

        # Find current phase
        limit = 5
        for schedule_day, schedule_limit in self.SCHEDULE:
            if day >= schedule_day:
                limit = schedule_limit

        return limit

    def can_send(self, domain: str) -> bool:
        """Check if we can send more emails today."""
        if domain not in self.data["domains"]:
            return False

        d = self.data["domains"][domain]

        # Check if day has changed
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if d["last_sent_date"] != today:
            d["sent_today"] = 0
            d["day"] = d.get("day", 1) + 1
            d["last_sent_date"] = today

        limit = self.get_daily_limit(domain)
        can = d["sent_today"] < limit

        if not can:
            logger.info(f"[WARMUP] {domain}: daily limit reached ({d['sent_today']}/{limit})")

        return can

    def record_sent(self, domain: str):
        """Record that an email was sent."""
        if domain not in self.data["domains"]:
            return

        d = self.data["domains"][domain]
        d["sent_today"] += 1
        d["total_sent"] += 1
        d["stats"]["total_sent"] += 1
        self._save()

    def record_opened(self, domain: str):
        if domain in self.data["domains"]:
            self.data["domains"][domain]["stats"]["total_opened"] += 1
            self._save()

    def record_replied(self, domain: str):
        if domain in self.data["domains"]:
            self.data["domains"][domain]["stats"]["total_replied"] += 1
            self._save()

    def record_bounced(self, domain: str):
        if domain in self.data["domains"]:
            self.data["domains"][domain]["stats"]["total_bounced"] += 1
            # Slow down if bouncing
            d = self.data["domains"][domain]
            bounce_rate = d["stats"]["total_bounced"] / max(d["stats"]["total_sent"], 1)
            if bounce_rate > 0.05:
                d["status"] = "paused"
                logger.warning(f"[WARMUP] {domain}: paused — bounce rate {bounce_rate:.1%}")
            self._save()

    def record_spam(self, domain: str):
        if domain in self.data["domains"]:
            self.data["domains"][domain]["stats"]["total_spam"] += 1
            # Critical: pause immediately on spam complaint
            self.data["domains"][domain]["status"] = "paused"
            logger.critical(f"[WARMUP] {domain}: PAUSED — spam complaint received")
            self._save()

    def get_health(self, domain: str) -> Dict:
        """Get domain health metrics."""
        if domain not in self.data["domains"]:
            return {"status": "not_registered"}

        d = self.data["domains"][domain]
        stats = d["stats"]
        total = max(stats["total_sent"], 1)

        return {
            "domain": domain,
            "status": d["status"],
            "day": d["day"],
            "daily_limit": self.get_daily_limit(domain),
            "sent_today": d["sent_today"],
            "total_sent": stats["total_sent"],
            "open_rate": round(stats["total_opened"] / total * 100, 1),
            "reply_rate": round(stats["total_replied"] / total * 100, 1),
            "bounce_rate": round(stats["total_bounced"] / total * 100, 1),
            "spam_rate": round(stats["total_spam"] / total * 100, 1),
            "health_score": self._calculate_health(d)
        }

    def _calculate_health(self, domain_data: Dict) -> int:
        """Calculate 0-100 health score."""
        stats = domain_data["stats"]
        total = max(stats["total_sent"], 1)

        score = 100

        # Penalize bounces
        bounce_rate = stats["total_bounced"] / total
        if bounce_rate > 0.05:
            score -= 40
        elif bounce_rate > 0.02:
            score -= 20

        # Penalize spam
        spam_rate = stats["total_spam"] / total
        if spam_rate > 0.001:
            score -= 50

        # Reward opens
        open_rate = stats["total_opened"] / total
        if open_rate > 0.3:
            score += 10

        # Reward replies
        reply_rate = stats["total_replied"] / total
        if reply_rate > 0.05:
            score += 10

        return max(0, min(100, score))

    def get_warmup_email_content(self) -> Dict:
        """
        Generate warm-up email content.
        These are friendly emails sent to build reputation.
        """
        subjects = [
            "Quick question about your services",
            "Following up on our conversation",
            "Checking in — how are things going?",
            "Wanted to share something with you",
            "Quick update from OROVA",
            "Hope you're having a great week",
            "Just reaching out to say hello",
            "Thought you might find this useful"
        ]

        bodies = [
            "Hi — just wanted to check in and see how things are going on your end. Let me know if there's anything I can help with.\n\nBest,\nNova",
            "Hey — came across something interesting today that I thought you might appreciate. Happy to share if you're interested.\n\nCheers,\nNova",
            "Hi there — hope your week is going well. Just a quick note to stay in touch. Talk soon.\n\nBest,\nNova"
        ]

        import random
        return {
            "subject": random.choice(subjects),
            "body": random.choice(bodies)
        }

    def should_send_warmup(self, domain: str) -> bool:
        """Should we send a warm-up email right now?"""
        if not self.can_send(domain):
            return False

        health = self.get_health(domain)
        if health.get("status") == "paused":
            return False

        # During warm-up phase (first 30 days), mix warm-up emails with real emails
        d = self.data["domains"].get(domain, {})
        if d.get("day", 999) <= 30:
            return True

        return False


# Global instance
warmup = EmailWarmup()
