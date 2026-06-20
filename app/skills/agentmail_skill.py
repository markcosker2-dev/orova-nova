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
from datetime import datetime
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
    
    # MX record check
    try:
        import asyncio as _aio
        loop = _aio.get_event_loop()
        import socket
        
        def _check_mx():
            try:
                result = socket.getaddrinfo(domain, 25, socket.AF_INET, socket.SOCK_STREAM)
                return len(result) > 0
            except (socket.gaierror, socket.error):
                return False
        
        mx_exists = await loop.run_in_executor(None, _check_mx)
        if not mx_exists:
            return {"valid": False, "reason": f"No MX/A records found for domain: {domain}"}
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
    Sends an outreach email. Passes through the AI proofreading gate first
    unless skip_proofread is True.
    """
    api_key = os.getenv("AGENTMAIL_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "AGENTMAIL_API_KEY is not set. "
            "Add it to your Render environment variables or .env file."
        )

    client, error = _get_client()
    if not client:
         raise EnvironmentError(f"AgentMail client failed to initialize: {error}")

    # Validate email format before sending
    if not _validate_email(to):
        logger.warning(f"[AgentMail] Invalid email format: {to}. Skipping send.")
        return {"status": "error", "error": f"Invalid email format: {to}"}

    # Deep verification: MX record check + disposable domain block
    verify_result = await _verify_email_deliverable(to)
    if not verify_result["valid"]:
        logger.warning(f"[AgentMail] Email verification failed for {to}: {verify_result['reason']}")
        return {"status": "error", "error": f"Email not deliverable: {verify_result['reason']}"}

    # Use Nova's default inbox
    sender = _get_nova_inbox()
    if not sender:
        raise ValueError("No Nova inbox available. Create one first with create_inbox.")

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
                _send_telegram_alert(alert_msg)
                
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
        # Send using AgentMail client synchronous call wrapped inside run_in_executor in caller,
        # but since we are async, we run in executor directly here.
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
            # Also update client quotas if needed
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
        raise


def _get_last_reply_check():
    """Read last-processed reply timestamp from state_store via sync SQLite."""
    try:
        import sqlite3
        from app.core.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT value FROM state_store WHERE key = 'last_reply_check_at'"
            ).fetchone()
            if row and row["value"]:
                return datetime.fromisoformat(row["value"])
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Could not read last_reply_check_at: {e}")
    return None


def _set_last_reply_check(ts: datetime) -> None:
    """Persist last-processed reply timestamp to state_store."""
    try:
        import sqlite3
        from app.core.database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO state_store (key, value, updated_at) "
                "VALUES ('last_reply_check_at', ?, CURRENT_TIMESTAMP)",
                (ts.isoformat(),),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.warning(f"Could not persist last_reply_check_at: {e}")


def check_replies(inbox_id: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    Check Nova's inbox for new INBOUND messages since last check.

    Fixes two bugs from the previous version:
    1. No labels filter meant SENT messages could show up as 'replies'.
       Now filtered to labels=["INBOX"].
    2. No checkpoint meant the same messages re-alerted every 5min cycle.
       Now tracks last_reply_check_at in state_store.
    """
    client, error = _get_client()
    if not client:
        return {"status": "error", "message": f"AgentMail client not initialized: {error}"}

    inbox = inbox_id or _get_nova_inbox()
    if not inbox:
        return {"status": "error", "message": "No inbox available."}

    last_checked = _get_last_reply_check()
    now = datetime.utcnow()

    # First run: set checkpoint, return empty — don't alert on backlog
    if last_checked is None:
        _set_last_reply_check(now)
        logger.info("[AgentMail] First check — checkpoint set, no backlog alert.")
        return {"status": "success", "inbox": inbox, "count": 0, "messages": []}

    try:
        result = client.inboxes.messages.list(
            inbox_id=inbox,
            limit=limit,
            labels=["INBOX"],
            after=last_checked,
        )
        messages = []
        if hasattr(result, 'messages') and result.messages:
            for msg in result.messages[:limit]:
                messages.append({
                    "message_id": getattr(msg, 'message_id', 'unknown'),
                    "from": getattr(msg, 'from_', getattr(msg, 'sender', 'unknown')),
                    "subject": getattr(msg, 'subject', 'No subject'),
                    "snippet": str(getattr(msg, 'text', getattr(msg, 'snippet', '')))[:200],
                    "date": str(getattr(msg, 'created_at', ''))
                })

        # Advance checkpoint on success only
        _set_last_reply_check(now)

        return {
            "status": "success",
            "inbox": inbox,
            "count": len(messages),
            "messages": messages,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def reply_to_email(message_id: str, body: str, inbox_id: str = None) -> Dict[str, Any]:
    """Reply to a specific email in Nova's inbox."""
    client, error = _get_client()
    if not client:
        return {"status": "error", "message": f"AgentMail client not initialized: {error}"}

    inbox = inbox_id or _get_nova_inbox()
    if not inbox:
        return {"status": "error", "message": "No inbox available."}

    try:
        result = client.inboxes.messages.reply(
            inbox_id=inbox,
            message_id=message_id,
            text=body
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
    raw_inbox = check_replies(inbox_id, limit)
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
