import asyncio
import os
import re
import logging
import uuid
import httpx
from typing import Optional, Union
from app.core.hardening import rate_limiter, tracer, RequestSanitizer, operator_chat_allowed
from app.core.guardrails import Guardrails
from app.core.identity import IDENTITY_PROBE_RE as _IDENTITY_PROBE_RE, IDENTITY_DEFLECT as _IDENTITY_DEFLECT

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)


def _command_text(message: str) -> str:
    return re.sub(r"^(/[a-z_]+)@[a-z0-9_]+(?=\s|$)", r"\1", message.strip().lower())


def bounded_chat_history(history) -> list:
    """Keep only bounded text turns, including restored or caller-supplied state."""
    if not isinstance(history, list):
        return []
    turns = []
    for turn in history:
        if (isinstance(turn, dict) and turn.get("role") in ("user", "assistant")
                and isinstance(turn.get("content"), str)):
            content = RequestSanitizer.sanitize_string(
                turn["content"], max_len=5000 if turn["role"] == "user" else 3000)
            if turn["role"] == "user":
                content = Guardrails.sanitize_input(content)[:5000]
            turns.append({"role": turn["role"], "content": content})
    return turns[-12:]


class Router:
    def __init__(self, lead_hunter=None):
        self.lead_hunter = lead_hunter
        self.shortcuts = {
            r"/reset": self._reset_instruction,
            r"/help": self._show_help,
            r"/start": self._show_help,
            r"/leads": self._leads_handler,
            r"/contact\s+(\d+)": self._contact_handler,
            r"/approve_pruning": self._approve_pruning_handler,
            r"/status": self._status_handler,
            r"/cancel\s+(\S+)": self._cancel_handler,
        }

    async def route(self, message: str, chat_id: int, history: list = None, agent_id: str = "nova") -> Union[str, dict]:
        # chat_id=0 is the separately authenticated dashboard, not Telegram.
        if chat_id != 0 and not operator_chat_allowed(chat_id):
            return "Admin access required."
        # [P4] Hardening: Generate request ID for tracing
        request_id = str(uuid.uuid4())[:8]
        client_id_str = f"tg_{chat_id}"
        
        # [P4] Rate limiting check
        if not rate_limiter.is_allowed(client_id_str):
            retry_after = rate_limiter.get_retry_after(client_id_str)
            logger.warning(f"[Router] Rate limit exceeded for {client_id_str}. Retry after {retry_after:.1f}s")
            tracer.trace(request_id, "rate_limit_exceeded", {"client_id": chat_id, "retry_after": retry_after})
            return {"error": "Rate limit exceeded. Please try again later.", "retry_after": retry_after}
        
        # [P4] Sanitize input
        message = RequestSanitizer.sanitize_string(message, max_len=5000).strip()
        # Also run the prompt-injection guardrail
        message = Guardrails.sanitize_input(message)[:5000]
        if not message:
            logger.warning(f"[Router] Empty/invalid message from {chat_id}")
            return "Your message appears to be empty or was rejected by safety guardrails. Please try again."
        
        tracer.trace(request_id, "route_start", {"client_id": chat_id, "agent_id": agent_id, "msg_len": len(message)})
        
        lower_msg = _command_text(message)
        aliases = {"status": "/status", "leads": "/leads", "show leads": "/leads",
                   "show me the leads": "/leads", "help": "/help"}
        lower_msg = aliases.get(lower_msg, lower_msg)

        if _IDENTITY_PROBE_RE.search(lower_msg):
            logger.info(f"[Router] {request_id} Identity probe intercepted")
            tracer.trace(request_id, "identity_probe")
            return _IDENTITY_DEFLECT

        # Operator access was checked before reading state or matching shortcuts.
        for pattern, handler in self.shortcuts.items():
            m = re.fullmatch(pattern, lower_msg)
            if m:
                groups = m.groups()
                logger.info(f"[Router] {request_id} Shortcut matched '{pattern}'")
                tracer.trace(request_id, "shortcut_matched", {"pattern": pattern})
                return await handler(*groups) if groups else await handler()

        if lower_msg.startswith("/"):
            return "Unknown command or missing argument. " + await self._show_help()
        if re.match(r"(?:please\s+)?(?:find|hunt|send|email|call|contact|message|book)\b", lower_msg):
            return ("I haven't taken any action. Use /leads, then /contact ID for a sourced contact card "
                    "and a draft. New hunts run from Mission Control. I can't send DMs or place calls from chat.")

        # Free-form message → lean conversational Nova (human tone, grounded
        # in the live pipeline snapshot). No agentic tool-loop. Outbound
        # actions stay with the deterministic shortcuts + approval gate.
        tracer.trace(request_id, "nova_chat", {"message_preview": message[:100]})
        from app.core.nova_chat import nova_reply
        result = await nova_reply(message, chat_id=chat_id, history=history)
        tracer.trace(request_id, "route_complete", {"result_type": type(result).__name__})
        return result

    async def _reset_instruction(self):
        return "Use /forget to clear this chat's recent context. Leads and business records are kept."

    async def _status_handler(self):
        """Handle /status command - return quick pipeline status."""
        from app.core.nova_chat import pipeline_status
        return await pipeline_status()

    async def _leads_handler(self):
        from app.core.nova_chat import lead_contact_cards
        return await lead_contact_cards()

    async def _contact_handler(self, lead_id):
        from app.core.nova_chat import lead_contact_cards
        return await lead_contact_cards(int(lead_id))

    async def _cancel_handler(self, task_id: str = None):
        """Handle /cancel {task_id} command - cancel pending auto-execution."""
        if not task_id:
            return "❌ Usage: /cancel {task_id}"
        from app.core.ceo_brain import CEOBrain
        brain = CEOBrain()
        cancelled = await brain.cancel_auto_execute(task_id)
        if cancelled:
            return f"✅ Cancelled task `{task_id}`"
        return f"❌ Task `{task_id}` not found or already executing."

    async def _approve_pruning_handler(self):
        from app.core.database import DatabaseManager
        from app.skills.email_sequence_skill import update_sheets_lead_status
        lead_ids = await DatabaseManager.get_state("pending_prune_lead_ids")
        if not lead_ids:
            return "No pending stale leads to prune."
            
        try:
            # Fetch lead details first so we can update Sheets
            placeholders = ",".join("?" for _ in lead_ids)
            leads = await DatabaseManager.fetchall(
                # noqa-safe: `placeholders` is "?,?,?" generated from a count.
                f"SELECT business FROM leads WHERE id IN ({placeholders})",  # noqa: S608
                tuple(lead_ids)
            )
            
            # Update status in DB
            await DatabaseManager.query(
                # noqa-safe: `placeholders` is "?,?,?" generated from a count.
                f"UPDATE leads SET status = 'Archived', updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",  # noqa: S608
                tuple(lead_ids)
            )
            
            # Clear state
            await DatabaseManager.set_state("pending_prune_lead_ids", None)
            
            # Async background update of Google Sheets
            for lead in leads:
                asyncio.create_task(update_sheets_lead_status(lead["business"], "Archived"))
                
            return f"✅ Approved! Archived {len(lead_ids)} stale leads in the database and CRM."
        except Exception as e:
            logger.error(f"Error executing pruning: {e}")
            return f"❌ Error executing pruning: {e}"

    async def _greet(self):
        return "👋 I'm Nova, your OROVA AI. Ready to work."

    async def _health_check(self):
        return "✅ System Status: ONLINE"

    async def _show_help(self):
        return ("/status — actual pipeline counts and blockers\n"
                "/leads — five uncontacted prospects\n"
                "/contact ID — recorded contact details and a manual first-message draft\n"
                "/forget — clear recent chat context only\n"
                "Chat answers questions; it does not execute outreach. No paid calls or automatic cold outreach in $0 mode.")

    async def _confirm_presence(self):
        return "Yes, Boss. I am here."

    async def handle_message(self, message: str, chat_id: int, history: list = None) -> str:
        from app.core.database import DatabaseManager
        if chat_id != 0 and not operator_chat_allowed(chat_id):
            return "Admin access required."
        message = RequestSanitizer.sanitize_string(message, max_len=5000).strip()
        message = Guardrails.sanitize_input(message)[:5000]
        key = f"nova_chat:{chat_id}"
        if _command_text(message) == "/forget":
            try:
                await DatabaseManager.set_state(key, [])
            except Exception:
                logger.warning("[Router] Could not clear recent chat context")
                return "I couldn't clear recent chat context. Please try /forget again."
            return "Recent chat context cleared. Your leads and business records are unchanged."
        if history is None:
            try:
                history = await DatabaseManager.get_state(key, [])
            except Exception:
                logger.warning("[Router] Recent chat context unavailable")
                history = []
        history = bounded_chat_history(history)[-10:]
        result = await self.route(message, chat_id, history)
        if isinstance(result, dict):
            result = result.get("error") or result.get("response") or "No action was completed."
        result = result if isinstance(result, str) and result else "No action was completed."
        try:
            await DatabaseManager.set_state(key, (history + [
                {"role": "user", "content": message[:5000]},
                {"role": "assistant", "content": result[:3000]},
            ])[-12:])
        except Exception:
            logger.warning("[Router] Could not retain recent chat context")
        return result

    async def _send_telegram(self, chat_id: int, text: str, parse_mode: Optional[str] = None) -> bool:
        """Send a Telegram message with one retry on failure."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("[Router] Cannot send Telegram: TELEGRAM_BOT_TOKEN missing")
            return False
        for attempt in range(2):
            try:
                payload = {"chat_id": chat_id, "text": text[:4096]}
                if parse_mode:
                    payload["parse_mode"] = parse_mode
                async with httpx.AsyncClient(timeout=15) as client:
                    res = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=payload,
                    )
                if res.status_code == 200:
                    return True
                logger.error(f"[Router] Telegram send failed (attempt {attempt+1}): {res.status_code} {res.text}")
            except Exception as e:
                logger.error(f"[Router] Telegram send exception (attempt {attempt+1}): {e}")
            await asyncio.sleep(1)
        return False
