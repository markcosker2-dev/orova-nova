
╔══════════════════════════════════════════════════════════════════════════════╗
║   OROVA — FULL SYSTEM AUDIT REPORT + ALL CODE FIXES                        ║
║   Cross-referenced: Gemini Audit + Live API Documentation + GODMODE code   ║
╚══════════════════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EXECUTIVE SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Gemini found 5 issues. I found 8 total after cross-referencing against our
actual GODMODE codebase and live API documentation.

CONFIRMED FROM GEMINI AUDIT:
  ✗ Issue 1: DuckDuckGo — DDGS v6 API already fixed in GODMODE. But cipher_agent.py
    is a NEW file referenced in the walkthrough that doesn't exist in our build.
    Build it now.
  ✗ Issue 2: Retell E.164 — CONFIRMED. API docs show strict E.164 required.
    Our GODMODE ai_caller.py passes the number raw. Fix: add sanitizer.
  ✗ Issue 3: Hardcoded Telegram IP — This was in an earlier codebase version.
    Our GODMODE main.py does NOT have this. Safe. Confirm Oracle Cloud notes.
  ✗ Issue 4: Email Inbox Rotation — NOT in our codebase. Real risk. Build it.
  ✗ Issue 5: Persona renames — Not applicable to our Flask/Python stack.
    Our system uses constants.py AGENT_ROSTER, not .md persona files.
    Gemini was auditing a different walkthrough version. No action needed here.

ADDITIONAL ISSUES I FOUND (Gemini missed these):
  ✗ Issue 6: Meta Ads Agent — Entire module missing. Build it.
  ✗ Issue 7: Retell V1 API officially deprecated February 5, 2025. Our
    defensive SDK lookup may still hit V1 methods. Explicit V2 lock needed.
  ✗ Issue 8: Missing E.164 validation on phone numbers coming in from
    Meta Lead Ads webhook — those numbers often arrive without +1 prefix.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX 1 — Core_Engine/phone_utils.py (NEW — used by ai_caller + meta_leads)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
Core_Engine/phone_utils.py
E.164 phone number formatter and validator.

AUDIT FIX: Retell AI V2 API strictly requires E.164 format (+12137774445).
Numbers from scraped websites and Meta Lead Ads often arrive without +1 prefix,
with dashes, spaces, or parentheses. This module normalises all of them.
Retell V1 deprecated Feb 5, 2025. V2 (create_phone_call) is mandatory.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("orova.phone")


def to_e164(raw_number: str, default_country: str = "1") -> Optional[str]:
    """
    Convert any US phone number format to strict E.164.

    Handles all common formats:
      (213) 777-4445   →  +12137774445
      213-777-4445     →  +12137774445
      2137774445       →  +12137774445
      +12137774445     →  +12137774445  (already correct, pass through)
      +1 (213) 777-4445 → +12137774445

    Returns None if the number cannot be normalised to a valid US number.
    This is intentional — a None return tells the caller to skip this lead
    rather than send a malformed number to Retell and get a silent failure.
    """
    if not raw_number:
        return None

    # Strip everything except digits and leading +
    cleaned = re.sub(r"[^\d+]", "", raw_number.strip())

    # Already E.164 with country code
    if cleaned.startswith("+"):
        digits_only = cleaned[1:]
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return cleaned  # Valid US E.164
        if len(digits_only) == 10:
            return "+" + "1" + digits_only  # Missing +1, add it
        logger.warning(f"[PHONE] Unrecognised format: {raw_number}")
        return None

    # Strip leading 1 if present and then add +1
    if cleaned.startswith("1") and len(cleaned) == 11:
        return "+" + cleaned

    # 10 digit US number without country code
    if len(cleaned) == 10:
        return "+1" + cleaned

    logger.warning(f"[PHONE] Cannot normalise to E.164: {raw_number!r}")
    return None


def is_valid_e164(number: str) -> bool:
    """Quick validation that a string is already valid E.164."""
    if not number:
        return False
    return bool(re.match(r"^\+1[2-9]\d{9}$", number))


