"""
Phase 6: Email Warmup & Deliverability Monitoring
Strategic sender reputation building and ISP feedback management.
"""
import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import random

logger = logging.getLogger(__name__)

# ─────── [P6.1] EMAIL WARMUP STRATEGY ─────────
class EmailWarmupStrategy:
    """
    Industry-standard email warmup: Gradual increase in sending volume
    to build sender reputation with ISPs.
    
    Timeline: 14-21 days to full sending capacity
    Strategy: Linear growth + engagement-triggered acceleration
    """
    
    # Warmup phases: (day_range, daily_volume, engagement_requirement)
    WARMUP_PHASES = [
        # Week 1: Ultra-conservative (validation)
        {"days": (1, 2),   "daily_limit": 5,    "min_engagement": 0.0},
        {"days": (3, 4),   "daily_limit": 10,   "min_engagement": 0.0},
        {"days": (5, 7),   "daily_limit": 25,   "min_engagement": 0.0},
        
        # Week 2: Conservative (reputation building)
        {"days": (8, 10),  "daily_limit": 50,   "min_engagement": 0.1},  # 10% open rate
        {"days": (11, 14), "daily_limit": 100,  "min_engagement": 0.15}, # 15% open rate
        
        # Week 3: Moderate (acceleration)
        {"days": (15, 17), "daily_limit": 250,  "min_engagement": 0.20}, # 20% open rate
        {"days": (18, 21), "daily_limit": 500,  "min_engagement": 0.20},
        
        # Full capacity (if engagement targets met)
        {"days": (22, 999), "daily_limit": 2000, "min_engagement": 0.15},
    ]
    
    def __init__(self, sender_email: str, start_date: Optional[str] = None):
        self.sender_email = sender_email
        self.start_date = start_date or datetime.utcnow().isoformat()
        self.stats = {
            "emails_sent": 0,
            "emails_opened": 0,
            "emails_clicked": 0,
            "emails_bounced": 0,
            "emails_complained": 0,
            "current_phase": 0,
        }
    
    def get_current_phase(self) -> Dict:
        """Get current warmup phase based on start date."""
        try:
            start = datetime.fromisoformat(self.start_date)
            days_elapsed = (datetime.utcnow() - start).days + 1
        except:
            days_elapsed = 1
        
        for phase in self.WARMUP_PHASES:
            if phase["days"][0] <= days_elapsed <= phase["days"][1]:
                return {
                    **phase,
                    "day": days_elapsed,
                    "status": "active"
                }
        
        # Beyond warmup period
        return {
            "daily_limit": 2000,
            "min_engagement": 0.15,
            "status": "fully_warmed",
            "day": days_elapsed,
        }
    
    def can_send_today(self, emails_sent_today: int) -> Tuple[bool, str]:
        """Check if sender can send more emails today."""
        phase = self.get_current_phase()
        limit = phase.get("daily_limit", 2000)
        
        if emails_sent_today >= limit:
            return False, f"Daily limit reached ({limit} emails)"
        
        return True, f"{limit - emails_sent_today} emails available today"
    
    def check_engagement_requirement(self, current_engagement: float) -> bool:
        """Check if engagement rate meets phase requirement."""
        phase = self.get_current_phase()
        required = phase.get("min_engagement", 0.0)
        
        if current_engagement < required:
            logger.warning(f"[WARMUP] Engagement {current_engagement:.1%} below requirement {required:.1%}")
            return False
        
        return True
    
    def get_warmup_progress(self) -> Dict:
        """Get detailed warmup progress."""
        phase = self.get_current_phase()
        
        total_sent = self.stats["emails_sent"]
        open_rate = (self.stats["emails_opened"] / total_sent) if total_sent > 0 else 0
        bounce_rate = (self.stats["emails_bounced"] / total_sent) if total_sent > 0 else 0
        complaint_rate = (self.stats["emails_complained"] / total_sent) if total_sent > 0 else 0
        
        return {
            "sender": self.sender_email,
            "status": phase.get("status"),
            "day": phase.get("day", 0),
            "daily_limit": phase.get("daily_limit"),
            "emails_sent": total_sent,
            "open_rate": open_rate,
            "bounce_rate": bounce_rate,
            "complaint_rate": complaint_rate,
            "health": self._assess_health(bounce_rate, complaint_rate),
            "next_phase_in": self._days_to_next_phase(phase),
        }
    
    def _assess_health(self, bounce_rate: float, complaint_rate: float) -> str:
        """Assess sender reputation health."""
        if bounce_rate > 0.05 or complaint_rate > 0.01:
            return "critical"
        if bounce_rate > 0.02 or complaint_rate > 0.005:
            return "warning"
        return "healthy"
    
    def _days_to_next_phase(self, current_phase: Dict) -> int:
        """Days until next warmup phase."""
        next_day = current_phase.get("days", (999, 999))[1] + 1
        days_elapsed = (datetime.utcnow() - datetime.fromisoformat(self.start_date)).days + 1
        return max(0, next_day - days_elapsed)

