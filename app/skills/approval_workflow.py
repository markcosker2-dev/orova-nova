import logging
import asyncio
import json
import time
import os

logger = logging.getLogger(__name__)

# In-memory approval queue (persists during runtime)
_pending_approvals = {}
_approval_counter = 0


async def request_approval(action: str, details: str) -> str:
    """
    Request Mark's approval before executing a critical action.
    Returns a message that Nova should send to Mark via Telegram.
    
    The approval request is stored so it can be checked later.
    """
    global _approval_counter
    _approval_counter += 1
    request_id = f"APPROVAL-{_approval_counter:04d}"

    _pending_approvals[request_id] = {
        "action": action,
        "details": details,
        "status": "pending",
        "created_at": time.time(),
        "resolved_at": None,
    }

    logger.info(f"[APPROVAL] Created {request_id}: {action}")

    # Format the approval request as a Telegram message
    message = (
        f"[APPROVAL NEEDED] #{request_id}\n"
        f"---\n"
        f"Action: {action}\n"
        f"Details: {details}\n"
        f"---\n"
        f"Reply 'approve {request_id}' or 'reject {request_id}'"
    )

    return message


async def check_approval(request_id: str) -> str:
    """
    Check the status of an approval request.
    """
    if request_id not in _pending_approvals:
        return f"No approval request found with ID: {request_id}"

    req = _pending_approvals[request_id]
    status = req["status"]
    age = int(time.time() - req["created_at"])

    if status == "pending":
        return f"Approval {request_id} is still PENDING ({age}s ago). Waiting for Mark's response."
    elif status == "approved":
        return f"Approval {request_id} was APPROVED. Proceed with: {req['action']}"
    elif status == "rejected":
        return f"Approval {request_id} was REJECTED. Do not proceed."
    else:
        return f"Approval {request_id} status: {status}"


async def handle_approval_response(text: str) -> str:
    """
    Process Mark's approval/rejection response from Telegram.
    Called when a message matches 'approve APPROVAL-XXXX' or 'reject APPROVAL-XXXX'.
    Returns confirmation message.
    """
    text = text.strip().lower()

    if text.startswith("approve "):
        request_id = text.replace("approve ", "").strip().upper()
        if request_id in _pending_approvals:
            _pending_approvals[request_id]["status"] = "approved"
            _pending_approvals[request_id]["resolved_at"] = time.time()
            action = _pending_approvals[request_id]["action"]
            logger.info(f"[APPROVAL] {request_id} APPROVED by Mark")
            return f"APPROVED: {request_id} - '{action}'. Proceeding."
        return f"No pending request: {request_id}"

    elif text.startswith("reject "):
        request_id = text.replace("reject ", "").strip().upper()
        if request_id in _pending_approvals:
            _pending_approvals[request_id]["status"] = "rejected"
            _pending_approvals[request_id]["resolved_at"] = time.time()
            action = _pending_approvals[request_id]["action"]
            logger.info(f"[APPROVAL] {request_id} REJECTED by Mark")
            return f"REJECTED: {request_id} - '{action}'. Standing down."
        return f"No pending request: {request_id}"

    return None  # Not an approval response


async def list_pending() -> str:
    """List all pending approval requests."""
    pending = {k: v for k, v in _pending_approvals.items() if v["status"] == "pending"}

    if not pending:
        return "No pending approvals. All clear."

    result = f"# Pending Approvals ({len(pending)})\n\n"
    for req_id, req in pending.items():
        age = int(time.time() - req["created_at"])
        result += f"- **{req_id}**: {req['action']} ({age}s ago)\n"
        result += f"  Details: {req['details']}\n\n"

    return result


