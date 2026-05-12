"""
Fixed: added handle_message() that process_telegram_message() in main.py requires.
Without this, the Telegram webhook silently does nothing.
"""
import re
import os
import logging
import httpx

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)

_IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm) are you|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)|"
    r"who (made|built|created|trained) you|what powers you|underlying model|"
    r"what (are|is) (your|the) (model|ai|engine)|powered by)\b",
    re.IGNORECASE,
)

_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI partner. What can I do for you?"

# Per-chat history stored in memory (cleared on restart, which is fine for free tier)
_CHAT_HISTORIES: dict[str, list] = {}


class Router:
    \"\"\"
    Smart Router for OpenClaw.
    Priority: Identity Guard → Shortcuts → Direct-Send Intercept → AI Planner
    \"\"\"

    def __init__(self, ai_planner, lead_hunter):
        self.planner = ai_planner
        self.lead_hunter = lead_hunter
        self.shortcuts = {
            r"^/reset$": self._reset_instruction,
        }

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: called by main.py process_telegram_message (queue worker)
    # ─────────────────────────────────────────────────────────────────────
    async def handle_message(self, update: dict, agent_role: str = "nova"):
        \"\"\"
        Handle a full Telegram update dict.
        Extracts text + chat_id, routes to planner, sends reply back.
        \"\"\"
        msg = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or {}
        )
        text = msg.get("text", "").strip()
        chat_id = msg.get("chat", {}).get("id")

        if not text or not chat_id:
            return  # ignore non-text updates (stickers, photos, etc.)

        chat_key = str(chat_id)

        # /reset clears history without hitting the planner
        if text.lower() == "/reset":
            _CHAT_HISTORIES[chat_key] = []
            await self._send_telegram(chat_id, "🧠 Memory wiped. Fresh start.")
            return

        history = _CHAT_HISTORIES.setdefault(chat_key, [])

        try:
            result = await self.route(text, chat_id, history, agent_role)

            if isinstance(result, dict):
                reply = result.get("response") or result.get("result") or str(result)
            else:
                reply = str(result)

            # Update history (trim to last 20 turns)
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            if len(history) > 20:
                _CHAT_HISTORIES[chat_key] = history[-20:]

            await self._send_telegram(chat_id, reply)

        except Exception as e:
            logger.error(f"[Router.handle_message] Error for chat {chat_id}: {e}", exc_info=True)
            await self._send_telegram(chat_id, f"⚠️ Error: {str(e)[:200]}")

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: called directly by /api/chat endpoint
    # ─────────────────────────────────────────────────────────────────────
    async def route(
        self,
        message: str,
        chat_id: int,
        history: list = None,
        agent_id: str = "nova",
    ) -> str | dict:
        message = message.strip()
        lower_msg = message.lower()

        # 1. Identity guard (no token spend)
        if _IDENTITY_PROBE_RE.search(lower_msg):
            logger.info("[Router] Identity probe intercepted")
            return _IDENTITY_DEFLECT

        # 2. Instant shortcuts
        for pattern, handler in self.shortcuts.items():
            if re.search(pattern, lower_msg):
                logger.info(f"[Router] Shortcut matched '{pattern}'")
                return await handler()

        # 3. Direct-email intercept (prevents double planner entry)
        email_match = _EMAIL_RE.search(message)
        send_intent = any(
            k in lower_msg
            for k in ["send", "write", "email", "reach out", "follow up"]
        )
        if email_match and send_intent:
            logger.info(f"[Router] Direct-send intercept → {email_match.group(0)}")
            return await self.planner.execute(
                message,
                client_id=chat_id,
                conversation_history=history or [],
                agent_id="nova",
                _already_intercepted=True,
            )

        # 4. Full planner (ReAct loop)
        return await self.planner.execute(
            message,
            client_id=chat_id,
            conversation_history=history or [],
            agent_id=agent_id,
        )

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE helpers
    # ─────────────────────────────────────────────────────────────────────
    async def _send_telegram(self, chat_id: int, text: str):
        \"\"\"Send a message (split if > 4000 chars) via Telegram Bot API.\"\"\"
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("[Router] TELEGRAM_BOT_TOKEN not set — cannot reply")
            return

        chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)] if len(text) > 4000 else [text]
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for chunk in chunks:
                    await client.post(url, json={"chat_id": chat_id, "text": chunk})
        except Exception as e:
            logger.error(f"[Router] Telegram send failed: {e}")

    async def _reset_instruction(self):
        return "Use the /reset command to wipe my memory."

    async def _greet(self):
        return "👋 Nova online. Ready, Mark."

    async def _health_check(self):
        return "✅ System Status: ONLINE"

    async def _show_help(self):
        return "🤖 Try: 'Find 10 leads for [niche]' or '/reset' to wipe memory."

    async def _confirm_presence(self):
        return "Yes, Boss. I am here."
