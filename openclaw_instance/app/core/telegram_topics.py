"""
OROVA Nova — Telegram Topics Router (Operator 2.0)
Routes agent logs and notifications to isolated Telegram Forum Topics.

Prerequisites:
- Your Telegram group must be a Supergroup with Topics enabled.
- Run /setup_topics to auto-create the 4 forum threads.
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Topic configuration file path
TOPICS_FILE = os.path.join(
    os.getenv("DATA_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "telegram_topics.json"
)

# Default topic definitions
DEFAULT_TOPICS = {
    "hunting":  {"name": "🧵 Hunting",  "description": "Lead Gen logs — HAWK, Viper, Lead Finder", "thread_id": None},
    "strategy": {"name": "🧵 Strategy", "description": "Objection handling, SAGE, Quill drafts",   "thread_id": None},
    "finance":  {"name": "🧵 Finance",  "description": "CASH agent, ROI reports, Revenue",         "thread_id": None},
    "system":   {"name": "🧵 System",   "description": "Sentinel health, reboots, errors",         "thread_id": None},
}

# Agent-to-topic mapping
AGENT_TOPIC_MAP = {
    "hawk":     "hunting",
    "viper":    "hunting",
    "lead_finder": "hunting",
    "gate":     "hunting",
    "quill":    "strategy",
    "sage":     "strategy",
    "closer":   "strategy",
    "oracle":   "finance",
    "cashclaw": "finance",
    "revenue":  "finance",
    "sentinel": "system",
    "nightshift": "system",
    "nova":     None,  # Nova sends to main chat
}


class TelegramTopicRouter:
    """Manages Telegram Forum Topics for OROVA sub-agent routing."""

    def __init__(self):
        self.topics = self._load_topics()
        self.enabled = any(t.get("thread_id") for t in self.topics.values())
        if self.enabled:
            logger.info(f"[TOPICS] Router active — {sum(1 for t in self.topics.values() if t.get('thread_id'))} topics configured")
        else:
            logger.info("[TOPICS] Router inactive — run /setup_topics to enable")

    def _load_topics(self) -> dict:
        """Load topic config from disk, or return defaults."""
        if os.path.exists(TOPICS_FILE):
            try:
                with open(TOPICS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_TOPICS.copy()

    def _save_topics(self):
        """Persist topic config to disk."""
        try:
            with open(TOPICS_FILE, "w") as f:
                json.dump(self.topics, f, indent=2)
        except Exception as e:
            logger.error(f"[TOPICS] Failed to save: {e}")

    def get_thread_id(self, topic_key: str) -> Optional[int]:
        """Get the message_thread_id for a topic key."""
        topic = self.topics.get(topic_key)
        return topic.get("thread_id") if topic else None

    def get_topic_for_agent(self, agent_name: str) -> Optional[str]:
        """Map an agent name to its topic key."""
        return AGENT_TOPIC_MAP.get(agent_name.lower())

    async def send_to_topic(self, bot, chat_id: int, topic_key: str, text: str, **kwargs):
        """Send a message to a specific topic thread, with fallback to main chat."""
        thread_id = self.get_thread_id(topic_key)

        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=thread_id,
                **kwargs
            )
        except Exception as e:
            # Fallback: send to main chat if topic fails
            logger.warning(f"[TOPICS] Failed to send to '{topic_key}' (thread={thread_id}): {e}")
            try:
                await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            except Exception as e2:
                logger.error(f"[TOPICS] Fallback also failed: {e2}")

    async def send_agent_log(self, bot, chat_id: int, agent_name: str, text: str, **kwargs):
        """Route an agent's log message to the correct topic."""
        topic_key = self.get_topic_for_agent(agent_name)
        if topic_key and self.enabled:
            await self.send_to_topic(bot, chat_id, topic_key, text, **kwargs)
        else:
            # No topic mapping or topics not enabled — send to main chat
            try:
                await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            except Exception as e:
                logger.error(f"[TOPICS] send_agent_log failed: {e}")

    async def setup_topics(self, bot, chat_id: int) -> str:
        """Auto-create forum topics in a Supergroup. Returns status message."""
        created = 0
        errors = []

        for key, topic_def in self.topics.items():
            if topic_def.get("thread_id"):
                continue  # Already created

            try:
                result = await bot.create_forum_topic(
                    chat_id=chat_id,
                    name=topic_def["name"],
                    icon_color=0x6FB9F0  # Blue
                )
                self.topics[key]["thread_id"] = result.message_thread_id
                created += 1
                logger.info(f"[TOPICS] Created '{topic_def['name']}' → thread_id={result.message_thread_id}")
            except Exception as e:
                errors.append(f"{topic_def['name']}: {e}")
                logger.warning(f"[TOPICS] Failed to create '{topic_def['name']}': {e}")

        self._save_topics()
        self.enabled = any(t.get("thread_id") for t in self.topics.values())

        if errors:
            return (
                f"✅ Created {created} topics, ❌ {len(errors)} failed.\n"
                f"Errors:\n" + "\n".join(f"  • {e}" for e in errors) + "\n\n"
                "⚠️ Make sure your group has Topics enabled (Group Settings → Topics → ON)"
            )
        return f"✅ All {created} topics created successfully! OROVA Operator 2.0 is live."


# Global instance
topic_router = TelegramTopicRouter()
