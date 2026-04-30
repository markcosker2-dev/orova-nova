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