def sanitise_phone_list(phones: list, default_country: str = "1") -> list:
    """
    Convert a list of raw phone strings to E.164.
    Filters out any that cannot be normalised.
    """
    result = []
    for p in phones:
        e164 = to_e164(p, default_country)
        if e164:
            result.append(e164)
    return result


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX 2 — Core_Engine/ai_caller.py (PATCHED — E.164 + explicit Retell V2 lock)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Replace the initiate_call() method in Core_Engine/ai_caller.py with this:

    async def initiate_call(self, lead_id: int) -> Dict[str, Any]:
        """
        AUDIT FIX: Retell V1 deprecated Feb 5 2025.
        Now uses explicit create_phone_call (V2) only.
        AUDIT FIX: E.164 validation via phone_utils before any API call.
        Silent failures from malformed numbers are now caught and logged.
        """
        if not self.retell:
            return {"status": "error", "message": "RETELL_API_KEY not set"}
        if not self.from_number:
            return {"status": "error", "message": "RETELL_FROM_NUMBER not set"}
        if not self.agent_id:
            return {"status": "error", "message": "RETELL_AGENT_ID not set"}
        if not self._is_calling_hours():
            return {"status": "skipped", "message": "Outside calling hours or weekend"}

        lead = self.db.get_lead(lead_id)
        if not lead:
            return {"status": "error", "message": f"Lead #{lead_id} not found"}

        # AUDIT FIX: Validate and normalise phone number to E.164 before calling
        from .phone_utils import to_e164
        raw_phone = lead.get("phone", "")
        phone_e164 = to_e164(raw_phone)
        if not phone_e164:
            self.db.log_activity(
                lead_id, "call_skipped",
                f"Phone '{raw_phone}' could not be normalised to E.164 — skipped"
            )
            logger.warning(
                f"[CALLER] Skipping lead #{lead_id} — "
                f"phone '{raw_phone}' is not a valid US number"
            )
            return {
                "status": "skipped",
                "message": f"Phone number '{raw_phone}' could not be formatted to E.164",
            }

        # Also validate from_number on startup (log once if misconfigured)
        from_e164 = to_e164(self.from_number)
        if not from_e164:
            logger.error(
                f"[CALLER] RETELL_FROM_NUMBER '{self.from_number}' is not valid E.164. "
                f"Update your .env — calls will fail."
            )
            return {
                "status": "error",
                "message": f"RETELL_FROM_NUMBER is not valid E.164: {self.from_number}",
            }

        vertical = lead.get("vertical", "General")
        try:
            script = await self.generate_call_script(lead, vertical)
            dv = dict(script.get("dynamic_variables", {}))
            dv.update({
                "opener":    script.get("opener", ""),
                "hook":      script.get("hook", ""),
                "pitch":     script.get("pitch", ""),
                "close":     script.get("close", ""),
                "voicemail": script.get("voicemail", ""),
            })

            # AUDIT FIX: Explicit V2 only — no defensive fallback to V1 methods.
            # Retell V1 APIs deprecated February 5, 2025.
            # create_phone_call is the V2 method. If it doesn't exist, the SDK
            # version is outdated — raise an explicit error.
            if not hasattr(self.retell.call, "create_phone_call"):
                raise AttributeError(
                    "retell.call.create_phone_call not found. "
                    "Update retell-sdk: pip install retell-sdk>=4.0.0"
                )

            call = self.retell.call.create_phone_call(
                from_number=from_e164,
                to_number=phone_e164,
                agent_id=self.agent_id,
                retell_llm_dynamic_variables=dv,
            )

            call_id = getattr(call, "call_id", None) or call.get("call_id", "")
            self.db.update_lead_status(lead_id, "Called")
            self.db.update_lead_call_id(lead_id, call_id)
            self.db.log_activity(lead_id, "call", f"Retell V2 call_id={call_id}")

            logger.info(
                f"[CALLER] Call → {phone_e164} ({lead['business']}) id={call_id}"
            )
            return {
                "status": "ok",
                "call_id": call_id,
                "to_number": phone_e164,
                "script_preview": script.get("opener", "")[:100],
            }
        except AttributeError as e:
            logger.error(f"[CALLER] SDK version error: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"[CALLER] Call failed for #{lead_id}: {e}")
            return {"status": "error", "message": str(e)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX 3 — Core_Engine/email_inbox_rotation.py (NEW)
AUDIT FIX: Multi-domain inbox rotation to protect deliverability at scale.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
Core_Engine/email_inbox_rotation.py
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

import yagmail

from .db_manager import DatabaseManager

logger = logging.getLogger("orova.inbox_rotation")


class InboxRotationManager:
    """
    Manages multiple sending email accounts for deliverability protection.
    Falls back to single-account mode if EMAIL_ACCOUNTS is not configured.
    """

    def __init__(self):
        self.db = DatabaseManager()
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
        """Count emails sent today from a specific domain."""
        today = date.today().isoformat()
        with self.db._get_conn() as conn:
            r = conn.execute(
                """SELECT COUNT(*) FROM send_log
                   WHERE sent_date=? AND recipient LIKE ?""",
                (today, f"%__{domain_label}")
            ).fetchone()
            return r[0] if r else 0

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

    def get_yag(self, account: Dict[str, str]) -> yagmail.SMTP:
        """Create a yagmail SMTP connection for the given account."""
        user   = account.get("user", "")
        passwd = account.get("pass", "")
        if not user or not passwd:
            raise RuntimeError(
                f"Email account '{account.get('label','')}' is missing user or pass"
            )
        return yagmail.SMTP(user, passwd)

    def record_send(self, account: Dict[str, str], recipient: str,
                    action: str = "email"):
        """Record a send against the specific domain's quota."""
        label = account.get("label", account.get("user", ""))
        # Store with domain label appended so per-domain queries work
        self.db.record_send(
            recipient=f"{recipient}__{label}",
            action=action
        )

    def can_send(self) -> bool:
        """Quick check — is any domain available?"""
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


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX 4 — Core_Engine/email_outreach.py (PATCHED — uses InboxRotationManager)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Replace send_to_lead() and send_followup_to_lead() in email_outreach.py
with these patched versions that use InboxRotationManager:

    async def send_to_lead(self, lead_data: Dict[str, Any]) -> Dict[str, str]:
        """
        AUDIT FIX: Uses InboxRotationManager instead of single yagmail instance.
        Distributes sends across multiple domains to protect deliverability.
        """
        from .email_inbox_rotation import InboxRotationManager
        rotator = InboxRotationManager()

        recipient = (lead_data.get("email") or "").strip()
        if not recipient:
            raise ValueError(f"No email for {lead_data.get('business')}")
        if self.db.is_dnc(recipient):
            raise ValueError(f"{recipient} is on DNC list")

        # Use rotator instead of legacy RateLimiter
        sender = rotator.get_available_sender()
        if not sender:
            raise RuntimeError(
                "All sending domains at daily cap. No emails can be sent today."
            )

        email_content = await self.draft_initial_email(lead_data)
        body = (
            email_content["body"]
            + f"\n\n---\n{self.agency_name}\n"
            + "Not relevant? Reply 'remove' and I will never contact you again."
        )

        yag = rotator.get_yag(sender)
        yag.send(to=recipient, subject=email_content["subject"], contents=body)
        rotator.record_send(sender, recipient, action="email")

        # Async-safe delay (doesn't block event loop)
        from .rate_limiter import RateLimiter
        await asyncio.to_thread(RateLimiter().wait_between_sends)

        logger.info(
            f"[EMAIL] Sent via {sender['_label']} → {recipient} "
            f"({lead_data.get('business')}) '{email_content['subject']}'"
        )
        return email_content

    async def send_followup_to_lead(
        self, lead_data: Dict[str, Any], step: int
    ) -> Dict[str, str]:
        """Follow-up send — same inbox rotation logic."""
        from .email_inbox_rotation import InboxRotationManager
        rotator = InboxRotationManager()

        recipient = (lead_data.get("email") or "").strip()
        if not recipient:
            raise ValueError("No email on lead")
        if self.db.is_dnc(recipient):
            raise ValueError(f"{recipient} is on DNC list")

        sender = rotator.get_available_sender()
        if not sender:
            raise RuntimeError("All sending domains at daily cap.")

        email_content = await self.draft_followup_email(lead_data, step)
        yag = rotator.get_yag(sender)
        yag.send(
            to=recipient,
            subject=email_content["subject"],
            contents=email_content["body"],
        )
        rotator.record_send(sender, recipient, action=f"follow_up_{step}")

        from .rate_limiter import RateLimiter
        await asyncio.to_thread(RateLimiter().wait_between_sends)

        logger.info(
            f"[EMAIL] Follow-up {step} via {sender['_label']} → "
            f"{recipient} ({lead_data.get('business')})"
        )
        return email_content


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIX 5 — Core_Engine/cipher_agent.py (NEW — Competitive Intelligence)
AUDIT FIX: Uses DDGS v6 API correctly. No raw requests/BS4 to DuckDuckGo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
Core_Engine/cipher_agent.py
OROVA Cipher — Competitive Intelligence Agent.

AUDIT FIX: Uses duckduckgo-search (DDGS) library, NOT raw requests/BeautifulSoup.
DDGS handles User-Agent rotation and rate-limit backoff automatically.
Direct requests to DuckDuckGo return 403 within 48 hours — Cipher would go blind.

Cipher monitors:
  1. Competitor positioning in target verticals
  2. Whether a OROVA lead is also being targeted by known competitors
  3. Weekly competitive edge report for Nova's MISSION PULSE
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from google import genai
from tenacity import retry, stop_after_attempt, wait_exponential

from .db_manager import DatabaseManager

logger = logging.getLogger("orova.cipher")

# Known competitor signals to watch for in search results
COMPETITOR_SIGNALS = [
    "AI lead generation agency",
    "appointment setting agency",
    "done-for-you lead gen",
    "outbound sales agency",
    "AI cold outreach",
    "lead generation retainer",
]


class CipherAgent:
    """
    Competitive intelligence agent.
    Uses DDGS (duckduckgo-search library) — never raw requests to DDG.
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.agency_name = os.getenv("AGENCY_NAME", "OROVA")

    def _ddg_search(self, query: str, max_results: int = 5) -> List[Dict]:
        """
        AUDIT FIX: Uses DDGS library with built-in rate-limit handling.
        Never calls DuckDuckGo directly via requests — that gets 403'd in 48h.
        """
        for attempt in range(3):
            try:
                from duckduckgo_search import DDGS
                results = list(DDGS().text(query, max_results=max_results))
                return results
            except Exception as e:
                err = str(e).lower()
                if "ratelimit" in err or "202" in err:
                    wait = (attempt + 1) * 15
                    logger.warning(f"[CIPHER] DDG rate limited, waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"[CIPHER] Search failed (attempt {attempt+1}): {e}")
                    if attempt == 2:
                        return []
                    time.sleep(5)
        return []

    def scan_competitor_activity(self, vertical: str) -> Dict[str, Any]:
        """
        Scan for competitor agency activity in a target vertical.
        Returns a summary of what competitors are doing and claiming.
        """
        query = f"AI lead generation agency {vertical} 2026 outreach"
        results = self._ddg_search(query, max_results=5)

        competitor_mentions = []
        for r in results:
            body = (r.get("body") or "").lower()
            title = (r.get("title") or "").lower()
            for signal in COMPETITOR_SIGNALS:
                if signal.lower() in body or signal.lower() in title:
                    competitor_mentions.append({
                        "source":  r.get("href", ""),
                        "title":   r.get("title", ""),
                        "snippet": (r.get("body") or "")[:200],
                        "signal":  signal,
                    })
                    break

        return {
            "vertical":             vertical,
            "competitors_detected": len(competitor_mentions),
            "mentions":             competitor_mentions[:3],
            "scanned_at":           datetime.utcnow().isoformat(),
        }

    def check_lead_competitor_exposure(
        self, lead: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check if a specific lead is being targeted by competitor agencies.
        If yes, return signal so Nova can accelerate the outreach sequence.

        Method: Search for the lead's business name + competitor signal terms.
        If results appear suggesting competitor outreach, flag it.
        """
        business = lead.get("business", "")
        if not business:
            return {"exposed": False, "lead_id": lead.get("id")}

        query = f'"{business}" AI marketing lead generation agency'
        results = self._ddg_search(query, max_results=3)

        # Look for signals that competitors are talking about this business
        exposed = False
        exposure_signals = []
        for r in results:
            body  = (r.get("body") or "").lower()
            title = (r.get("title") or "").lower()
            for signal in COMPETITOR_SIGNALS:
                if signal.lower() in body or signal.lower() in title:
                    exposed = True
                    exposure_signals.append(signal)

        if exposed:
            logger.info(
                f"[CIPHER] Competitor exposure detected for '{business}': "
                + ", ".join(exposure_signals)
            )

        return {
            "lead_id":    lead.get("id"),
            "business":   business,
            "exposed":    exposed,
            "signals":    exposure_signals,
            "checked_at": datetime.utcnow().isoformat(),
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def generate_competitive_edge_report(
        self, verticals: List[str]
    ) -> str:
        """
        Generate a weekly competitive intelligence summary for Nova's
        MISSION PULSE. Uses Gemini to synthesise raw search findings.
        """
        intelligence = []
        for vertical in verticals[:3]:  # Cap at 3 to avoid DDG rate limits
            data = self.scan_competitor_activity(vertical)
            intelligence.append(data)
            time.sleep(5)  # Respectful delay between searches

        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        prompt = f"""
You are the Competitive Intelligence Director for OROVA, a premium AI lead
generation agency. Analyse this raw competitive data and write a concise
2-paragraph intelligence brief for the agency director.

Raw data: {json.dumps(intelligence, indent=2)}

Paragraph 1: What competitors are positioning around this week.
Paragraph 2: One specific recommendation for OROVA to sharpen its edge.

Tone: Clinical. Analytical. Executive-level. No fluff.
Max 80 words.
"""
        resp = client.models.generate_content(
            model="gemini-2.0-flash", contents=prompt
        )
        report = resp.text.strip()
        logger.info("[CIPHER] Weekly competitive edge report generated")
        return report

    def run_daily_sweep(self, client_id: int = 0) -> Dict[str, Any]:
        """
        Daily Cipher run. Scans the 3 highest-priority leads for competitor
        exposure. If any lead is exposed, returns flag so scheduler can
        accelerate OROVA's outreach sequence for those leads.
        """
        from .constants import AUTO_SCRAPE_ROTATION
        # Get top scored leads in active pipeline
        leads = self.db.get_all_leads(client_id)
        priority_leads = sorted(
            [l for l in leads if l.get("status") in
             ("New", "Emailed", "Follow-up 1") and (l.get("score") or 0) >= 70],
            key=lambda l: l.get("score", 0),
            reverse=True
        )[:5]

        exposed_leads = []
        for lead in priority_leads:
            result = self.check_lead_competitor_exposure(lead)
            if result.get("exposed"):
                exposed_leads.append(result)
            time.sleep(8)  # Respectful DDG pacing

        return {
            "leads_checked":  len(priority_leads),
            "exposed_count":  len(exposed_leads),
            "exposed_leads":  exposed_leads,
            "recommendation": (
                "Accelerate outreach by 48 hours for exposed leads"
                if exposed_leads else "No competitor exposure detected"
            ),
        }