def get_all_pending_approvals():
    """
    Get all pending approvals including workflow, calls, and emails for API.
    Returns unified list with standardized fields.
    """
    approvals = []
    
    # Add workflow approvals
    for req_id, req in _pending_approvals.items():
        if req["status"] == "pending":
            approvals.append({
                "id": req_id,
                "type": "workflow",
                "action": req["action"],
                "details": req["details"],
                "created_at": req["created_at"],
                "age_seconds": int(time.time() - req["created_at"])
            })
    
    # Add pending calls
    from app.main import pending_calls
    for call_id, call in pending_calls.items():
        approvals.append({
            "id": call_id,
            "type": "call",
            "action": f"Initiate call to {call.get('name', 'Unknown')}",
            "details": f"Phone: {call.get('phone', 'Unknown')}\nScript: {call.get('script', '')}",
            "created_at": call.get("_ts", time.time()),
            "age_seconds": int(time.time() - call.get("_ts", time.time()))
        })
    
    # Add pending emails
    from app.main import pending_emails
    for draft_id, draft in pending_emails.items():
        approvals.append({
            "id": draft_id,
            "type": "email",
            "action": f"Send email to {draft.get('company', 'Unknown')}",
            "details": f"To: {draft.get('to', 'Unknown')}\nSubject: {draft.get('subject', '')}\nPreview: {draft.get('body', '')[:200]}",
            "created_at": draft.get("_ts", time.time()),
            "age_seconds": int(time.time() - draft.get("_ts", time.time()))
        })
    
    return approvals


def approve_item(item_id: str) -> dict:
    """Approve an item by ID (handles all types: workflow, call, email)."""
    # Check workflow approvals first
    if item_id in _pending_approvals and _pending_approvals[item_id]["status"] == "pending":
        _pending_approvals[item_id]["status"] = "approved"
        _pending_approvals[item_id]["resolved_at"] = time.time()
        logger.info(f"[APPROVAL] {item_id} APPROVED via API")
        return {"status": "ok", "message": f"Approved {item_id}", "type": "workflow"}
    
    # Check pending calls
    from app.main import pending_calls
    if item_id in pending_calls:
        call = pending_calls[item_id]
        from app.services.call_manager import execute_call
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            retell_id = loop.run_until_complete(execute_call(call['phone'], call['name'], call['script']))
            del pending_calls[item_id]
            logger.info(f"[APPROVAL] Call {item_id} APPROVED via API, started with ID {retell_id}")
            return {"status": "ok", "message": f"Call initiated to {call['name']}", "type": "call", "retell_id": retell_id}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    # Check pending emails
    from app.main import pending_emails
    if item_id in pending_emails:
        draft = pending_emails[item_id]
        from app.skills.agentmail_skill import send_outreach
        try:
            result = send_outreach(to=draft["to"], subject=draft["subject"], body=draft["body"])
            if result.get("status") == "sent":
                del pending_emails[item_id]
                logger.info(f"[APPROVAL] Email {item_id} APPROVED via API, sent to {draft['to']}")
                return {"status": "ok", "message": f"Email sent to {draft['to']}", "type": "email"}
            else:
                return {"status": "error", "error": result.get("message", "Send failed")}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    return {"status": "error", "error": "Item not found or already resolved", "code": 404}


def deny_item(item_id: str) -> dict:
    """Deny an item by ID (handles all types: workflow, call, email)."""
    # Check workflow approvals first
    if item_id in _pending_approvals and _pending_approvals[item_id]["status"] == "pending":
        _pending_approvals[item_id]["status"] = "rejected"
        _pending_approvals[item_id]["resolved_at"] = time.time()
        logger.info(f"[APPROVAL] {item_id} REJECTED via API")
        return {"status": "ok", "message": f"Denied {item_id}", "type": "workflow"}
    
    # Check pending calls
    from app.main import pending_calls
    if item_id in pending_calls:
        del pending_calls[item_id]
        logger.info(f"[APPROVAL] Call {item_id} DENIED via API")
        return {"status": "ok", "message": "Call cancelled", "type": "call"}
    
    # Check pending emails
    from app.main import pending_emails
    if item_id in pending_emails:
        del pending_emails[item_id]
        logger.info(f"[APPROVAL] Email {item_id} DENIED via API")
        return {"status": "ok", "message": "Email draft discarded", "type": "email"}
    
    return {"status": "error", "error": "Item not found or already resolved", "code": 404}
