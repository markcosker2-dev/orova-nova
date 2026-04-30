import re
import logging

logger = logging.getLogger(__name__)

class Router:
    """
    Smart Router for OpenClaw.
    Priority: Shortcuts -> AI Planner (The Brain)
    """
    def __init__(self, ai_planner, lead_hunter):
        self.planner = ai_planner
        self.lead_hunter = lead_hunter

        # Instant Regex Shortcuts (No AI - $0 Cost)
        self.shortcuts = {
            r'/reset': self._reset_instruction
        }

    async def route(self, message: str, chat_id: int, history: list = None):
        """
        Route the message to the correct handler.
        """
        message = message.strip()
        lower_msg = message.lower()

        # 1. Check Shortcuts (Instant Responses)
        for pattern, handler in self.shortcuts.items():
            if re.search(pattern, lower_msg):
                logger.info(f"Router: Shortcut matched '{pattern}'")
                return await handler()

        # 2. AI Planner (The Brain) - EVERYTHING else goes here
        logger.info(f"Router: Routing to AI Planner (Nova) for Client {chat_id}") # chat_id here is client_id
        return await self.planner.execute(message, client_id=chat_id, conversation_history=history)

    async def _greet(self):
        return "👋 NOVA (CLOUD V2.2 - 18:32). Ready, Mark."

    async def _health_check(self):
        return "✅ **System Status:** ONLINE\nRunning on AWS."

    async def _show_help(self):
        return "🤖 Try: 'Find 10 leads for [niche]' or '/reset' to wipe memory."

    async def _chat_status(self):
        return "I'm functioning at 100% efficiency and ready to work! 🚀"

    async def _is_strategy(self, message: str):
        keywords = ["strategy", "analyze", "report", "plan", "how to", "advice", "look up"]
        return any(k in message.lower() for k in keywords)

    async def _confirm_presence(self):
        return "Yes, Boss. I am here."
        
    async def _reset_instruction(self):
        return "Use the /reset command to wipe my memory."
