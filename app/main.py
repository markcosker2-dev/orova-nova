# OROVA Nova Agency Engine - V2.2.1 (Architect Overhaul)
import os
import sys
import json
import logging
import asyncio
import threading
import time
from typing import Optional
from datetime import datetime, timedelta
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
# All topics route through Nova — she's the CEO and calls tools herself.
# Sub-agent models were causing 429 rate limits.
TOPIC_AGENT_MAP = {
    "1": "nova",    # General
    "2": "nova",    # Lead hunt
    "3": "nova",    # Sales
    "5": "nova",    # Creative
    "6": "nova",    # Financials
    "7": "nova"     # Dev
}

def _append_log(msg: str):
    LOG_BUFFER.append({"ts": datetime.now().strftime("%H:%M:%S"), "msg": msg})
    if len(LOG_BUFFER) > 100: LOG_BUFFER.pop(0)
from app.core.telegram_queue import tg_queue
from app.core.pattern_reinforcer import reinforcer
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# [P1] Mandatory Client Isolation Dependency
async def require_client(x_client_id: Optional[str] = Header(None), client_id: Optional[int] = None) -> int:
    resolved = None
    if x_client_id and x_client_id.isdigit(): resolved = int(x_client_id)
    elif client_id is not None: resolved = client_id
    if resolved is None or resolved < 1:
        raise HTTPException(status_code=401, detail="Valid client_id required")
    return resolved

from app.core.database import run_phase5_migrations, register_sigterm_handler, get_usage_stats
from app.skills.vault_skill import backup_database, restore_latest, vault_scheduler_loop
from app.skills.crawl_skill import cleanup_crawler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # [P5/P6] Run migrations and optimizations
    await DatabaseManager.init_db()
    await run_phase5_migrations()
    await AgentSoul.initialize()
    
    # [P6] Register SIGTERM for Render redeploys
    loop = asyncio.get_running_loop()
    register_sigterm_handler(loop)
    
    # [P6] Start Vault Scheduler (Auto-backup)
    asyncio.create_task(vault_scheduler_loop())
    
    # [P2] Start Bounded Telegram Queue
    await tg_queue.start(process_telegram_message)
    
    # [P2] Start Autonomous Learning Loop
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reinforcer.run_cycle, "interval", hours=6)
    scheduler.start()
    
    logger.info("🚀 NOVA Gateway Online | Swarm Survivability Layer Active")
    yield
    await tg_queue.stop()
    await cleanup_crawler()
    scheduler.shutdown()

app = FastAPI(title="OROVA Indestructible Agency Bridge", lifespan=lifespan)

# --- [P6] Admin Command Center ---

async def cmd_backup(update, context):
    """/backup — Manual vault upload."""
    await update.message.reply_text("🔐 *Vault:* Initiating backup...")
    res = await backup_database()
    msg = f"✅ *Backup Complete*: `{res['filename']}`" if res["ok"] else f"❌ *Failed*: `{res['error']}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_restore(update, context):
    """/restore — Pull latest from Drive."""
    await update.message.reply_text("⚠️ *Vault Restore:* Pulling latest snapshot...")
    res = await restore_latest()
    msg = f"✅ *Restored*: `{res['filename']}`. Restarting engine..." if res["ok"] else f"❌ *Failed*: `{res['error']}`"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_stats(update, context):
    """/stats — Report Economics."""
    usage = await get_usage_stats()
    totals = usage["totals"]
    msg = (
        f"📊 *OROVA Economic Report*\n"
        f"Total Cost: `${totals['cost']:.4f}`\n"
        f"Total Tokens: `{totals['t_in'] + totals['t_out']:,}`\n"
        f"Total Requests: `{totals['reqs']:,}`\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

@app.get("/health")
async def health_check():
    """Phase 5: Full system pulse — circuit breakers, queue depth, learning stats."""
    from app.core.ai_client import _BREAKER
    now = datetime.utcnow()
    window_24h = now - timedelta(hours=24)
    
    # Circuit Breaker Status
    breaker_status = {k: {"state": "open" if v["open_until"] > time.time() else "closed", "failures": v["failures"]} for k, v in _BREAKER.items()}
    
    # Queue Depth
    try: q_depth = tg_queue._q.qsize()
    except: q_depth = -1
    
    # Learning Stats (24h)
    try:
        row = await DatabaseManager.fetchone("SELECT COUNT(*) as cnt, AVG(decay_score) as avg_score FROM learned_patterns WHERE last_used_at >= ?", (window_24h.isoformat(),))
        learning_stats = {"patterns_reinforced": row["cnt"], "avg_confidence": row["avg_score"]}
    except: learning_stats = {}

    any_open = any(v["state"] == "open" for v in breaker_status.values())
    
    return {
        "status": "Degraded" if any_open else "Operational",
        "timestamp": now.isoformat(),
        "circuit_breakers": breaker_status,
        "queue_depth": q_depth,
    }

async def process_telegram_message(data: dict):
    """Worker for the Backpressure Queue."""
    try:
        # Resolve Topic/Agent
        topic_id = str(data.get("message", {}).get("message_thread_id", "1"))
        agent_role = TOPIC_AGENT_MAP.get(topic_id, "nova")
        
        # Route to Brain
        await router.handle_message(data, agent_role=agent_role)
    except Exception as e:
        logger.error(f"[Swarm] Worker failed: {e}")

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Ingest point for Telegram via Queue."""
    data = await request.json()
    accepted = await tg_queue.enqueue(data)
    if not accepted:
        return JSONResponse(status_code=503, content={"status": "queue_full", "detail": "Server under heavy load, try again"})
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