# ─────── [P6.2] SENDER REPUTATION MONITORING ─────────
class SenderReputationMonitor:
    """
    Monitor sender reputation across major ISPs:
    - Gmail/Google Workspace
    - Microsoft (Outlook/Office365)
    - Yahoo
    - AOL
    - Custom domains
    """
    
    ISP_REPUTATION_THRESHOLDS = {
        "gmail": {"bounce_limit": 0.03, "complaint_limit": 0.005},
        "microsoft": {"bounce_limit": 0.025, "complaint_limit": 0.003},
        "yahoo": {"bounce_limit": 0.04, "complaint_limit": 0.008},
        "other": {"bounce_limit": 0.05, "complaint_limit": 0.01},
    }
    
    def __init__(self):
        self.reputation_scores: Dict[str, Dict] = defaultdict(lambda: {
            "bounces": 0,
            "complaints": 0,
            "total_sent": 0,
            "last_updated": datetime.utcnow().isoformat(),
        })
    
    @staticmethod
    def get_isp_from_domain(email: str) -> str:
        """Extract ISP from email domain."""
        domain = email.split("@")[1].lower() if "@" in email else "other"
        
        isp_map = {
            "gmail.com": "gmail",
            "googlemail.com": "gmail",
            "outlook.com": "microsoft",
            "hotmail.com": "microsoft",
            "live.com": "microsoft",
            "office365.com": "microsoft",
            "yahoo.com": "yahoo",
            "ymail.com": "yahoo",
            "aol.com": "yahoo",  # AOL owned by Yahoo
        }
        
        return isp_map.get(domain, "other")
    
    def record_bounce(self, recipient_email: str):
        """Record email bounce for reputation tracking."""
        isp = self.get_isp_from_domain(recipient_email)
        self.reputation_scores[isp]["bounces"] += 1
        self.reputation_scores[isp]["last_updated"] = datetime.utcnow().isoformat()
    
    def record_complaint(self, recipient_email: str):
        """Record spam complaint for reputation tracking."""
        isp = self.get_isp_from_domain(recipient_email)
        self.reputation_scores[isp]["complaints"] += 1
        self.reputation_scores[isp]["last_updated"] = datetime.utcnow().isoformat()
    
    def record_send(self, recipient_email: str):
        """Record successful send for reputation tracking."""
        isp = self.get_isp_from_domain(recipient_email)
        self.reputation_scores[isp]["total_sent"] += 1
    
    def get_isp_health(self, isp: str) -> Dict:
        """Get health status for specific ISP."""
        scores = self.reputation_scores[isp]
        total = scores["total_sent"]
        
        bounce_rate = (scores["bounces"] / total) if total > 0 else 0
        complaint_rate = (scores["complaints"] / total) if total > 0 else 0
        
        thresholds = self.ISP_REPUTATION_THRESHOLDS.get(isp, self.ISP_REPUTATION_THRESHOLDS["other"])
        
        is_healthy = (
            bounce_rate <= thresholds["bounce_limit"] and
            complaint_rate <= thresholds["complaint_limit"]
        )
        
        return {
            "isp": isp,
            "total_sent": total,
            "bounce_rate": bounce_rate,
            "complaint_rate": complaint_rate,
            "status": "healthy" if is_healthy else "at_risk",
            "bounce_threshold": thresholds["bounce_limit"],
            "complaint_threshold": thresholds["complaint_limit"],
        }
    
    def get_overall_health(self) -> Dict:
        """Get overall sender reputation health."""
        if not self.reputation_scores:
            return {"status": "no_data"}
        
        isps = ["gmail", "microsoft", "yahoo", "other"]
        health_statuses = []
        
        for isp in isps:
            isp_health = self.get_isp_health(isp)
            health_statuses.append(isp_health)
        
        overall_status = "healthy"
        if any(h["status"] == "at_risk" for h in health_statuses):
            overall_status = "at_risk"
        
        return {
            "overall_status": overall_status,
            "isp_breakdown": health_statuses,
            "timestamp": datetime.utcnow().isoformat(),
        }

