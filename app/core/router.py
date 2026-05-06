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

    async def route(self, message: str, chat_id: int, history: list = None, agent_id: str = "nova"):
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

        # 1.5 DIRECT EMAIL INTERCEPT (Bypass AI for speed)
        if "email" in lower_msg and "@" in lower_msg:
            logger.info("🎯 ROUTER: Direct Email Intercept triggered.")
            email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', message)
            if email_match:
                recipient = email_match.group(1)
                body_match = re.search(r'(?:saying|content|message|body|say|tell|write|intro|introducing)\s+(.*)', message, re.IGNORECASE)
                body = body_match.group(1) if body_match else message
                try:
                    from app.skills.agentmail_skill import send_outreach
                    res = send_outreach(to=recipient, subject="Nova | Message from OROVA", body=body)
                    if res.get("status") == "success":
                        return f"✅ Done, Boss. I've sent that email to {recipient} via AgentMail."
                    else:
                        # Return the ACTUAL AgentMail error to diagnose it
                        agentmail_error = res.get('error') or res.get('message')
                        return f"⚠️ AgentMail Failed: {agentmail_error}"
                except Exception as e:
                    logger.error(f"💥 Router Email failed: {e}")
                    return f"⚠️ Email tool error: {str(e)}."

        # 2. AI Planner (The Brain) - EVERYTHING else goes here
        logger.info(f"Router: Routing to {agent_id.upper()} for Client {chat_id}")
        return await self.planner.execute(message, agent_id=agent_id, client_id=chat_id, conversation_history=history)

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
