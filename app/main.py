import os
import sys
import json
import logging
import asyncio
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from fastapi import FastAPI, Request, BackgroundTasks
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

# --- Health Server (Port 10000) ---
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OpenClaw Health: ONLINE")
    def log_message(self, format, *args): pass # Suppress

def run_health_server():
    server = HTTPServer(('0.0.0.0', 10000), HealthHandler)
    logger.info("💓 Health Check Server running on port 10000")
    server.serve_forever()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB and Soul
    await DatabaseManager.init_db()
    await AgentSoul.initialize()
    # Start separate thread for health checks on port 10000
    threading.Thread(target=run_health_server, daemon=True).start()
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

# --- Telegram Webhook Logic (Operator 2.0) ---
async def process_telegram_message(update_data: dict):
    try:
        message = update_data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "")
        
        # Support for Threaded Topics
        is_topic_message = message.get("is_topic_message", False)
        message_thread_id = message.get("message_thread_id")
        
        if not text or not chat_id:
            return

        _append_log(f"Message from {chat_id}: {text}")
        
        # Router with async db
        history = await DatabaseManager.get_chat_history(client_id=0)
        history_list = [{"role": row["role"], "content": row["content"]} for row in history]
        
        response = await router.route(text, chat_id, history_list)
        
        # Save interaction
        await DatabaseManager.query(
            "INSERT INTO chat_history (role, content) VALUES (?, ?), (?, ?)",
            ("user", text, "assistant", response)
        )
        
        # Send back to Telegram
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if token:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": chat_id, "text": response}
            if is_topic_message and message_thread_id:
                payload["message_thread_id"] = message_thread_id
                
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(url, json=payload)
                
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")

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
    uvicorn.run("app.main:app", host="0.0.0.0", port=18789)
