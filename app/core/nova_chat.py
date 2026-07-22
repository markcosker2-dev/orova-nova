"""Nova conversational chat — the lean, human-sounding Telegram brain.

Replaces the 24-tool agentic planner (+ semantic firewall + self-learning)
for free-form Telegram messages. Mark wanted Nova to "speak like a regular
human" and keep him posted — not run an autonomous tool-loop. So this is
deliberately simple: gather a compact snapshot of the live pipeline, hand it
to one AI call with a warm persona, return the reply. No tool execution, so
no injection surface and no tool-loop memory blow-up.

Proactive email/reply notifications are handled separately by the reply lane
(worker.reply_and_drip_check_job → send_telegram_report), which already pings
Mark on every new reply.
"""
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

NOVA_PERSONA = (
    "You are Nova, Mark's AI partner at OROVA. OROVA is an autonomous sales rep that finds "
    "luxury / exotic-car dealers, researches the real decision maker, and books meetings for Mark.\n\n"
    "Talk to Mark like a sharp, friendly human colleague — warm, plain-spoken, and brief. "
    "No corporate filler, no buzzwords, no emoji spam (one is fine). Get to the point.\n\n"
    "When he asks about the pipeline, replies, or numbers, answer ONLY from the LIVE SNAPSHOT "
    "below. Never invent leads, owners, emails, phone numbers, or metrics — if the snapshot "
    "doesn't have it, say so plainly and, if useful, tell him how to get it (e.g. run a hunt). "
    "Keep answers short unless he asks for detail."
)


async def _pipeline_snapshot() -> str:
    """Compact live-data block injected into the system prompt. Fail-open:
    any piece that can't be fetched is simply omitted."""
    from app.core.database import DatabaseManager
    parts: List[str] = []

    try:
        m = await DatabaseManager.aget_metrics(0)
        parts.append(
            "METRICS today — leads: {leads}, emails sent: {sent}, replies: {rep}, "
            "meetings booked: {mtg}".format(
                leads=m.get("leads_found", 0), sent=m.get("emails_sent", 0),
                rep=m.get("replies_received", 0), mtg=m.get("meetings_booked", 0)))
    except Exception as e:
        logger.debug(f"[NOVA_CHAT] metrics fetch failed: {e}")

    try:
        rows = await DatabaseManager.query(
            "SELECT business, owner, owner_title, status, score, phone, email "
            "FROM leads WHERE COALESCE(status,'') != 'Invalid' "
            "ORDER BY score DESC LIMIT 8", (), fetchall=True)
        if rows:
            lines = ["TOP LEADS (business | decision maker | status | score):"]
            for r in rows:
                r = dict(r)
                dm = r.get("owner") or "—"
                if r.get("owner_title"):
                    dm += f" ({r['owner_title']})"
                lines.append(f"  - {r.get('business','?')} | {dm} | "
                             f"{r.get('status','New')} | {int(r.get('score') or 0)}")
            parts.append("\n".join(lines))
        else:
            parts.append("TOP LEADS: pipeline is empty — no leads yet.")
    except Exception as e:
        logger.debug(f"[NOVA_CHAT] leads fetch failed: {e}")

    try:
        pend = await DatabaseManager.query(
            "SELECT COUNT(*) AS n FROM leads WHERE status = 'Awaiting Approval'",
            (), fetchall=True)
        n = dict(pend[0]).get("n", 0) if pend else 0
        if n:
            parts.append(f"APPROVALS: {n} outbound message(s) waiting for your approval.")
    except Exception as e:
        logger.debug(f"[NOVA_CHAT] approvals fetch failed: {e}")

    return "\n\n".join(parts) if parts else "LIVE SNAPSHOT: unavailable right now."


async def nova_reply(message: str, chat_id: int = 0,
                     history: Optional[List[Dict]] = None) -> str:
    """One warm, grounded conversational turn. No tools, no agentic loop."""
    from app.core.ai_client import UnifiedAIClient
    try:
        snapshot = await _pipeline_snapshot()
        system = f"{NOVA_PERSONA}\n\n=== LIVE SNAPSHOT ===\n{snapshot}\n====================="

        messages = [{"role": "system", "content": system}]
        if history:
            # keep only the last few user/assistant turns, text only
            for h in history[-6:]:
                role = h.get("role")
                content = h.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        ai = UnifiedAIClient()
        resp = await ai.chat(messages, role="default", temperature=0.6, max_tokens=600)
        text = (getattr(resp, "content", "") or "").strip()
        if text and not text.startswith("[!!]"):
            return text
        logger.warning(f"[NOVA_CHAT] provider returned no usable text: {text[:80]}")
        return ("I'm having trouble reaching my AI providers this second (usually a free-tier "
                "rate limit). Try me again in a minute — everything else is still running.")
    except Exception as e:
        logger.error(f"[NOVA_CHAT] reply failed: {e}", exc_info=True)
        return "Something went wrong on my end just now — give me a moment and try again."
