"""
Phase 5: Email Compliance - CAN-SPAM, GDPR, CASL, PECR enforcement
"""
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ─────── [P5.1] CAN-SPAM COMPLIANCE ─────────
class CANSPAMCompliance:
    """
    Ensures all emails meet CAN-SPAM Act requirements (15 USC § 7701):
    - Accurate subject line
    - Legitimate sender identity
    - Opt-out mechanism (unsubscribe link)
    - Opt-out honored within 10 business days
    - Physical address included
    - No deceptive headers
    """
    
    REQUIRED_HEADERS = {
        "From": "Must be accurate sender",
        "To": "Must be recipient",
        "Subject": "Must not be deceptive",
        "List-Unsubscribe": "Unsubscribe link (required)",
    }
    
    @staticmethod
    def validate_email(email_content: Dict) -> Dict[str, any]:
        """Validate email against CAN-SPAM requirements."""
        issues = []
        warnings = []
        
        # Check subject line
        subject = email_content.get("subject", "")
        if not subject or len(subject) < 5:
            issues.append("Subject line missing or too short")
        if any(word in subject.lower() for word in ["free", "act now", "click here"]):
            warnings.append("Subject line contains common spam trigger words")
        
        # Check sender identity
        from_addr = email_content.get("from", "")
        if not from_addr or "@" not in from_addr:
            issues.append("From address missing or invalid")
        
        # Check unsubscribe mechanism
        body = email_content.get("body", "")
        headers = email_content.get("headers", {})
        
        unsubscribe_present = (
            "unsubscribe" in body.lower() or
            "opt-out" in body.lower() or
            "list-unsubscribe" in headers
        )
        if not unsubscribe_present:
            issues.append("No unsubscribe/opt-out mechanism found")
        
        # Check physical address
        if not any(part in body for part in ["address", "located at", "headquarters"]):
            warnings.append("No physical address found in email body")
        
        # Check for deceptive headers
        if "bcc" in email_content.get("headers", {}).get("Bcc", "").lower():
            issues.append("BCC field populated - violates CAN-SPAM")
        
        return {
            "compliant": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "timestamp": datetime.utcnow().isoformat(),
        }

# ─────── [P5.2] GDPR COMPLIANCE ─────────
class GDPRCompliance:
    """
    GDPR compliance for EU users (EU General Data Protection Regulation):
    - Legal basis (Legitimate Interest or Explicit Consent)
    - Privacy notice provided
    - Right to access, rectify, erasure, portability
    - Data processing agreements
    - Data minimization
    """
    
    @staticmethod
    def check_legal_basis(user: Dict) -> Dict[str, any]:
        """Verify legal basis for processing user data."""
        basis = user.get("legal_basis", "consent")
        
        if basis == "consent":
            consent_date = user.get("consent_date")
            if not consent_date:
                return {"valid": False, "reason": "Consent date not recorded"}
            try:
                consent_dt = datetime.fromisoformat(consent_date)
                if datetime.utcnow() - consent_dt > timedelta(days=365 * 3):  # 3 year consent
                    return {"valid": False, "reason": "Consent expired"}
            except (ValueError, TypeError) as e:
                logger.warning(f"[Compliance] Invalid consent_date: {consent_date!r} — {e}")
                return {"valid": False, "reason": "Invalid consent date format"}
        
        return {"valid": True, "legal_basis": basis}
    
    @staticmethod
    def generate_data_export(user_id: int, from_db_func) -> Dict[str, any]:
        """Generate GDPR Right to Portability export."""
        from_db_func(f"SELECT * FROM leads WHERE client_id = ?", (user_id,), fetchall=True)
        # This is a placeholder - actual implementation calls database
        return {
            "user_id": user_id,
            "export_date": datetime.utcnow().isoformat(),
            "data_categories": ["leads", "metrics", "call_logs", "emails"],
            "format": "json",
        }
    
    @staticmethod
    def generate_deletion_report(user_id: int, from_db_func) -> Dict[str, any]:
        """Generate GDPR Right to Erasure (Right to Be Forgotten) report."""
        return {
            "user_id": user_id,
            "deletion_date": datetime.utcnow().isoformat(),
            "categories_deleted": ["leads", "metrics", "call_logs", "emails", "personal_data"],
            "retention_exceptions": ["minimal for legal compliance"],
        }

