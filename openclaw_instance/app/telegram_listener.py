import os
import time
import asyncio
import requests
import sys
import logging
import re
from dotenv import load_dotenv

# Ensure we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.ai_client import UnifiedAIClient
from app.core.agent_router import dispatch_task
from app.skills.instagram_skill import generate_instagram_content

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ Missing TELEGRAM_BOT_TOKEN in .env file.")
    sys.exit(1)

API_URL = f"https://api.telegram.org/bot{TOKEN}/"

def send_message(chat_id, text):
    """Sends a markdown formatted message back to the user via Telegram."""
    try:
        requests.post(API_URL + "sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

async def process_message(chat_id, text):
    """Feeds the user text to Nova's brain and handles sub-agent routing."""
    ai = UnifiedAIClient()
    
    system_prompt = (
        "You are Nova, the AI Chief of Staff for the 7-figure agency OROVA. "
        "You are texting your boss, Mark, on Telegram. "
        "Reply warmly, highly competent, and casually like a trusting friend. "
        "If Mark is just chatting, just reply normally. "
        "CRITICAL RULE: If Mark asks you to DO a specific task (e.g. 'Make an instagram post', 'Find leads for me', 'Write an email'), "
        "you MUST include exactly this XML tag in your reply: <ROUTING>extract the task description here</ROUTING>. "
        f"Mark just texted you: '{text}'"
    )
    
    response = await ai.generate(system_prompt)
    if not response or "Failed" in response:
        send_message(chat_id, "⚠️ Nova's brain is temporarily offline.")
        return

    # Check if Nova decided to route a task to a sub-agent
    match = re.search(r'<ROUTING>(.*?)</ROUTING>', response, re.IGNORECASE | re.DOTALL)
    
    if match:
        task_desc = match.group(1).strip()
        
        # Clean Nova's conversational response by hiding the routing tag from Mark
        clean_response = re.sub(r'<ROUTING>.*?</ROUTING>', '', response, flags=re.IGNORECASE | re.DOTALL).strip()
        if clean_response:
            send_message(chat_id, clean_response)
        
        send_message(chat_id, f"🔄 *Nova Dispatching Engine*:\nRouting task: _{task_desc}_")
        
        # Determine which sub-agent handles this (Hawk, Pixel, Quill, etc.)
        dispatch_res = dispatch_task(task_desc)
        agent_id = dispatch_res["assigned_agent"]
        agent_name = dispatch_res["agent_info"]["name"]
        
        # Execute the specific agent's skill
        if agent_id == "pixel":
            send_message(chat_id, f"🎨 **{agent_name}** activated. Designing scroll-stopping content...")
            ig_content = await generate_instagram_content(task_desc)
            send_message(chat_id, ig_content)
        else:
            send_message(chat_id, f"✅ Handed off successfully to **{agent_name}**. (Full execution for this specific agent is ready for OpenCode expansion).")
            
    else:
        # It's just a friendly chat, send Nova's raw response
        send_message(chat_id, response)

def main():
    logger.info("🤖 Nova 2-Way Conversational Telegram Listener Started...")
    offset = None
    
    while True:
        try:
            req = requests.get(API_URL + "getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            if req.status_code == 200:
                updates = req.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    
                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"]["text"]
                        
                        logger.info(f"Received message: {text}")
                        # Process asynchronously
                        asyncio.run(process_message(chat_id, text))
            else:
                logger.error(f"Telegram API Error: {req.status_code}")
                time.sleep(5)
                
        except requests.exceptions.Timeout:
            # Normal long-polling timeout, just continue
            continue
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