# ─────── [P6.3] AUTHENTICATION SETUP (SPF, DKIM, DMARC) ─────────
class EmailAuthenticationGuide:
    """
    Guide for setting up email authentication:
    - SPF (Sender Policy Framework) - prevents spoofing
    - DKIM (DomainKeys Identified Mail) - adds digital signature
    - DMARC (Domain-based Message Authentication, Reporting and Conformance) - policy enforcement
    """
    
    @staticmethod
    def get_spf_setup_instructions(domain: str, sending_service: str = "generic") -> Dict:
        """Generate SPF record setup instructions."""
        
        spf_records = {
            "sendgrid": "sendgrid.net",
            "mailgun": "mailgun.org",
            "mailchimp": "mandrillapp.com",
            "aws_ses": "amazonses.com",
            "google_workspace": "google.com",
            "generic": "mx.example.com",
        }
        
        service_domain = spf_records.get(sending_service, spf_records["generic"])
        
        return {
            "record_type": "TXT",
            "record_name": f"@  (root domain: {domain})",
            "record_value": f'v=spf1 include:{service_domain} -all',
            "explanation": "SPF allows specified servers to send email on behalf of your domain",
            "priority": "HIGH - Setup first",
        }
    
    @staticmethod
    def get_dkim_setup_instructions(domain: str) -> Dict:
        """Generate DKIM setup instructions."""
        
        return {
            "record_type": "TXT",
            "record_name": "mail._domainkey (or provided by email service)",
            "record_value": "[Your DKIM public key - provided by email service]",
            "explanation": "DKIM adds a cryptographic signature to email headers",
            "steps": [
                "1. Request DKIM key from your email service provider",
                "2. Copy the public key value",
                "3. Create TXT record in DNS with the public key",
                "4. Verify DKIM record is propagated (DNS lookup)",
            ],
            "priority": "HIGH - Setup after SPF",
        }
    
    @staticmethod
    def get_dmarc_setup_instructions(domain: str, contact_email: str) -> Dict:
        """Generate DMARC setup instructions."""
        
        return {
            "record_type": "TXT",
            "record_name": f"_dmarc.{domain}",
            "record_value": f'v=DMARC1; p=quarantine; rua=mailto:{contact_email}; ruf=mailto:{contact_email}; pct=100',
            "explanation": "DMARC sets policy for handling failed SPF/DKIM emails and sends reports",
            "policy_options": {
                "p=none": "Monitor mode - no action, receive reports",
                "p=quarantine": "Quarantine failed emails",
                "p=reject": "Reject failed emails (use after monitoring)",
            },
            "steps": [
                "1. Start with p=none for monitoring",
                "2. Monitor DMARC reports for 1-2 weeks",
                "3. Move to p=quarantine after analysis",
                "4. Consider p=reject after full compliance",
            ],
            "priority": "MEDIUM - Setup after SPF/DKIM",
        }

