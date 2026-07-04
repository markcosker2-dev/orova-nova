"""Approval gate for Nova's autonomous outbound (WP4).

Enforces the automation_policy from business_context.json: cold email and cold
calls require Mark's approval *for now*, until the AI is proven — at which point
Mark flips an env flag to enable autopilot. Ad spend / signing are gated
elsewhere (they never run autonomously).

How it works with the periodic worker lanes: when a send is gated and not yet
approved, we request approval (a single deduped Telegram ping) and skip THIS
cycle. Mark approves via Telegram; the next lane pass finds the approval and
sends. `request_firewall_approval` dedupes by action hash, so lanes never spam.
"""
import os
import logging

from app.skills.approval_workflow import is_action_approved, request_firewall_approval

logger = logging.getLogger(__name__)


def autopilot_enabled(kind: str) -> bool:
    """True if `kind` may send with no approval. Default OFF (approval required)."""
    if kind == "email":
        return os.getenv("OUTREACH_AUTOPILOT", "0") == "1"
    if kind == "call":
        return os.getenv("CALLS_AUTOPILOT", "0") == "1"
    if kind == "reply":
        # Auto-replying to a warm inbound (e.g. a booking-link reply to a HOT
        # lead) is lower risk than cold outreach, so it has its own flag —
        # Mark can enable fast reply autopilot while still approving cold sends.
        return os.getenv("REPLIES_AUTOPILOT", "0") == "1"
    return False


async def gate_allows(kind: str, params: dict, reason: str) -> bool:
    """Return True if an autonomous email/call may go out right now.

    - Autopilot on for this kind -> always True.
    - Otherwise True only if Mark has already approved this exact action
      (single-use); else request approval (deduped) and return False so the
      caller skips the send this cycle.

    `params` must be STABLE per lead+action (e.g. {"lead_id": .., "to": ..}) so
    the action hash matches across lane cycles and the approval targets it.
    """
    if autopilot_enabled(kind):
        return True
    tool = f"auto_{kind}"
    try:
        if await is_action_approved(tool, params):
            logger.info(f"[GATE] {kind} approved for {params} — sending.")
            return True
        await request_firewall_approval(tool, params, reason)
        logger.info(f"[GATE] {kind} awaiting approval for {params} — skipped this cycle.")
        return False
    except Exception as e:
        # Fail CLOSED: if the approval system errors, do NOT send unsupervised.
        logger.error(f"[GATE] approval check failed for {kind} ({e}) — skipping send.")
        return False