# ─────── [P5.3] CASL COMPLIANCE ─────────
class CASLCompliance:
    """
    CASL (Canada's Anti-Spam Legislation) compliance:
    - Express consent required for commercial emails
    - Sender ID required
    - Unsubscribe mechanism required (within 10 business days)
    - No misleading headers
    """
    
    @staticmethod
    def requires_consent(recipient_country: Optional[str]) -> bool:
        """Check if recipient is in Canada (requires explicit consent)."""
        return recipient_country and recipient_country.upper() == "CA"
    
    @staticmethod
    def validate_consent(recipient: Dict) -> bool:
        """Verify express consent for Canadian recipients."""
        if not CASLCompliance.requires_consent(recipient.get("country")):
            return True
        
        consent = recipient.get("consent_casl")
        consent_date = recipient.get("consent_date")
        
        if not consent or not consent_date:
            logger.warning(f"[CASL] No consent for {recipient.get('email', 'unknown')}")
            return False
        
        return True

# ─────── [P5.4] PECR COMPLIANCE ─────────
class PECRCompliance:
    """
    PECR (Privacy and Electronic Communications Regulations - UK):
    - Opt-in consent for electronic marketing
    - Corporate preference services honored
    - Privacy notice required
    """
    
    @staticmethod
    def check_uk_compliance(recipient: Dict) -> Dict[str, any]:
        """Verify PECR compliance for UK recipients."""
        country = recipient.get("country", "").upper()
        
        if country != "GB":
            return {"applicable": False}
        
        opt_in_consent = recipient.get("pecr_opt_in")
        if not opt_in_consent:
            return {
                "applicable": True,
                "compliant": False,
                "reason": "PECR opt-in consent required for UK recipients"
            }
        
        # Check corporate preference service
        tps_registered = recipient.get("tps_registered", False)
        if tps_registered:
            return {
                "applicable": True,
                "compliant": False,
                "reason": "Recipient registered with TPS - cannot contact"
            }
        
        return {"applicable": True, "compliant": True}

