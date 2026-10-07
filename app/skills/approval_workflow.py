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

Approvals expire 24h after creation and cannot be reopened once resolved.
State failures keep actions blocked; request failures are surfaced to the
existing gate callers. Telegram delivery remains best-effort.
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
import time

import httpx

logger = logging.getLogger(__name__)

_STATE_KEY = "pending_approvals"
_APPROVAL_TTL_S = 24 * 3600
_pending_approvals = {}
_approval_counter = 0
_loaded_from_db = False
_load_lock = threading.Lock()


def _action_hash(tool_name: str, params: dict) -> str:
    canonical = json.dumps({"tool": tool_name, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _request_is_current(request: dict, now: float) -> bool:
    """A request has one 24-hour lifetime, measured from its creation."""
    try:
        return 0 <= now - float(request["created_at"]) < _APPROVAL_TTL_S
    except (KeyError, TypeError, ValueError):
        return False


async def _load_state() -> bool:
    """Lazy-load persisted approvals once per process (Render restarts)."""
    global _pending_approvals, _approval_counter, _loaded_from_db
    if _loaded_from_db:
        return True
    # A thread lock has no event-loop affinity. Nonblocking acquisition keeps
    # the loop responsive and cannot leak a later executor acquisition when a
    # waiting coroutine is cancelled.
    while not _load_lock.acquire(blocking=False):
        await asyncio.sleep(0.01)
    try:
        if _loaded_from_db:
            return True
        from app.core.database import DatabaseManager
        saved = await DatabaseManager.get_state(_STATE_KEY, {})
        if not isinstance(saved, dict):
            logger.warning("[APPROVAL] Invalid approval state; actions remain blocked")
            return False
        # Retain terminal/expired IDs so a delayed Telegram reply cannot
        # approve a different action after an ID is recycled on restart.
        _pending_approvals = {
            k: v for k, v in saved.items()
            if isinstance(k, str) and isinstance(v, dict)
        }
        nums = [int(k.removeprefix("APPROVAL-")) for k in saved
                if isinstance(k, str) and k.startswith("APPROVAL-")
                and k.removeprefix("APPROVAL-").isdigit()]
        _approval_counter = max(nums) if nums else 0
        _loaded_from_db = True
        logger.info(f"[APPROVAL] Restored {len(_pending_approvals)} request(s) from DB")
        return True
    except Exception as e:
        logger.warning(f"[APPROVAL] Could not restore state: {e}")
        return False
    finally:
        _load_lock.release()


async def _persist_state() -> bool:
    try:
        from app.core.database import DatabaseManager
        await DatabaseManager.set_state(_STATE_KEY, _pending_approvals)
        return True
    except Exception as e:
        logger.warning(f"[APPROVAL] Could not persist state: {e}")
        return False


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
    if not await _load_state():
        return "[APPROVAL BLOCKED] Could not load approval records. Try again."
    _approval_counter += 1
    request_id = f"APPROVAL-{_approval_counter:04d}"

    _pending_approvals[request_id] = {
        "action": action,
        "details": details,
        "status": "pending",
        "created_at": time.time(),
        "resolved_at": None,
    }
    if not await _persist_state():
        _pending_approvals.pop(request_id, None)
        return "[APPROVAL BLOCKED] Could not persist the request. Try again."
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
    if not await _load_state():
        raise RuntimeError("Approval records unavailable; action remains blocked")
    ahash = _action_hash(tool_name, params)

    # Reuse an existing pending request for the same action
    now = time.time()
    for rid, req in _pending_approvals.items():
        if (req.get("action_hash") == ahash and req.get("status") == "pending"
                and _request_is_current(req, now)):
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
    if not await _persist_state():
        _pending_approvals.pop(request_id, None)
        raise RuntimeError("Could not persist approval request; action remains blocked")

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
    if not await _load_state():
        return False
    ahash = _action_hash(tool_name, params)
    now = time.time()
    for rid, req in _pending_approvals.items():
        try:
            resolved_age = now - float(req.get("resolved_at") or 0)
        except (TypeError, ValueError):
            continue
        if (
            req.get("action_hash") == ahash
            and req.get("status") == "approved"
            and _request_is_current(req, now)
            and 0 <= resolved_age < _APPROVAL_TTL_S
        ):
            req["status"] = "consumed"
            if not await _persist_state():
                return False
            logger.info(f"[APPROVAL] {rid} consumed for {tool_name}")
            return True
    return False


async def check_approval(request_id: str) -> str:
    """Check the status of an approval request."""
    if not await _load_state():
        return "Approval records unavailable; actions remain blocked. Try again."
    if request_id not in _pending_approvals:
        return f"No approval request found with ID: {request_id}"

    req = _pending_approvals[request_id]
    if not _request_is_current(req, time.time()):
        return f"Approval {request_id} is EXPIRED. Request fresh approval for this action."
    status = req["status"]
    age = int(time.time() - float(req["created_at"]))

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
    text = text.strip().lower()

    if not text.startswith(("approve ", "reject ")):
        return None
    if not await _load_state():
        return "Could not load approval records; the action remains blocked. Try again."
    verb, request_id = text.split(maxsplit=1)
    request_id = request_id.strip().upper()
    req = _pending_approvals.get(request_id)
    now = time.time()
    if not req or req.get("status") != "pending":
        return f"No pending request: {request_id}"
    if not _request_is_current(req, now):
        return f"Approval {request_id} is EXPIRED. Request fresh approval for this action."

    previous = req.copy()
    req["status"] = "approved" if verb == "approve" else "rejected"
    req["resolved_at"] = now
    if not await _persist_state():
        req.update(previous)
        return f"Could not record the response for {request_id}; the action remains blocked. Try again."
    action = req["action"]
    if verb == "approve":
        logger.info(f"[APPROVAL] {request_id} APPROVED by Mark")
        return f"APPROVED: {request_id} - '{action}'. Awaiting execution through its action gates."
    logger.info(f"[APPROVAL] {request_id} REJECTED by Mark")
    return f"REJECTED: {request_id} - '{action}'. Standing down."


async def list_pending() -> str:
    """List all pending approval requests."""
    if not await _load_state():
        return "Approval records unavailable; actions remain blocked. Try again."
    now = time.time()
    pending = {k: v for k, v in _pending_approvals.items()
               if v.get("status") == "pending" and _request_is_current(v, now)}

    if not pending:
        return "No pending approvals. All clear."

    result = f"# Pending Approvals ({len(pending)})\n\n"
    for req_id, req in pending.items():
        age = int(time.time() - float(req["created_at"]))
        result += f"- **{req_id}**: {req['action']} ({age}s ago)\n"
        result += f"  Details: {req['details']}\n\n"

    return result
