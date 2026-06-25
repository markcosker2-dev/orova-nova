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


async def send_outreach(
    to: str, 
    subject: str, 
    body: str, 
    skip_proofread: bool = False, 
    recipient_context: str = "",
    lead_id: int = 0,
    strategy: str = "pas",
    niche: str = "",
    client_id: int = 0
) -> dict:
    """
    Sends an outreach email via AgentMail API.
    Passes through the AI proofreading gate first unless skip_proofread is True.
    """
    # Validate email format before sending
    if not _validate_email(to):
        logger.warning(f"[AgentMail] Invalid email format: {to}. Skipping send.")
        return {"status": "error", "error": f"Invalid email format: {to}"}

    # Deep verification: MX record check + disposable domain block
    verify_result = await _verify_email_deliverable(to)
    if not verify_result["valid"]:
        logger.warning(f"[AgentMail] Email verification failed for {to}: {verify_result['reason']}")
        return {"status": "error", "error": f"Email not deliverable: {verify_result['reason']}"}

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
