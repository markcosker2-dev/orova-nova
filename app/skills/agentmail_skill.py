"""
AgentMail Skill - Nova's Own Email System
==========================================
Nova gets her own email inbox via AgentMail API.
She can create inboxes, send outreach, check replies, and respond.
"""
import os
import re
import asyncio
import logging
import json
from typing import Dict, Any
from datetime import datetime, timezone
import httpx
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# Cached at module level to avoid repeated env reads
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_TG_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")

async def _send_telegram_alert(message: str):
    """Async Telegram alert — non-blocking, reuses cached token/chat_id."""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        logger.warning("Telegram report skipped: TOKEN or CHAT_ID missing.")
        return
    url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, data={"chat_id": _TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

# ── Globals ──────────────────────────────────────────────────────
_client = None
_nova_inbox_id = None  # Cached inbox address


def _get_client():
    """Lazy-init the AgentMail client. Returns (client, error_msg)."""
    global _client
    if _client is None:
        try:
            from agentmail import AgentMail
            api_key = os.getenv("AGENTMAIL_API_KEY")
            if not api_key:
                return None, "AGENTMAIL_API_KEY not set in environment variables! Set it in Render dashboard or .env file."
            _client = AgentMail(api_key=api_key)
            logger.info("[+] AgentMail client initialized")
        except Exception as e:
            return None, f"Import/Init failed: {str(e)}. Check if 'agentmail' is the correct pip package name."
    return _client, None


def _get_nova_inbox():
    """Get or create Nova's inbox. Returns inbox_id (email address)."""
    global _nova_inbox_id
    if _nova_inbox_id:
        return _nova_inbox_id

    client, error = _get_client()
    if not client:
        return None

    try:
        # Check if Nova already has an inbox
        result = client.inboxes.list()
        if hasattr(result, 'inboxes') and result.inboxes:
            for inbox in result.inboxes:
                if hasattr(inbox, 'display_name') and inbox.display_name and 'nova' in str(inbox.display_name).lower():
                    _nova_inbox_id = inbox.inbox_id
                    logger.info(f"[+] Found existing Nova inbox: {_nova_inbox_id}")
                    return _nova_inbox_id
            # Use the first inbox if none named Nova
            _nova_inbox_id = result.inboxes[0].inbox_id
            logger.info(f"[+] Using existing inbox: {_nova_inbox_id}")
            return _nova_inbox_id
    except Exception as e:
        logger.warning(f"Could not list inboxes: {e}")

    # Create a new Nova inbox
    try:
        from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest
        inbox = client.inboxes.create(
            request=CreateInboxRequest(
                username="nova-orova",
                display_name="Nova | OROVA"
            )
        )
        _nova_inbox_id = inbox.inbox_id
        logger.info(f"[+] Created Nova inbox: {_nova_inbox_id}")
        return _nova_inbox_id
    except Exception as e:
        logger.error(f"Failed to create inbox: {e}")
        return None


def create_inbox(username: str = "nova-orova", display_name: str = "Nova | OROVA") -> Dict[str, Any]:
    """Create a new AgentMail inbox for Nova."""
    client, error = _get_client()
    if not client:
        return {"status": "error", "message": f"AgentMail client not initialized: {error}"}

    try:
        from agentmail.inboxes.types.create_inbox_request import CreateInboxRequest
        inbox = client.inboxes.create(
            request=CreateInboxRequest(
                username=username,
                display_name=display_name
            )
        )
        global _nova_inbox_id
        _nova_inbox_id = inbox.inbox_id
        return {
            "status": "success",
            "inbox_id": inbox.inbox_id,
            "display_name": display_name,
            "message": f"Inbox created: {inbox.inbox_id}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Known disposable/temp email domains (blocklist)
_DISPOSABLE_DOMAINS = frozenset([
    "tempmail.com", "throwaway.email", "guerrillamail.com", "mailinator.com",
    "yopmail.com", "guerrillamailblock.com", "grr.la", "dispostable.com",
    "sharklasers.com", "trashmail.com", "fakeinbox.com", "temp-mail.org",
    "10minutemail.com", "getnada.com", "emailondeck.com",
])

def _validate_email(email: str) -> bool:
    """Basic email format validation before sending."""
    return bool(_EMAIL_RE.match(email.strip())) if email else False


# Commercial language Nova is not authorised to use. `commercial_terms` is
# UNRESOLVED — the owner has set no offer — so ANY of this in outbound copy is
# a promise he would have to honour or retract.
#
# Deliberately narrow. It must not fire on ordinary sales prose ("free up your
# Saturdays", "at no obligation"), because a filter that cries wolf gets
# disabled, and a disabled filter protects nothing. So it matches money figures
# and explicit no-cost OFFERS, not the words in isolation.
_PRICE_PATTERNS = (
    (r"\$\s?\d", "a dollar figure"),
    (r"\b\d+\s?k\s*(?:/|per\s|a\s)?\s*(?:mo|month)", "a monthly figure (e.g. '4k/mo')"),
    (r"\b(?:usd|dollars?)\b\s*\d|\d\s*(?:usd|dollars?)\b", "an amount in dollars"),
    (r"\b(?:starts?|starting|pricing starts)\s+at\b", "a price anchor ('starts at')"),
    (r"\bper\s+month\b.*\b\d|\b\d.*\bper\s+month\b", "a monthly rate"),
    (r"\bfree\s+(?:trial|pilot|month|week|two\s+weeks|audit|for\s+two)", "a free-offer term"),
    (r"\b(?:no|zero)\s+(?:cost|charge)\b", "a no-cost offer"),
    (r"\byou\s+(?:don'?t|do\s+not|won'?t)\s+pay\b", "a no-payment promise"),
    (r"\b(?:discount|money[-\s]?back|refund)\b", "a discount/refund term"),
    (r"\bretainer\b", "a retainer reference"),
)


def _contains_price(subject: str, body: str) -> str:
    """Return a description of the offending term, or '' if the copy is clean."""
    haystack = f"{subject or ''}\n{body or ''}".lower()
    for pattern, label in _PRICE_PATTERNS:
        if re.search(pattern, haystack):
            return label
    return ""


async def _verify_email_deliverable(email: str) -> dict:
    """
    Verify an email is deliverable by checking MX records and basic hygiene.
    Returns: {"valid": bool, "reason": str}
    """
    import re as _re
    email = (email or "").strip().lower()
    
    # Format check
    if not _EMAIL_RE.match(email):
        return {"valid": False, "reason": "Invalid email format"}
    
    # Extract domain
    domain = email.split("@")[1] if "@" in email else ""
    
    # Block disposable domains
    if domain in _DISPOSABLE_DOMAINS:
        return {"valid": False, "reason": f"Disposable email domain: {domain}"}
    
    # Block common fake patterns
    if _re.match(r"^(test|fake|temp|trash|dump|spam)@", email):
        return {"valid": False, "reason": "Likely test/disposable address"}
    
    # MX record check (proper DNS MX lookup via dnspython)
    try:
        import asyncio as _aio
        import dns.resolver

        def _check_mx():
            try:
                answers = dns.resolver.resolve(domain, 'MX')
                return len(answers) > 0
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
                    dns.resolver.NoNameservers, dns.exception.DNSException):
                return False

        loop = _aio.get_running_loop()
        mx_exists = await loop.run_in_executor(None, _check_mx)
        if not mx_exists:
            return {"valid": False, "reason": f"No MX records found for domain: {domain}"}
    except Exception as e:
        logger.warning(f"[EmailVerify] MX check failed for {domain}: {e} — proceeding anyway")
    
    return {"valid": True, "reason": "OK"}


# ── CAN-SPAM compliance footer ───────────────────────────────────────────────
# 15 U.S.C. §7704. CAN-SPAM does NOT require prior consent, so cold B2B email to
# a work address is lawful in the US — but every commercial message must carry
# all of the following, and each non-compliant message is its own violation at
# up to $53,088 (FTC 2026 inflation adjustment):
#
#   1. accurate header / routing information        (AgentMail, real inbox)
#   2. a non-deceptive subject line                 (proofreader gate)
#   3. CLEAR AND CONSPICUOUS NOTICE THAT THE MESSAGE IS AN ADVERTISEMENT
#   4. a valid physical postal address              (BUSINESS_POSTAL_ADDRESS)
#   5. a working opt-out mechanism                  (reply-based, below)
#   6. opt-outs honoured within 10 business days    (reply monitor -> DNC)
#   7. monitoring anyone acting on your behalf      (n/a - no affiliates)
#
# (3) was MISSING and is added here. The FTC mandates no particular wording or
# placement — only that the disclosure be clear and conspicuous — so this is
# phrased plainly rather than shouted, which keeps it honest without reading
# like a legal notice bolted to a one-paragraph email.
#
# The transactional/relationship exemption does NOT apply to this path: cold
# prospecting mail is commercial by primary purpose. A genuine reply to an
# inbound enquiry is a different case and does not route through here.
#
# ⚠️ (5) has an operational dependency worth stating: the opt-out is REPLY-BASED,
# so it only remains functional while the sending inbox exists and the reply
# monitor runs. CAN-SPAM requires the mechanism to work for at least 30 days
# after sending. Rotating or deleting the AgentMail inbox inside that window
# breaks compliance for every message already sent.

_AD_DISCLOSURE_LINE = "This is an advertisement from OROVA, a marketing agency."
_OPT_OUT_LINE = 'Not relevant? Reply "no thanks" and I won\'t write again.'
_warned_no_postal = False


def _apply_compliance_footer(body: str) -> str:
    """Append the CAN-SPAM footer. Idempotent — never double-appends."""
    global _warned_no_postal
    if _OPT_OUT_LINE in (body or ""):
        return body
    postal = os.getenv("BUSINESS_POSTAL_ADDRESS", "").strip()
    if not postal and not _warned_no_postal:
        logger.warning("[CAN-SPAM] BUSINESS_POSTAL_ADDRESS not set — emails ship "
                       "with opt-out but no postal address (required for full "
                       "CAN-SPAM compliance; set it on Render).")
        _warned_no_postal = True
    ident = f"OROVA · {postal}" if postal else "OROVA"
    return (f"{body}\n\n—\n{ident}\n"
            f"{_AD_DISCLOSURE_LINE}\n{_OPT_OUT_LINE}")


async def send_outreach(
    to: str,
    subject: str,
    body: str,
    skip_proofread: bool = False,
    recipient_context: str = "",
    lead_id: int = 0,
    strategy: str = "pas",
    niche: str = "",
    client_id: int = 0,
    *,
    _approval_checked: bool = False,
) -> dict:
    """
    Sends an outreach email via AgentMail API.
    Passes through the AI proofreading gate first unless skip_proofread is True.
    """
    # Validate email format before sending
    if not _validate_email(to):
        logger.warning(f"[AgentMail] Invalid email format: {to}. Skipping send.")
        return {"status": "error", "error": f"Invalid email format: {to}"}

    # ── Opt-out gate (CAN-SPAM) ──────────────────────────────────────────────
    # Mirrors the DNC gate the calling lane already has. Until now the reply
    # classifier DETECTED opt-out language and marked the thread COLD so nothing
    # auto-replied, but the address was never recorded and nothing checked one
    # here — so a later drip cycle could email someone who had explicitly asked
    # to be left alone, breaking the promise the footer's opt-out line makes.
    # Fail-closed, same as the phone gate.
    from app.core.dnc import is_email_suppressed
    if await is_email_suppressed(to):
        logger.warning("[AgentMail] Blocked send — recipient is on the email "
                       "opt-out list (or the lookup failed; fail-closed).")
        return {"status": "error", "skipped": True,
                "error": "Recipient opted out — send blocked."}

    # ── CAN-SPAM postal address: FAIL CLOSED ─────────────────────────────────
    # 15 U.S.C. §7704 requires a valid physical postal address in commercial
    # email. This path used to warn-and-send, and on 2026-07-25 that shipped 48
    # cold emails without one. Every other risky path here fails closed (DNC,
    # opt-out, storage gate); this one failed open, which is exactly why it went
    # unnoticed. Any real address unblocks it — a PO box counts.
    if not os.getenv("BUSINESS_POSTAL_ADDRESS", "").strip():
        logger.error("[AgentMail] Blocked send — BUSINESS_POSTAL_ADDRESS is not "
                     "set, so the footer would ship without the physical address "
                     "CAN-SPAM requires. Set it on Render to unblock.")
        return {"status": "error", "skipped": True,
                "error": "BUSINESS_POSTAL_ADDRESS unset — send blocked (CAN-SPAM)."}

    # ── ICP gate (ADR-0012): never email a disqualified vertical ─────────────
    # Defence in depth. The storage gate now quarantines off-ICP rows, but a row
    # already in flight, or restored from an older snapshot, must not slip
    # through here. This is the check that would have stopped all 48 sends.
    # Reads `business` as well as `vertical`: most rows carry no vertical at all
    # (licence-registry discovery supplies none), and a vertical-only check let
    # "Keith's Auto Repair" sit in production as 'Contacted' on 2026-07-29.
    try:
        from app.skills.lead_validator import off_icp_trade_reason
        if lead_id:
            row = await DatabaseManager.query(
                "SELECT vertical, business FROM leads WHERE id = ?",
                (int(lead_id),), fetchone=True)
            if row:
                why = off_icp_trade_reason(dict(row))
                if why:
                    logger.warning(f"[AgentMail] Blocked send — {why}")
                    return {"status": "error", "skipped": True,
                            "error": f"Off-ICP lead — send blocked. {why}"}
    except Exception as e:
        # Never let a lookup failure become an unchecked send.
        logger.error(f"[AgentMail] ICP pre-send check failed ({e}) — blocking send.")
        return {"status": "error", "skipped": True,
                "error": "ICP pre-send check failed — send blocked (fail-closed)."}

    # Deep verification: MX record check + disposable domain block
    verify_result = await _verify_email_deliverable(to)
    if not verify_result["valid"]:
        logger.warning(f"[AgentMail] Email verification failed for {to}: {verify_result['reason']}")
        return {"status": "error", "error": f"Email not deliverable: {verify_result['reason']}"}

    # Ordered LAST on purpose. Every check above fails closed and is free;
    # this one pages a human. Asking Mark to approve a send that opt-out,
    # CAN-SPAM, the ICP gate or MX verification would have rejected anyway
    # trains him to approve without reading, which is how an approval gate
    # quietly becomes a rubber stamp.
    # ── APPROVAL GATE — the chokepoint, not the call site ────────────────────
    # Of the five paths that reach this function, exactly ONE gated:
    #
    #   worker.py:515   day-0 cold email                     GATED
    #   worker.py:952   cold-escalation re-engagement email  ungated
    #   email_sequence_skill.py:359  drip touches 2,3,4      ungated
    #   outreach_orchestrator.py:502                          ungated
    #   planner.py:245  exposed to the LLM as a TOOL          ungated
    #
    # So "every cold send needs Mark's approval" was true of the first email
    # only. The drip enrols unconditionally — including for leads whose day-0
    # email Mark explicitly did NOT approve (observed live 2026-08-07: an
    # "awaiting approval" log line immediately followed by an enrolment) — and
    # then sends its follow-ups with no gate at all.
    #
    # Only BUSINESS_POSTAL_ADDRESS being unset is currently stopping that. The
    # moment it is set to enable approved email, three of every four touches
    # start going out unsupervised. This is the same shape as the §227(b) hole
    # in outbound_dialer.py, in a second subsystem: a gate applied per-call-site
    # while other paths reach the same sink. And as there, the LLM tool path
    # cannot be gated by convention — there is no call site to edit.
    #
    # `_approval_checked` is keyword-only, underscore-prefixed, and absent from
    # the LLM tool schema in definitions.py (which exposes only to/subject/body),
    # so the model cannot set it. It defaults to False so a NEW caller is gated
    # unless it explicitly opts out — the safe default is the one you get by
    # forgetting.
    #
    # Placed after the cheap fail-closed checks on purpose: never ask Mark to
    # approve a send that opt-out or CAN-SPAM would have blocked anyway.
    if not _approval_checked:
        try:
            from app.core.approval_gate import gate_allows
            allowed = await gate_allows(
                "email",
                {"lead_id": lead_id, "to": to, "subject": subject},
                reason=f"Email to {to} — subject: {subject}",
            )
        except Exception as gate_err:
            logger.error(f"[AgentMail] Approval gate errored for {to} ({gate_err}) "
                         f"— blocking send (fail-closed).")
            return {"status": "error", "skipped": True,
                    "error": f"Approval gate error — send blocked (fail-closed): {gate_err}"}
        if not allowed:
            logger.info(f"[AgentMail] Send to {to} awaiting Mark's approval — skipped this cycle.")
            return {"status": "error", "skipped": True,
                    "error": "Awaiting approval — send skipped this cycle."}

    return await _send_via_agentmail(to, subject, body, skip_proofread, recipient_context, lead_id, strategy, niche, client_id)


async def _send_via_agentmail(to: str, subject: str, body: str, skip_proofread: bool, recipient_context: str, lead_id: int, strategy: str, niche: str, client_id: int) -> dict:
    """Send email via AgentMail API (requires AGENTMAIL_API_KEY)."""
    client, error = _get_client()
    if not client:
         return {"status": "error", "error": f"AgentMail client failed: {error}"}

    # Use Nova's default inbox
    sender = _get_nova_inbox()
    if not sender:
        return {"status": "error", "error": "No Nova inbox available."}

    final_subject = subject
    final_body = body
    quality_score = 100.0
    fixes = "None"

    if not skip_proofread:
        from app.skills.email_proofreader import proofread_email
        attempts = 0
        max_attempts = 3  # Original + 2 retries
        
        while attempts < max_attempts:
            verdict_res = await proofread_email(to, final_subject, final_body, recipient_context)
            verdict = verdict_res.get("verdict", "pass").lower()
            quality_score = verdict_res.get("score", 80.0)
            fixes = verdict_res.get("fixes", "None")
            
            if verdict == "pass":
                final_subject = verdict_res.get("improved_subject", final_subject)
                final_body = verdict_res.get("improved_body", final_body)
                break
            elif verdict == "rewrite" and attempts < max_attempts - 1:
                logger.info(f"[AgentMail] Proofreader rewrite requested (Attempt {attempts+1}). Applying fixes...")
                final_subject = verdict_res.get("improved_subject", final_subject)
                final_body = verdict_res.get("improved_body", final_body)
                attempts += 1
            else:
                # Reject or max attempts reached with failures
                logger.warning(f"[AgentMail] Email outreach to {to} was REJECTED by proofreader. Blocking send.")
                alert_msg = (
                    f"🚫 **Email Send Blocked by Proofreader**\n\n"
                    f"To: {to}\n"
                    f"Original Subject: {subject}\n"
                    f"Score: {quality_score}\n"
                    f"Reason/Fixes:\n{fixes}"
                )
                await _send_telegram_alert(alert_msg)
                
                try:
                    now = datetime.now()
                    await DatabaseManager.aupdate_metrics({"emails_rejected": 1}, client_id=client_id)
                    await DatabaseManager.query(
                        """INSERT INTO outreach_outcomes (action, strategy, niche, recipient, lead_id, result, quality_score, send_hour, send_day, metadata, client_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        ("email_sent", strategy, niche, to, lead_id, "rejected", quality_score, now.hour, now.weekday(), json.dumps({"fixes": fixes}), client_id)
                    )
                except Exception as db_err:
                    logger.error(f"Failed to log rejected outcome: {db_err}")
                    
                return {"status": "rejected", "reason": fixes, "score": quality_score}

    # CAN-SPAM: every commercial email carries a clear opt-out (and the postal
    # address once configured). Applied AFTER the proofreader so boilerplate is
    # never QA'd against the 75-word copy budget.
    final_body = _apply_compliance_footer(final_body)

    # ── NO PRICE MAY LEAVE THIS FUNCTION — fail closed ───────────────────────
    # The owner mandate is that Nova states no price, because no offer has been
    # set. The two live Retell voice prompts enforce this line-by-line with
    # scripted deflections. Email had no equivalent: the ONLY gate on outbound
    # copy was `email_proofreader`, which was handed the real retainer figures
    # in its brand context AND authorised to rewrite the body on a REWRITE
    # verdict. An LLM holding the real numbers and told to improve the copy is
    # not a control against quoting them — it is the likeliest source of one.
    #
    # Prices are now stripped from that prompt, but a rubric instruction is
    # guidance, not enforcement. This is the enforcement: the final text, after
    # proofreading and after the footer, is checked for a quotable figure and
    # the send is blocked rather than corrected. Same fail-closed posture as
    # opt-out, CAN-SPAM and the ICP gate directly above.
    _priced = _contains_price(final_subject, final_body)
    if _priced:
        logger.error(f"[AgentMail] Blocked send to {to} — outbound copy contains a "
                     f"commercial term Nova is not authorised to state: {_priced}. "
                     f"commercial_terms is UNRESOLVED; the owner has set no offer.")
        return {"status": "error", "skipped": True,
                "error": f"Blocked — unauthorised price/offer language in outbound copy: {_priced}"}

    try:
        # Send using AgentMail client synchronous call wrapped inside run_in_executor
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.inboxes.messages.send(
                inbox_id=sender,
                to=to,
                subject=final_subject,
                text=final_body
            )
        )
        logger.info(f"[AgentMail] Sent to {to} | subject='{final_subject}'")
        msg_id = getattr(result, "message_id", None)
        
        try:
            now = datetime.now()
            await DatabaseManager.query(
                "INSERT OR IGNORE INTO client_quotas (client_id) VALUES (?)", (client_id,)
            )
            await DatabaseManager.query(
                "UPDATE client_quotas SET emails_sent_today = emails_sent_today + 1 WHERE client_id = ?", (client_id,)
            )
            await DatabaseManager.query(
                """INSERT INTO outreach_outcomes (action, strategy, niche, recipient, lead_id, result, quality_score, send_hour, send_day, metadata, client_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("email_sent", strategy, niche, to, lead_id, "sent", quality_score, now.hour, now.weekday(), json.dumps({"message_id": msg_id}), client_id)
            )
        except Exception as db_err:
            logger.error(f"Failed to log success outcome: {db_err}")

        # Unified event log (ADR-0007): one wiring point covers every email
        # send in the system — hunt, escalation, drip, reply. Fail-open.
        from app.core.event_log import alog_event
        await alog_event(lead_id, "outreach_sent", "courier",
                         payload={"to": to, "subject": final_subject, "strategy": strategy,
                                  "niche": niche, "quality_score": quality_score},
                         variant_id=strategy, campaign_id=client_id)

        return {"status": "success", "to": to, "message_id": msg_id, "score": quality_score}
    except Exception as e:
        logger.error(f"[AgentMail] Send failed to {to}: {e}", exc_info=True)
        try:
            now = datetime.now()
            await DatabaseManager.query(
                """INSERT INTO outreach_outcomes (action, strategy, niche, recipient, lead_id, result, quality_score, send_hour, send_day, metadata, client_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("email_sent", strategy, niche, to, lead_id, "failed", quality_score, now.hour, now.weekday(), json.dumps({"error": str(e)}), client_id)
            )
        except Exception as db_err:
            logger.error(f"Failed to log fail outcome: {db_err}")
        return {"status": "error", "error": str(e)}


_LAST_REPLY_READ_ERROR = object()

async def _get_last_reply_check():
    """Read last-processed reply timestamp from state_store via DatabaseManager.
    Returns:
        datetime if checkpoint exists
        None if checkpoint is missing (first run)
        _LAST_REPLY_READ_ERROR sentinel if a read error occurs
    """
    try:
        val = await DatabaseManager.get_state('last_reply_check_at', None)
        if val:
            return datetime.fromisoformat(val)
        return None
    except Exception as e:
        logger.warning(f"Could not read last_reply_check_at: {e}")
        return _LAST_REPLY_READ_ERROR


async def _set_last_reply_check(ts: datetime) -> bool:
    """Persist last-processed reply timestamp to state_store via DatabaseManager.

    Returns:
        True if the checkpoint was persisted successfully, False otherwise.
        Callers should treat a False return as a write failure and react
        accordingly (retry, skip advancement, or return an error).
    """
    try:
        await DatabaseManager.set_state('last_reply_check_at', ts.isoformat())
        return True
    except Exception as e:
        logger.warning(f"Could not persist last_reply_check_at: {e}")
        return False


async def check_replies(inbox_id: str = None, limit: int = 10, advance_checkpoint: bool = True) -> Dict[str, Any]:
    """
    Check Nova's inbox for new INBOUND messages since last check.

    Fixes two bugs from the previous version:
    1. No labels filter meant SENT messages could show up as 'replies'.
       Now filtered to labels=["INBOX"].
    2. No checkpoint meant the same messages re-alerted every 5min cycle.
       Now tracks last_reply_check_at in state_store.

    Args:
        advance_checkpoint: If True (default), advance the checkpoint after
            fetching. Read-only callers (morning_brief, categorize, etc.)
            should pass False so the owning flow (run_reply_monitor) can
            advance the checkpoint only after its side effects succeed.
            The latest_ts is always returned in the response dict so the
            owning flow can call _set_last_reply_check manually if needed.
    """
    client, error = _get_client()
    if not client:
        return {"status": "error", "message": f"AgentMail client not initialized: {error}"}

    inbox = inbox_id or _get_nova_inbox()
    if not inbox:
        return {"status": "error", "message": "No inbox available."}

    last_checked = await _get_last_reply_check()

    # Read error — return error without advancing checkpoint
    if last_checked is _LAST_REPLY_READ_ERROR:
        return {"status": "error", "message": "Database read error — cannot determine last check time."}

    now = datetime.now(timezone.utc)

    # First run: set checkpoint, return empty — don't alert on backlog
    if last_checked is None:
        if advance_checkpoint:
            ok = await _set_last_reply_check(now)
            if not ok:
                return {"status": "error", "message": "Failed to persist initial checkpoint — database write error."}
        logger.info("[AgentMail] First check — checkpoint set, no backlog alert.")
        return {"status": "success", "inbox": inbox, "count": 0, "messages": [], "latest_ts": now.isoformat()}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.inboxes.messages.list(
                inbox_id=inbox,
                limit=limit,
                labels=["INBOX"],
                after=last_checked,
            )
        )
        messages = []
        latest_ts = last_checked  # track newest message actually processed
        if latest_ts is not None and latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=timezone.utc)
        if hasattr(result, 'messages') and result.messages:
            for msg in result.messages[:limit]:
                msg_ts = getattr(msg, 'created_at', None)
                if msg_ts:
                    try:
                        parsed = datetime.fromisoformat(str(msg_ts)) if isinstance(msg_ts, str) else msg_ts
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        if parsed > latest_ts:
                            latest_ts = parsed
                    except (ValueError, TypeError):
                        pass
                messages.append({
                    "message_id": getattr(msg, 'message_id', 'unknown'),
                    "from": getattr(msg, 'from_', getattr(msg, 'sender', 'unknown')),
                    "subject": getattr(msg, 'subject', 'No subject'),
                    "snippet": str(getattr(msg, 'text', getattr(msg, 'snippet', '')))[:200],
                    "date": str(msg_ts or '')
                })

        # Advance checkpoint to latest processed message timestamp (not `now`)
        # so messages arriving between last_checked and now but beyond `limit`
        # are not skipped on the next check cycle.
        # Only advance when the owning flow requests it; read-only callers
        # pass advance_checkpoint=False so run_reply_monitor can advance
        # after its side effects (alerts, metrics) succeed.
        if advance_checkpoint:
            ok = await _set_last_reply_check(latest_ts)
            if not ok:
                return {"status": "error", "message": "Messages fetched but failed to persist checkpoint — database write error."}

        return {
            "status": "success",
            "inbox": inbox,
            "count": len(messages),
            "messages": messages,
            "latest_ts": latest_ts.isoformat() if latest_ts else None,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def reply_to_email(message_id: str, body: str, inbox_id: str = None) -> Dict[str, Any]:
    """Reply to a specific email in Nova's inbox."""
    client, error = _get_client()
    if not client:
        return {"status": "error", "message": f"AgentMail client not initialized: {error}"}

    inbox = inbox_id or _get_nova_inbox()
    if not inbox:
        return {"status": "error", "message": "No inbox available."}

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: client.inboxes.messages.reply(
                inbox_id=inbox,
                message_id=message_id,
                text=body
            )
        )
        logger.info(f"[+] Replied to message {message_id}")
        return {
            "status": "success",
            "message_id": message_id,
            "reply": body[:100],
            "message": f"Reply sent to message {message_id}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Single-reply intent classification (drives the HOT-reply booking funnel) ──
# Interest signals that mark a reply HOT when the LLM is unavailable.
_HOT_REPLY_SIGNALS = (
    "interested", "sounds good", "let's talk", "lets talk", "call me", "book",
    "schedule", "set up a call", "set up a time", "demo", "pricing", "price",
    "how much", "quote", "tell me more", "learn more", "meeting", "available",
    "when can", "keen", "let's do", "lets do", "get started", "sign up",
)
# Opt-out language — a hard COLD regardless of anything else (never auto-reply).
_OPTOUT_REPLY_SIGNALS = (
    "unsubscribe", "not interested", "no thanks", "no thank you", "remove me",
    "stop emailing", "take me off", "opt out", "opt-out", "do not contact",
    "leave me alone", "wrong person", "please stop",
)


def is_optout_reply(subject: str, snippet: str) -> bool:
    """True if this reply asks to be left alone.

    Public because the reply lane needs to SUPPRESS the address, not just
    classify the thread COLD — and it must read the same keyword list rather
    than keeping a second copy that can drift.
    """
    text = f"{subject or ''} {snippet or ''}".lower()
    return any(sig in text for sig in _OPTOUT_REPLY_SIGNALS)


def _keyword_classify_reply(subject: str, snippet: str) -> str:
    """Offline heuristic used when the LLM can't be reached."""
    text = f"{subject or ''} {snippet or ''}".lower()
    if any(sig in text for sig in _OPTOUT_REPLY_SIGNALS):
        return "COLD"
    if any(sig in text for sig in _HOT_REPLY_SIGNALS):
        return "HOT"
    return "WARM"


async def classify_reply_intent(subject: str, snippet: str, sender: str = "") -> str:
    """Classify one inbound reply as HOT / WARM / COLD.

    Tries the LLM first (same taxonomy as summarize_and_categorize_inbox); on any
    failure — including no live LLM key, the current blocker — it falls back to a
    keyword heuristic so the reply funnel keeps working. Opt-out language always
    resolves to COLD *before* the LLM runs, so we never auto-send a booking link
    to someone who asked to be left alone.
    """
    # Opt-out is a hard stop — don't even spend an LLM call on it.
    if _keyword_classify_reply(subject, snippet) == "COLD":
        return "COLD"
    try:
        from app.core.ai_client import UnifiedAIClient
        ai = UnifiedAIClient()
        prompt = (
            "Classify this inbound reply to a B2B sales outreach email as exactly "
            "one word: HOT, WARM, or COLD.\n"
            "- HOT: wants to talk/meet, asks about pricing, says yes/interested, "
            "requests a call or demo.\n"
            "- WARM: mild interest, a question, 'maybe later', not urgent.\n"
            "- COLD: not interested, opt-out, auto-reply, irrelevant.\n\n"
            f"From: {sender}\nSubject: {subject}\nBody: {snippet}\n\n"
            "Answer with ONE word only."
        )
        verdict = (await ai.write(prompt) or "").strip().upper()
        for label in ("HOT", "WARM", "COLD"):
            if label in verdict:
                return label
    except Exception as e:
        logger.info(f"[classify_reply] LLM unavailable ({e}); using keyword heuristic.")
    return _keyword_classify_reply(subject, snippet)


async def summarize_and_categorize_inbox(inbox_id: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    Scans the inbox and categorizes leads based on the Sales Guide logic.
    Categorizes as HOT, WARM, or COLD.
    """
    logger.info("[AGENTMAIL] Running inbox categorization check...")
    
    # 1. Fetch recent messages
    raw_inbox = await check_replies(inbox_id, limit, advance_checkpoint=False)
    if raw_inbox["status"] != "success" or not raw_inbox["messages"]:
        return raw_inbox

    messages = raw_inbox["messages"]
    
    prompt = (
        "Categorize these emails for a sales business (OROVA) based on the SALES GUIDE:\n\n"
        "LOGIC:\n"
        "- HOT: Inbound leads, replies to outreach, meeting requests, pricing questions, referral intros. Needs IMMEDIATE action.\n"
        "- WARM: Questions, interested-but-not-urgent, newsletters from competitors, industry news.\n"
        "- COLD: Spam, marketing blasts, newsletters, irrelevant.\n\n"
        "MESSAGES:\n"
    )
    
    for i, msg in enumerate(messages):
        prompt += f"[{i}] From: {msg['from']}, Subject: {msg['subject']}, Snippet: {msg['snippet']}\n"
    
    prompt += (
        "\nReturn a JSON array of objects with 'index', 'category' (HOT/WARM/COLD), and 'justification'.\n"
        "ONLY return the JSON array."
    )
    
    try:
        from app.core.ai_client import UnifiedAIClient
        ai = UnifiedAIClient()
        cat_json = await ai.write(prompt)
        # Simple cleanup if AI includes markdown blocks
        cat_json = cat_json.strip().replace("```json", "").replace("```", "").strip()
        categorizations = json.loads(cat_json)
        
        # Merge categorizations back into messages
        for cat in categorizations:
            idx = cat.get("index")
            if 0 <= idx < len(messages):
                messages[idx]["category"] = cat.get("category", "COLD")
                messages[idx]["justification"] = cat.get("justification", "")
        
        # Sort by HOT first
        messages.sort(key=lambda x: x.get("category", "COLD") == "HOT", reverse=True)
        
        return {
            "status": "success",
            "count": len(messages),
            "messages": messages,
            "summary_report": f"Processed {len(messages)} messages. Found {len([m for m in messages if m.get('category') == 'HOT'])} HOT leads."
        }
    except Exception as e:
        logger.error(f"Categorization failed: {e}")
        return {"status": "error", "message": f"Categorization failed: {str(e)}", "partial_data": raw_inbox}