# ─────── [P6.4] BOUNCE HANDLING ─────────
class BounceHandler:
    """
    Handle hard bounces (permanent) vs soft bounces (temporary).
    Hard bounces: Remove from list immediately
    Soft bounces: Retry, then mark as bad after 3+ attempts
    """
    
    BOUNCE_TYPES = {
        "hard_bounce": ["invalid_email", "user_not_found", "domain_not_found", "mailbox_disabled"],
        "soft_bounce": ["mailbox_full", "service_temporarily_unavailable", "try_again_later", "rate_limit"],
        "complaint": ["abuse", "spam_complaint", "fraud_complaint"],
    }
    
    def __init__(self, db_func):
        self.db = db_func
        self.bounce_log = defaultdict(list)
    
    async def record_bounce(self, email: str, bounce_type: str, error_code: str = None):
        """Record bounce and determine action."""
        self.bounce_log[email].append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": bounce_type,
            "error_code": error_code,
        })
        
        if bounce_type == "hard_bounce":
            await self._remove_from_list(email)
            logger.info(f"[BOUNCE] Hard bounce: {email} removed from list")
        
        elif bounce_type == "soft_bounce":
            soft_bounce_count = len([b for b in self.bounce_log[email] if b["type"] == "soft_bounce"])
            if soft_bounce_count >= 3:
                await self._mark_as_invalid(email)
                logger.warning(f"[BOUNCE] Soft bounce threshold reached ({soft_bounce_count}x): {email}")
        
        elif bounce_type == "complaint":
            await self._add_to_suppression(email, reason="complaint")
            logger.warning(f"[BOUNCE] Spam complaint: {email} added to suppression list")
    
    async def _remove_from_list(self, email: str):
        """Remove email from sending list."""
        await self.db(
            "UPDATE leads SET status = 'Invalid' WHERE email = ?",
            (email.lower(),)
        )
    
    async def _mark_as_invalid(self, email: str):
        """Mark email as invalid after repeated soft bounces."""
        await self.db(
            "UPDATE leads SET status = 'Invalid' WHERE email = ?",
            (email.lower(),)
        )
    
    async def _add_to_suppression(self, email: str, reason: str):
        """Add email to suppression list (complaint/abuse)."""
        await self.db(
            """
            INSERT OR IGNORE INTO suppression_list (email, reason, created_at)
            VALUES (?, ?, ?)
            """,
            (email.lower(), reason, datetime.utcnow().isoformat())
        )

# ─────── [P6.5] ENGAGEMENT TRACKING ─────────
class EngagementTracker:
    """
    Track email engagement metrics:
    - Open rate
    - Click rate
    - Reply rate
    - Forward rate
    - List unsubscribe rate
    """
    
    def __init__(self):
        self.engagement_metrics = defaultdict(lambda: {
            "sent": 0,
            "opened": 0,
            "clicked": 0,
            "replied": 0,
            "unsubscribed": 0,
            "bounced": 0,
        })
    
    def record_open(self, email_id: str):
        """Record email open (from pixel or header)."""
        self.engagement_metrics[email_id]["opened"] += 1
    
    def record_click(self, email_id: str):
        """Record link click."""
        self.engagement_metrics[email_id]["clicked"] += 1
    
    def record_reply(self, email_id: str):
        """Record email reply."""
        self.engagement_metrics[email_id]["replied"] += 1
    
    def get_engagement_rate(self, email_id: str) -> float:
        """Calculate engagement rate (any interaction / sent)."""
        metrics = self.engagement_metrics[email_id]
        total_sent = metrics["sent"]
        
        if total_sent == 0:
            return 0.0
        
        interactions = (
            metrics["opened"] +
            metrics["clicked"] +
            metrics["replied"]
        )
        
        return interactions / total_sent

# ─────── SINGLETON INSTANCES ─────────
warmup_strategy = EmailWarmupStrategy(sender_email="noreply@orova.ai")
reputation_monitor = SenderReputationMonitor()
bounce_handler = BounceHandler(None)  # Injected at runtime
engagement_tracker = EngagementTracker()

# Database schema for warmup/reputation tracking
WARMUP_SCHEMA = """
CREATE TABLE IF NOT EXISTS email_warmup_log (
    id INTEGER PRIMARY KEY,
    sender_email TEXT,
    recipient_email TEXT,
    sent_at TEXT,
    opened_at TEXT,
    clicked_at TEXT,
    bounced_at TEXT,
    complaint_at TEXT,
    engagement_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppression_list (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    reason TEXT,
    created_at TEXT,
    FOREIGN KEY (email) REFERENCES leads(email)
);

CREATE INDEX IF NOT EXISTS idx_warmup_sender ON email_warmup_log(sender_email);
CREATE INDEX IF NOT EXISTS idx_warmup_recipient ON email_warmup_log(recipient_email);
"""
