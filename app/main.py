import os
import sys
import json
import logging
import asyncio
import threading
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
async def process_telegram_message(update_data: dict):
    try:
        message = update_data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")
        
        if not chat_id: return

        logger.info(f"📥 Received Telegram message from {chat_id}: {text[:50]}...")
        _append_log(f"Message from {chat_id}: {text}")
        
        # Router with async db
        history = await DatabaseManager.get_chat_history(client_id=0)
        history_list = [{"role": row["role"], "content": row["content"]} for row in history]
        
        logger.info(f"🧠 Routing message for {chat_id}...")
        response = await router.route(text, chat_id, history_list)
        
        # Ensure response is a string
        if not isinstance(response, str):
            response = str(response)

        logger.info(f"📤 Sending reply to {chat_id}: {response[:50]}...")
        
        # Save interaction
        await DatabaseManager.query(
            "INSERT INTO chat_history (role, content) VALUES (?, ?), (?, ?)",
            ("user", text, "assistant", response)
        )
        
        # Send back to Telegram
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("❌ TELEGRAM_BOT_TOKEN is missing from environment!")
            return
        
        logger.info(f"🔑 Using Bot Token: {token[:4]}...{token[-4:]}")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id, 
            "text": response
            # parse_mode removed for resilience against AI markdown errors
        }
        
        if message.get("is_topic_message") and message.get("message_thread_id"):
            payload["message_thread_id"] = message.get("message_thread_id")
            
        import httpx
        async with httpx.AsyncClient() as client:
            tg_res = await client.post(url, json=payload)
            if tg_res.status_code != 200:
                logger.error(f"❌ Telegram API Error: {tg_res.text}")
            else:
                logger.info(f"✅ Reply delivered to {chat_id}")
                
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
