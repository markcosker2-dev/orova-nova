import os
import sys
import json
import logging
import asyncio
import threading
from typing import Optional
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

# Add app and parent paths for modular imports
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root_path)

from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner
from app.core.router import Router
from app.core.database import DatabaseManager
from app.core.soul import AgentSoul
from app.skills.lead_finder import find_leads

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- State ---
ai_client = UnifiedAIClient()
planner = TaskPlanner(ai_client)
router = Router(planner, lead_hunter=find_leads)
LOG_BUFFER = []
# Map Telegram Thread IDs (Topic IDs) to Agent Personas
# User needs to fill these in once they see the IDs in the logs
TOPIC_AGENT_MAP = {
    "1": "nova",    # General
    "2": "hawk",    # Lead hunt
    "3": "closer",  # Sales and Objections
    "5": "pixel",   # Creative Audits
    "6": "oracle",  # Financials
    "7": "atlas"    # Dev & Fixes
}

def _append_log(msg: str):
    LOG_BUFFER.append({"ts": datetime.now().strftime("%H:%M:%S"), "msg": msg})
    if len(LOG_BUFFER) > 100: LOG_BUFFER.pop(0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and Soul
    await DatabaseManager.init_db()
    await AgentSoul.initialize()
    logger.info("🚀 NOVA Gateway Online on port 18789")
    yield
    logger.info("🛑 NOVA Gateway Shutting Down")

app = FastAPI(title="OROVA Unified Agency Bridge", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Security (REMOVED) ---
async def validate_api_key():
    return True

# --- Health Check ---
@app.get("/health")
@app.head("/")
async def health_check():
    return {"status": "OpenClaw Online", "timestamp": datetime.now().isoformat()}

# --- API Routes ---
@app.get("/api/clients")
async def api_clients():
    try:
        clients = await DatabaseManager.get_clients()
        return {"clients": clients if clients else []}
    except Exception as e:
        logger.error(f"Error fetching clients: {e}")
        return {"clients": []}

@app.get("/api/metrics")
async def api_metrics(client_id: int = 0):
    try:
        metrics = await DatabaseManager.get_metrics(client_id)
        return metrics if metrics else {}
    except Exception:
        return {}

@app.get("/api/leads")
async def api_leads(client_id: int = 0):
    try:
        leads = await DatabaseManager.get_leads(client_id)
        return {"leads": leads if leads else [], "total": len(leads) if leads else 0}
    except Exception:
        return {"leads": [], "total": 0}

@app.get("/api/logs")
async def api_logs():
    return {"logs": LOG_BUFFER[-50:]}

@app.get("/api/dashboard")
async def api_dashboard(client_id: int = 0):
    try:
        return {
            "metrics": await DatabaseManager.get_metrics(client_id),
            "leads": await DatabaseManager.get_leads(client_id),
            "tasks": await DatabaseManager.get_tasks(client_id),
            "content": await DatabaseManager.get_content(client_id),
            "memories": await DatabaseManager.get_memories(client_id)
        }
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"error": str(e)}

@app.get("/api/tasks")
async def get_tasks(client_id: int = 0):
    return {"tasks": await DatabaseManager.get_tasks(client_id)}

@app.post("/api/tasks")
async def set_tasks(request: Request, client_id: int = 0):
    tasks = await request.json()
    # Simplified: Wipe and replace for the client
    await DatabaseManager.query("DELETE FROM tasks WHERE client_id = ?", (client_id,))
    for t in tasks:
        await DatabaseManager.query(
            "INSERT INTO tasks (id, title, description, assignee, priority, status, client_id, due) VALUES (?,?,?,?,?,?,?,?)",
            (t.get("id"), t.get("title"), t.get("description"), t.get("assignee"), t.get("priority"), t.get("status"), client_id, t.get("due"))
        )
    return {"status": "ok"}

@app.get("/api/content")
async def get_content(client_id: int = 0):
    return {"content": await DatabaseManager.get_content(client_id)}

@app.post("/api/content")
async def set_content(request: Request, client_id: int = 0):
    content = await request.json()
    await DatabaseManager.query("DELETE FROM content WHERE client_id = ?", (client_id,))
    for c in content:
        await DatabaseManager.query(
            "INSERT INTO content (id, title, body, type, status, client_id) VALUES (?,?,?,?,?,?)",
            (c.get("id"), c.get("title"), c.get("body"), c.get("type"), c.get("status"), client_id)
        )
    return {"status": "ok"}

@app.get("/api/memory")
async def get_memory(client_id: int = 0):
    return {"memories": await DatabaseManager.get_memories(client_id)}

@app.post("/api/memory")
async def set_memory(request: Request, client_id: int = 0):
    memories = await request.json()
    await DatabaseManager.query("DELETE FROM memories WHERE client_id = ?", (client_id,))
    for m in memories:
        await DatabaseManager.query(
            "INSERT INTO memories (id, category, content, client_id) VALUES (?,?,?,?)",
            (m.get("id"), m.get("tag") or m.get("category"), m.get("body") or m.get("content"), client_id)
        )
    return {"status": "ok"}

@app.get("/api/chat/history")
async def get_chat_history(client_id: int = 0):
    return {"history": await DatabaseManager.get_chat_history(client_id)}

@app.post("/api/chat/history")
async def set_chat_history(request: Request, client_id: int = 0):
    data = await request.json()
    history = data.get("history", [])
    await DatabaseManager.query("DELETE FROM chat_history WHERE client_id = ?", (client_id,))
    for h in history:
        await DatabaseManager.query(
            "INSERT INTO chat_history (role, content, client_id) VALUES (?,?,?)",
            (h.get("role"), h.get("content"), client_id)
        )
    return {"status": "ok"}

# --- Telegram Webhook Logic (Operator 2.0) ---
async def _send_telegram_reply(chat_id: int, text: str, thread_id: Optional[int] = None):
    """Helper to send messages back to Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ TELEGRAM_BOT_TOKEN missing")
        return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if thread_id:
        payload["message_thread_id"] = thread_id
        
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=10.0)
            if res.status_code != 200:
                logger.error(f"❌ TG Send Error: {res.text}")
                _append_log(f"TG Error: {res.text}")
    except Exception as e:
        logger.error(f"💥 Failed to send TG reply: {e}")

async def process_telegram_message(update_data: dict):
    try:
        message = update_data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")
        message_thread_id = message.get("message_thread_id")
        
        if not chat_id: return

        logger.info(f"📥 Received Telegram message from {chat_id} (Topic: {message_thread_id}): {text[:50]}...")
        _append_log(f"Message from {chat_id}: {text}")

        # Determine Agent based on Topic
        agent_id = "nova"
        if message_thread_id:
            agent_id = TOPIC_AGENT_MAP.get(str(message_thread_id), "nova")

        # --- COMMAND HANDLING (/mode, /status) ---
        if text.startswith("/"):
            cmd_parts = text.lower().split()
            cmd = cmd_parts[0]
            
            if cmd == "/mode":
                if len(cmd_parts) > 1:
                    new_flavor = cmd_parts[1]
                    if new_flavor in ai_client.FLAVORS:
                        ai_client._set_flavor(new_flavor)
                        response = f"🧠 **BRAIN SWAP SUCCESSFUL**\n\nNova is now using: `{new_flavor.upper()}` mode\n\n_Note: Genius and Smart modes may take longer to respond._"
                    else:
                        response = f"❌ **INVALID MODE**\nAvailable: `fast`, `smart`, `genius`, `kimi`"
                else:
                    response = f"📊 **CURRENT BRAIN**: `{ai_client._get_flavor().upper()}`\nUse `/mode [type]` to switch."
                
                await _send_telegram_reply(chat_id, response, message_thread_id)
                return

            if cmd == "/status":
                flavor = ai_client._get_flavor()
                history = await DatabaseManager.get_chat_history(client_id=0)
                response = f"✅ **OROVA SYSTEM STATUS**\n\n🤖 **Active Brain**: `{flavor.upper()}`\n🧵 **Agent Persona**: `{agent_id.upper()}`\n🔋 **Memory**: `{len(history)}` messages\n📡 **Gateway**: Online (Render v5.3)"
                await _send_telegram_reply(chat_id, response, message_thread_id)
                return

        # --- ROUTING ---
        history = await DatabaseManager.get_chat_history(client_id=0)
        history_list = [{"role": row["role"], "content": row["content"]} for row in history]
        
        if len(history_list) > 10:
            history_list = history_list[-10:]
        
        logger.info(f"🧠 Routing message to {agent_id.upper()} for {chat_id}...")
        response_raw = await router.route(text, chat_id, history_list, agent_id=agent_id)
        
        if isinstance(response_raw, (tuple, list)):
            response = str(response_raw[0])
        else:
            response = str(response_raw)

        logger.info(f"📤 Sending reply to {chat_id}...")
        
        # Save interaction
        await DatabaseManager.query(
            "INSERT INTO chat_history (role, content) VALUES (?, ?), (?, ?)",
            ("user", text, "assistant", response)
        )
        
        # Send back to Telegram
        await _send_telegram_reply(chat_id, response, message_thread_id)
                
    except Exception as e:
        logger.error(f"💥 Webhook processing error: {e}", exc_info=True)
        _append_log(f"Processing Error: {e}")
                
    except Exception as e:
        logger.error(f"💥 Webhook processing error: {e}", exc_info=True)

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    background_tasks.add_task(process_telegram_message, data)
    return {"status": "ok"}

# --- Static Frontend ---
MC_PATH = os.path.join(root_path, "mission-control")
if os.path.exists(MC_PATH):
    app.mount("/", StaticFiles(directory=MC_PATH, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Use $PORT from environment, default to 18789
    port = int(os.environ.get("PORT", 18789))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