# ─────── [P5.5] OPT-OUT ENFORCEMENT ─────────
class OptOutManager:
    """Manage opt-out lists and honor unsubscribe requests within legal timeframes."""
    
    def __init__(self, db_func):
        self.db = db_func
        self.opt_out_ttl_days = 10  # CAN-SPAM requirement
    
    async def add_to_optout(self, email: str, reason: str = "user_request"):
        """Add email to opt-out list."""
        await self.db(
            """
            INSERT INTO opt_out_list (email, reason, opt_out_date)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET opt_out_date = ?
            """,
            (email, reason, datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
        )
        logger.info(f"[OPT-OUT] Added {email} to opt-out list: {reason}")
    
    async def is_opted_out(self, email: str) -> bool:
        """Check if email is opted out."""
        result = await self.db(
            "SELECT 1 FROM opt_out_list WHERE email = ? LIMIT 1",
            (email.lower(),),
            fetchone=True
        )
        return result is not None
    
    async def honor_optout_deadline(self, email: str, reason: str) -> Dict[str, any]:
        """
        CAN-SPAM requires honoring opt-out within 10 business days.
        """
        result = await self.db(
            "SELECT opt_out_date FROM opt_out_list WHERE email = ?",
            (email.lower(),),
            fetchone=True
        )
        
        if not result:
            return {"compliant": True, "status": "not_in_list"}
        
        opt_out_dt = datetime.fromisoformat(result["opt_out_date"])
        days_since = (datetime.utcnow() - opt_out_dt).days
        business_days_elapsed = days_since * 5 / 7  # Rough estimate
        
        if business_days_elapsed <= self.opt_out_ttl_days:
            return {
                "compliant": False,
                "status": "violation",
                "message": f"Email sent {business_days_elapsed:.1f} business days after opt-out",
                "deadline": (opt_out_dt + timedelta(days=14)).isoformat()
            }
        
        return {
            "compliant": True,
            "status": "compliant",
            "business_days_since_optout": business_days_elapsed
        }

# ─────── [P5.6] COMPLIANCE CHECKER ─────────
class ComplianceChecker:
    """Master compliance checker across all jurisdictions."""
    
    def __init__(self, db_func):
        self.can_spam = CANSPAMCompliance()
        self.gdpr = GDPRCompliance()
        self.casl = CASLCompliance()
        self.pecr = PECRCompliance()
        self.optout = OptOutManager(db_func)
    
    async def check_email_send(self, email_data: Dict) -> Dict[str, any]:
        """
        Comprehensive compliance check before sending email.
        
        Returns:
            {
                "allowed": bool,
                "checks": {
                    "can_spam": {...},
                    "gdpr": {...},
                    "casl": {...},
                    "pecr": {...},
                    "optout": {...},
                },
                "block_reason": str or None,
            }
        """
        recipient = email_data.get("recipient", {})
        email_content = email_data.get("content", {})
        
        # Check opt-out first (fastest)
        is_opted_out = await self.optout.is_opted_out(recipient.get("email", ""))
        if is_opted_out:
            return {
                "allowed": False,
                "block_reason": "Email recipient has opted out",
                "checks": {"optout": {"opted_out": True}}
            }
        
        # CAN-SPAM validation
        can_spam_result = self.can_spam.validate_email(email_content)
        
        # GDPR check (if EU recipient)
        gdpr_result = self.gdpr.check_legal_basis(recipient) if recipient.get("country") in ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"] else {"valid": True}
        
        # CASL check (if Canadian)
        casl_result = {"compliant": self.casl.validate_consent(recipient)} if self.casl.requires_consent(recipient.get("country")) else {"compliant": True}
        
        # PECR check (if UK)
        pecr_result = self.pecr.check_uk_compliance(recipient)
        
        # Determine if email can be sent
        allowed = (
            can_spam_result.get("compliant", True) and
            gdpr_result.get("valid", True) and
            casl_result.get("compliant", True) and
            (not pecr_result.get("applicable") or pecr_result.get("compliant", True))
        )
        
        block_reason = None
        if not allowed:
            if not can_spam_result.get("compliant"):
                block_reason = f"CAN-SPAM violation: {can_spam_result['issues'][0]}"
            elif not gdpr_result.get("valid"):
                block_reason = f"GDPR violation: No legal basis"
            elif not casl_result.get("compliant"):
                block_reason = f"CASL violation: {recipient.get('email')} - no consent"
            elif pecr_result.get("applicable") and not pecr_result.get("compliant"):
                block_reason = f"PECR violation: {pecr_result['reason']}"
        
        return {
            "allowed": allowed,
            "block_reason": block_reason,
            "checks": {
                "can_spam": can_spam_result,
                "gdpr": gdpr_result,
                "casl": casl_result,
                "pecr": pecr_result,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }

# ─────── DATABASE SETUP ─────────
COMPLIANCE_SCHEMA = """
-- Opt-out list for CAN-SPAM compliance
CREATE TABLE IF NOT EXISTS opt_out_list (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    reason TEXT DEFAULT 'user_request',
    opt_out_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email consent tracking
CREATE TABLE IF NOT EXISTS email_consent (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    country TEXT,
    can_spam_opt_in BOOLEAN DEFAULT TRUE,
    gdpr_consent BOOLEAN DEFAULT FALSE,
    gdpr_consent_date TEXT,
    casl_consent BOOLEAN DEFAULT FALSE,
    pecr_opt_in BOOLEAN DEFAULT FALSE,
    tps_registered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Email send audit log
CREATE TABLE IF NOT EXISTS email_send_audit (
    id INTEGER PRIMARY KEY,
    recipient_email TEXT NOT NULL,
    subject TEXT,
    sent_at TEXT NOT NULL,
    compliance_check_passed BOOLEAN,
    compliance_violations TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_opt_out_email ON opt_out_list(email);
CREATE INDEX IF NOT EXISTS idx_consent_email ON email_consent(email);
"""
