import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
FORUM_CHAT_ID = os.getenv("FORUM_CHAT_ID") or os.getenv("PERSONAL_CHAT_ID")

API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Topic mapping: name -> (topic_id, icon_color)
TOPICS = {
    "logs":        None,
    "system":      None,
    "performance": None,
    "alerts":      None,
}

TOPIC_NAMES = {
    "logs":        "📜 Activity Logs",
    "system":      "⚙️ System Status",
    "performance": "📊 Performance Metrics",
    "alerts":      "🚨 Critical Alerts",
}

TOPIC_COLORS = {
    "logs":        0x6FB9F0,  # Light Blue
    "system":      0xFFD67E,  # Yellow
    "performance": 0xCB86DB,  # Purple
    "alerts":      0xFF6B6B,  # Red
}


def load_topic_ids():
    """Load saved topic IDs from env or local storage"""
    import json
    try:
        with open("forum_topics.json", "r") as f:
            saved = json.load(f)
            for key in TOPICS:
                if key in saved:
                    TOPICS[key] = saved[key]
        logger.info("✅ Loaded existing forum topic IDs")
        return True
    except:
        logger.info("ℹ️ No existing forum topics found")
        return False


def save_topic_ids():
    """Save current topic IDs to disk"""
    import json
    with open("forum_topics.json", "w") as f:
        json.dump(TOPICS, f, indent=2)
    logger.info("💾 Saved forum topic IDs")


def create_forum_topic(name, icon_color=0x6FB9F0):
    """Call Telegram API to create a new forum topic"""
    try:
        resp = requests.post(API_URL + "createForumTopic", json={
            "chat_id": FORUM_CHAT_ID,
            "name": name,
            "icon_color": icon_color,
        }, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                topic_id = data["result"]["message_thread_id"]
                logger.info(f"✅ Created forum topic: {name} (ID: {topic_id})")
                return topic_id
        else:
            logger.error(f"❌ Failed to create topic {name}: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        logger.error(f"❌ Exception creating topic {name}: {e}")
        return None


async def setup_all_topics():
    """Create all 4 required forum topics if they don't exist"""
    if not FORUM_CHAT_ID:
        return False, "FORUM_CHAT_ID not configured"

    created = []
    existing = []

    load_topic_ids()

    for key, topic_name in TOPIC_NAMES.items():
        if TOPICS[key] is not None:
            existing.append(key)
            continue

        topic_id = create_forum_topic(topic_name, TOPIC_COLORS[key])
        if topic_id:
            TOPICS[key] = topic_id
            created.append(key)

    save_topic_ids()

    message = (f"✅ Forum Topics Setup Complete\n"
               f"Created: {len(created)} topics\n"
               f"Already exists: {len(existing)} topics\n\n")

    for key in TOPICS:
        status = "✅" if TOPICS[key] else "❌ FAILED"
        message += f"{status} {TOPIC_NAMES[key]}: ID={TOPICS[key]}\n"

    return True, message


def send_to_topic(topic: str, text: str, parse_mode="Markdown"):
    """Send message to a specific forum topic"""
    if not FORUM_CHAT_ID:
        logger.debug(f"⚠️ No FORUM_CHAT_ID configured, dropping message: {text[:80]}")
        return False

    if topic not in TOPICS:
        logger.warning(f"⚠️ Unknown topic '{topic}', defaulting to system")
        topic = "system"

    if TOPICS[topic] is None:
        # Fallback to main chat if topic not setup
        thread_id = None
    else:
        thread_id = TOPICS[topic]

    try:
        payload = {
            "chat_id": FORUM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        if thread_id is not None:
            payload["message_thread_id"] = thread_id

        requests.post(API_URL + "sendMessage", json=payload, timeout=10)
        return True
    except Exception as e:
        logger.error(f"Failed to send to topic {topic}: {e}")
        return False


# Initialize on import
try:
    load_topic_ids()
except:
    pass
