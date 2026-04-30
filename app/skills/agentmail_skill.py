"""
AgentMail Skill - Nova's Own Email System
==========================================
Nova gets her own email inbox via AgentMail API.
She can create inboxes, send outreach, check replies, and respond.
"""
import os
import logging
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────
_client = None
_nova_inbox_id = None  # Cached inbox address


def _get_client():
    """Lazy-init the AgentMail client."""
    global _client
    if _client is None:
        try:
            from agentmail import AgentMail
            api_key = os.getenv("AGENTMAIL_API_KEY")
            if not api_key:
                logger.error("AGENTMAIL_API_KEY not set")
                return None
            _client = AgentMail(api_key=api_key)
            logger.info("[+] AgentMail client initialized")
        except Exception as e:
            logger.error(f"AgentMail init failed: {e}")
            return None
    return _client


def _get_nova_inbox():
    """Get or create Nova's inbox. Returns inbox_id (email address)."""
    global _nova_inbox_id
    if _nova_inbox_id:
        return _nova_inbox_id

    client = _get_client()
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
    client = _get_client()
    if not client:
        return {"status": "error", "message": "AgentMail client not initialized. Check AGENTMAIL_API_KEY."}

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


def send_outreach(to: str, subject: str, body: str, inbox_id: str = None) -> Dict[str, Any]:
    """Send an email from Nova's inbox."""
    client = _get_client()
    if not client:
        return {"status": "error", "message": "AgentMail client not initialized."}

    # Use provided inbox or get Nova's default
    sender = inbox_id or _get_nova_inbox()
    if not sender:
        return {"status": "error", "message": "No inbox available. Create one first with create_inbox."}

    try:
        result = client.inboxes.messages.send(
            inbox_id=sender,
            to=to,
            subject=subject,
            text=body
        )
        logger.info(f"[+] Email sent to {to} from {sender}")
        return {
            "status": "success",
            "from": sender,
            "to": to,
            "subject": subject,
            "message": f"Email sent to {to}"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_replies(inbox_id: str = None, limit: int = 10) -> Dict[str, Any]:
    """Check Nova's inbox for new messages/replies."""
    client = _get_client()
    if not client:
        return {"status": "error", "message": "AgentMail client not initialized."}

    inbox = inbox_id or _get_nova_inbox()
    if not inbox:
        return {"status": "error", "message": "No inbox available."}

    try:
        result = client.inboxes.messages.list(inbox_id=inbox)
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

        return {
            "status": "success",
            "inbox": inbox,
            "count": len(messages),
            "messages": messages
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def reply_to_email(message_id: str, body: str, inbox_id: str = None) -> Dict[str, Any]:
    """Reply to a specific email in Nova's inbox."""
    client = _get_client()
    if not client:
        return {"status": "error", "message": "AgentMail client not initialized."}

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
