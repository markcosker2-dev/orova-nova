import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm) are you|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)|"
    r"who (made|built|created|trained) you|what powers you|underlying model|"
    r"what (are|is) (your|the) (model|ai|engine)|powered by)\b",
    re.IGNORECASE,
)
_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI partner. What can I do for you?"

class Router:
    def __init__(self, ai_planner, lead_hunter):
        self.planner = ai_planner
        self.lead_hunter = lead_hunter
        self.shortcuts = {r"/reset": self._reset_instruction}

    async def route(self, message: str, chat_id: int, history: list = None, agent_id: str = "nova") -> str | dict:
        message = message.strip()
        lower_msg = message.lower()

        if _IDENTITY_PROBE_RE.search(lower_msg):
            logger.info("[Router] Identity probe intercepted — returning persona deflect")
            return _IDENTITY_DEFLECT

        for pattern, handler in self.shortcuts.items():
            if re.search(pattern, lower_msg):
                logger.info(f"[Router] Shortcut matched '{pattern}'")
                return await handler()

        email_match = _EMAIL_RE.search(message)
        send_intent = any(k in lower_msg for k in ["send", "write", "email", "reach out", "follow up"])

        if email_match and send_intent:
            logger.info(f"[Router] Direct-send intercept → {email_match.group(0)}")
            return await self.planner.execute(
                message, client_id=chat_id, conversation_history=history, agent_id="nova", _already_intercepted=True
            )

        return await self.planner.execute(
            message, client_id=chat_id, conversation_history=history, agent_id=agent_id
        )

    async def _reset_instruction(self):
        return "Use the /reset command to wipe memory."

    async def _greet(self):
        return "👋 NOVA (CLOUD V2.3 — PATCHED). Ready, Mark."

    async def _health_check(self):
        return "✅ System Status: ONLINE"

    async def _show_help(self):
        return "🤖 Try: 'Find 10 leads for [niche]' or '/reset' to wipe memory."

    async def _confirm_presence(self):
        return "Yes, Boss. I am here."

    async def handle_message(self, message: str, chat_id: int, history: list = None) -> str:
        result = await self.route(message, chat_id, history)
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            return result.get("response", "Done.")
        return "Processed."

    async def _send_telegram(self, chat_id: int, text: str, parse_mode: Optional[str] = None) -> bool:
        try:
            from app.core.telegram_queue import telegram_queue
            await telegram_queue.add_message(chat_id, text, parse_mode=parse_mode)
            return True
        except Exception as e:
            logger.error(f"[Router] Telegram send failed: {e}")
            return False
