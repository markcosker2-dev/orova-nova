"""
Approval Workflow — Human-in-the-Loop via Telegram
==================================================
Closes the loop between the Semantic Firewall's REQUIRE_HUMAN_APPROVAL
decision and Mark's Telegram:

  1. Firewall flags a destructive/high-impact tool call.
  2. request_firewall_approval() persists the request (survives Render
     restarts via the state_store) and pings Mark on Telegram.
  3. Mark replies "approve APPROVAL-XXXX" or "reject APPROVAL-XXXX"
     (handled by handle_approval_response from the webhook).
  4. When Nova retries the same action, firewall_guard calls
     is_action_approved() — a matching approval is consumed (single-use)
     and the action executes.

Approvals expire after 24h. Everything is best-effort: DB or Telegram
failures never crash the caller, they just leave the action blocked.
"""

import hashlib
import json
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

_STATE_KEY = "pending_approvals"
_APPROVAL_TTL_S = 24 * 3600
_pending_approvals = {}
_approval_counter = 0
_loaded_from_db = False


def _action_hash(tool_name: str, params: dict) -> str:
    canonical = json.dumps({"tool": tool_name, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


async def _load_state():
    """Lazy-load persisted approvals once per process (Render restarts)."""
    global _pending_approvals, _approval_counter, _loaded_from_db
    if _loaded_from_db:
        return
    _loaded_from_db = True
    try:
        from app.core.database import DatabaseManager
        saved = await DatabaseManager.get_state(_STATE_KEY, {})
        if isinstance(saved, dict) and saved:
            now = time.time()
            _pending_approvals = {
                k: v for k, v in saved.items()
                if now - v.get("created_at", 0) < _APPROVAL_TTL_S
            }
            nums = [int(k.split("-")[-1]) for k in _pending_approvals if "-" in k]
            _approval_counter = max(nums) if nums else 0
            logger.info(f"[APPROVAL] Restored {len(_pending_approvals)} request(s) from DB")
    except Exception as e:
        logger.warning(f"[APPROVAL] Could not restore state: {e}")


async def _persist_state():
    try:
        from app.core.database import DatabaseManager
        await DatabaseManager.set_state(_STATE_KEY, _pending_approvals)
    except Exception as e:
        logger.warning(f"[APPROVAL] Could not persist state: {e}")


async def _send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    # Same chat-id convention as worker.send_telegram_report
    chat_id = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("[APPROVAL] Telegram not configured; approval request logged only")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": message},
            )
        return True
    except Exception as e:
        logger.error(f"[APPROVAL] Telegram send failed: {e}")
        return False


async def request_approval(action: str, details: str) -> str:
    """
    Request Mark's approval before executing a critical action.
    Returns a message that Nova should send to Mark via Telegram.
    """
    global _approval_counter
    await _load_state()
    _approval_counter += 1
    request_id = f"APPROVAL-{_approval_counter:04d}"

    _pending_approvals[request_id] = {
        "action": action,
        "details": details,
        "status": "pending",
        "created_at": time.time(),
        "resolved_at": None,
    }
    await _persist_state()
    logger.info(f"[APPROVAL] Created {request_id}: {action}")

    return (
        f"[APPROVAL NEEDED] #{request_id}\n"
        f"---\n"
        f"Action: {action}\n"
        f"Details: {details}\n"
        f"---\n"
        f"Reply 'approve {request_id}' or 'reject {request_id}'"
    )


async def request_firewall_approval(tool_name: str, params: dict, reason: str) -> str:
    """
    Firewall entry point: persist an approval request for a blocked
    high-impact tool call and ping Mark on Telegram. Deduplicates by action
    hash so retries don't spam. Returns the request id.
    """
    await _load_state()
    ahash = _action_hash(tool_name, params)

    # Reuse an existing pending request for the same action
    for rid, req in _pending_approvals.items():
        if req.get("action_hash") == ahash and req["status"] == "pending":
            return rid

    global _approval_counter
    _approval_counter += 1
    request_id = f"APPROVAL-{_approval_counter:04d}"
    _pending_approvals[request_id] = {
        "action": tool_name,
        "details": json.dumps(params, default=str)[:500],
        "action_hash": ahash,
        "status": "pending",
        "created_at": time.time(),
        "resolved_at": None,
    }
    await _persist_state()

    await _send_telegram(
        f"🛡️ FIREWALL: approval needed #{request_id}\n"
        f"Tool: {tool_name}\n"
        f"Params: {json.dumps(params, default=str)[:300]}\n"
        f"Reason: {reason[:200]}\n\n"
        f"Reply 'approve {request_id}' or 'reject {request_id}'"
    )
    logger.warning(f"[APPROVAL] Firewall approval requested: {request_id} for {tool_name}")
    return request_id


async def is_action_approved(tool_name: str, params: dict) -> bool:
    """
    True if a matching approval exists (by action hash, within TTL).
    Approvals are single-use: consumed on first successful check.
    """
    await _load_state()
    ahash = _action_hash(tool_name, params)
    now = time.time()
    for rid, req in _pending_approvals.items():
        if (
            req.get("action_hash") == ahash
            and req["status"] == "approved"
            and now - (req.get("resolved_at") or 0) < _APPROVAL_TTL_S
        ):
            req["status"] = "consumed"
            await _persist_state()
            logger.info(f"[APPROVAL] {rid} consumed for {tool_name}")
            return True
    return False


async def check_approval(request_id: str) -> str:
    """Check the status of an approval request."""
    await _load_state()
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
    return f"Approval {request_id} status: {status}"


async def handle_approval_response(text: str):
    """
    Process Mark's approval/rejection response from Telegram.
    Returns a confirmation message, or None if the text isn't an approval reply.
    """
    await _load_state()
    text = text.strip().lower()

    if text.startswith("approve "):
        request_id = text.replace("approve ", "").strip().upper()
        if request_id in _pending_approvals:
            _pending_approvals[request_id]["status"] = "approved"
            _pending_approvals[request_id]["resolved_at"] = time.time()
            await _persist_state()
            action = _pending_approvals[request_id]["action"]
            logger.info(f"[APPROVAL] {request_id} APPROVED by Mark")
            return f"APPROVED: {request_id} - '{action}'. Proceeding."
        return f"No pending request: {request_id}"

    elif text.startswith("reject "):
        request_id = text.replace("reject ", "").strip().upper()
        if request_id in _pending_approvals:
            _pending_approvals[request_id]["status"] = "rejected"
            _pending_approvals[request_id]["resolved_at"] = time.time()
            await _persist_state()
            action = _pending_approvals[request_id]["action"]
            logger.info(f"[APPROVAL] {request_id} REJECTED by Mark")
            return f"REJECTED: {request_id} - '{action}'. Standing down."
        return f"No pending request: {request_id}"

    return None  # Not an approval response


async def list_pending() -> str:
    """List all pending approval requests."""
    await _load_state()
    pending = {k: v for k, v in _pending_approvals.items() if v["status"] == "pending"}

    if not pending:
        return "No pending approvals. All clear."

    result = f"# Pending Approvals ({len(pending)})\n\n"
    for req_id, req in pending.items():
        age = int(time.time() - req["created_at"])
        result += f"- **{req_id}**: {req['action']} ({age}s ago)\n"
        result += f"  Details: {req['details']}\n\n"

    return result
