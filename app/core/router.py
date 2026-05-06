import re
import logging

logger = logging.getLogger(__name__)

# ── Matchers ──────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)

# [FIX 1] Catches any common identity probe at the router level — before
# an AI call is made. If the router misses it (edge-case phrasing), the
# planner's own _IDENTITY_PROBE_RE provides a second line of defense.
_IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm) are you|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)|"
    r"who (made|built|created|trained) you|what powers you|underlying model|"
    r"what (are|is) (your|the) (model|ai|engine)|powered by)\b",
    re.IGNORECASE,
)

_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI partner. What can I do for you?"


class Router:
    """
    Smart Router for OpenClaw.
    Priority: Identity Guard → Shortcuts → Direct-Send Intercept → AI Planner
    """

    def __init__(self, ai_planner, lead_hunter):
        self.planner     = ai_planner
        self.lead_hunter = lead_hunter

        # Instant regex shortcuts — zero AI cost
        self.shortcuts = {
            r"/reset": self._reset_instruction,
        }

    async def route(
        self,
        message: str,
        chat_id: int,
        history: list = None,
        agent_id: str = "nova",
    ) -> str | dict:
        message   = message.strip()
        lower_msg = message.lower()

        # ── [FIX 1] IDENTITY GUARD — highest priority, instant response ───────
        # Checked before shortcuts and before any AI call. No token spend.
        if _IDENTITY_PROBE_RE.search(lower_msg):
            logger.info("[Router] Identity probe intercepted — returning persona deflect")
            return _IDENTITY_DEFLECT

        # ── SHORTCUTS ─────────────────────────────────────────────────────────
        for pattern, handler in self.shortcuts.items():
            if re.search(pattern, lower_msg):
                logger.info(f"[Router] Shortcut matched '{pattern}'")
                return await handler()

        # ── [FIX 2] DIRECT-EMAIL INTERCEPT ───────────────────────────────────
        # Router detected email + send intent.
        # Passes `_already_intercepted=True` so planner.execute() skips its own
        # Gate 1 duplicate check — one parse call, one send, done.
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
                conversation_history=history,
                agent_id="nova",
                _already_intercepted=True,  # ← tells planner: Gate 1 already done
            )

        # ── FULL PLANNER (Gate 2 ReAct) ───────────────────────────────────────
        return await self.planner.execute(
            message,
            client_id=chat_id,
            conversation_history=history,
            agent_id=agent_id,
        )

    # ── Shortcut handlers ──────────────────────────────────────────────────────

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
