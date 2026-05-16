# OROVA Nova Agency Engine - V2.2.1 (Architect Overhaul)
import os
import sys
import json
import logging
import asyncio
import threading
import time
import httpx
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

from app.skills.agentmail_skill import check_replies
from app.skills.vault_skill import backup_database, restore_latest, vault_scheduler_loop
from app.skills.crawl_skill import cleanup_crawler
from app.skills.sheets_sync import restore_leads_from_sheets, update_lead_status_sheets

@asynccontextmanager
async def lifespan(app: FastAPI):
    # [P5/P6] Run migrations and optimizations
    DatabaseManager.init_db()
    await DatabaseManager.run_phase5_migrations()
    await AgentSoul.initialize()

    if await DatabaseManager.is_empty():
        logger.info("♻️ Database appears empty. Checking Google Sheets for restoration source of truth...")
        leads = await restore_leads_from_sheets()
        if leads:
            for lead in leads:
                DatabaseManager.save_lead(lead, sync_to_sheets=False)
            logger.info(f"♻️ Restored {len(leads)} leads from Google Sheets")
        else:
            logger.warning("⚠️ No leads found in Google Sheets. Attempting Google Drive backup restore...")
            restore_res = await restore_latest()
            if restore_res.get("ok"):
                logger.info(f"♻️ Restored database snapshot from Drive: {restore_res.get('filename')}")
                DatabaseManager._close_all_connections()
                DatabaseManager._init_sqlite_fallback()
            else:
                logger.warning(f"⚠️ No Drive backup available or restore failed: {restore_res.get('error')}")

    # [P6] Register SIGTERM for Render redeploys
    loop = asyncio.get_running_loop()
    DatabaseManager.register_sigterm_handler(loop)
    
    # [P6] Register Telegram Webhook
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if tg_token and render_url:
        webhook_url = f"{render_url}/telegram"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"https://api.telegram.org/bot{tg_token}/setWebhook",
                    json={"url": webhook_url, "allowed_updates": ["message"]},
                    timeout=10
                )
                if res.status_code == 200:
                    logger.info(f"✅ Telegram webhook registered: {webhook_url}")
                else:
                    logger.warning(f"⚠️  Telegram webhook registration failed: {res.text}")
        except Exception as e:
            logger.warning(f"⚠️  Could not register Telegram webhook: {e}")
    else:
        logger.warning("⚠️ Telegram webhook not registered: TELEGRAM_BOT_TOKEN or RENDER_EXTERNAL_URL missing")
    
    # [P6] Start Vault Scheduler (Auto-backup)
    asyncio.create_task(vault_scheduler_loop())
    
    # [P2] Start Bounded Telegram Queue
    await tg_queue.start(process_telegram_message)
    
    # [P2] Start Autonomous Learning Loop
    scheduler = AsyncIOScheduler()
    scheduler.add_job(reinforcer.run_cycle, "interval", hours=6)
    scheduler.start()
    # Keep-alive ping for Render free tier
    keep_alive_url = os.getenv("RENDER_EXTERNAL_URL")
    if keep_alive_url:
        async def _ping():
            while True:
                try:
                    async with httpx.AsyncClient() as client:
                        await client.get(keep_alive_url, timeout=5)
                except Exception:
                    pass
                await asyncio.sleep(60)
        asyncio.create_task(_ping())
    
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
    usage = await DatabaseManager.get_usage_stats()
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
    """Phase 4+: Full system pulse — circuit breakers, queue depth, learning stats, hardening metrics."""
    from app.core.ai_client import _BREAKER
    from app.core.hardening import memory_monitor, health_checks, tracer
    
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
    
    # [P4] Memory monitoring
    memory_status = await memory_monitor.check_memory()
    
    # [P4] Health checks
    hardening_health = await health_checks.run_all()
    
    any_open = any(v["state"] == "open" for v in breaker_status.values())
    memory_critical = memory_status.get("critical", False)
    
    return {
        "status": "Critical" if memory_critical else ("Degraded" if any_open else "Operational"),
        "timestamp": now.isoformat(),
        "circuit_breakers": breaker_status,
        "queue_depth": q_depth,
        "learning_stats": learning_stats,
        "memory": memory_status,
        "hardening_health": hardening_health,
        "active_traces": len(tracer.traces),
    }

@app.get("/api/hardening/metrics")
async def get_hardening_metrics(authorized: bool = Depends(require_dashboard_api_key)):
    """Get hardening metrics: memory, rate limits, request traces."""
    from app.core.hardening import memory_monitor, tracer
    
    memory_stats = await memory_monitor.get_memory_stats()
    return {
        "status": "ok",
        "memory": memory_stats,
        "rate_limiter_state": dict(tracer.traces),
        "timestamp": datetime.utcnow().isoformat(),
    }

@app.get("/api/trace/{request_id}")
async def get_request_trace(request_id: str, authorized: bool = Depends(require_dashboard_api_key)):
    """Get trace for a specific request ID."""
    from app.core.hardening import tracer
    
    trace = tracer.get_trace(request_id)
    return {"status": "ok", "request_id": request_id, "trace": trace}

async def require_dashboard_api_key(x_api_key: Optional[str] = Header(None)):
    expected = os.getenv("DASHBOARD_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return True

@app.get("/api/leads")
async def get_leads(limit: int = 100, authorized: bool = Depends(require_dashboard_api_key)):
    leads = await DatabaseManager.query("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,), fetchall=True)
    return {"status": "ok", "leads": [dict(r) for r in leads]}

@app.get("/api/metrics")
async def get_metrics(client_id: int = 0, authorized: bool = Depends(require_dashboard_api_key)):
    metrics = DatabaseManager.get_metrics(client_id)
    return {"status": "ok", "metrics": metrics}

@app.get("/api/agents")
async def get_agent_status(authorized: bool = Depends(require_dashboard_api_key)):
    agents = [
        {"name": "Nova", "role": "CEO", "status": "online"},
        {"name": "Hawk", "role": "Lead Hunter", "status": "online"},
        {"name": "Closer", "role": "Sales Director", "status": "online"},
        {"name": "Quill", "role": "Content Strategist", "status": "online"},
        {"name": "Sentinel", "role": "Operations", "status": "online"},
        {"name": "Oracle", "role": "Data Intel", "status": "online"}
    ]
    return {"status": "ok", "agents": agents}

@app.post("/api/leads/{lead_id}/approve")
async def approve_lead(lead_id: int, authorized: bool = Depends(require_dashboard_api_key)):
    await DatabaseManager.query("UPDATE leads SET status = 'Approved' WHERE id = ?", (lead_id,))
    await update_lead_status_sheets(lead_id, "Approved")
    return {"status": "ok", "message": f"Lead {lead_id} approved"}

@app.post("/api/jobs/hunt")
async def job_hunt(authorization: str = Header(None), x_api_key: str = Header(None)):
    authorized = (authorization == f"Bearer {os.getenv('CRON_SECRET')}") or (x_api_key == os.getenv("DASHBOARD_API_KEY"))
    if not authorized:
        raise HTTPException(status_code=403)
    from app.worker import run_lead_hunt_slow_lane
    asyncio.create_task(run_lead_hunt_slow_lane(client_id=0))
    return {"status": "job_started", "job": "lead_hunt"}

@app.post("/api/jobs/check-replies")
async def job_replies(authorization: str = Header(None), x_api_key: str = Header(None)):
    authorized = (authorization == f"Bearer {os.getenv('CRON_SECRET')}") or (x_api_key == os.getenv("DASHBOARD_API_KEY"))
    if not authorized:
        raise HTTPException(status_code=403)
    res = check_replies(limit=5)
    return {"status": "complete", "replies_found": res.get("count", 0)}

@app.post("/api/jobs/backup")
async def job_backup(authorization: str = Header(None), x_api_key: str = Header(None)):
    authorized = (authorization == f"Bearer {os.getenv('CRON_SECRET')}") or (x_api_key == os.getenv("DASHBOARD_API_KEY"))
    if not authorized:
        raise HTTPException(status_code=403)
    res = await backup_database()
    return {"status": "complete", "backup": res}

@app.get("/api/observability/metrics")
async def get_metrics_prometheus(authorized: bool = Depends(require_dashboard_api_key)):
    """Get Prometheus-format metrics."""
    from app.core.monitoring import metrics_collector
    return {"prometheus": metrics_collector.export_prometheus()}

@app.get("/api/observability/errors")
async def get_errors(authorized: bool = Depends(require_dashboard_api_key)):
    """Get error tracking summary."""
    from app.core.monitoring import error_tracker
    return {"status": "ok", "errors": error_tracker.get_error_summary()}

@app.get("/api/observability/performance")
async def get_performance(authorized: bool = Depends(require_dashboard_api_key)):
    """Get performance profiling stats."""
    from app.core.monitoring import profiler
    return {"status": "ok", "performance": profiler.get_all_stats()}

@app.get("/api/observability/dashboard")
async def get_observability_dashboard(authorized: bool = Depends(require_dashboard_api_key)):
    """Get complete observability dashboard data."""
    from app.core.monitoring import observability
    dashboard_data = await observability.get_dashboard_data()
    return {"status": "ok", **dashboard_data}

async def process_telegram_message(data: dict):
    """Worker for the Backpressure Queue."""
    try:
        msg_obj = data.get("message", {})
        if not msg_obj:
            logger.warning("[Telegram] Received update with no message object")
            return
        
        # Extract chat_id and text
        chat_id = msg_obj.get("chat", {}).get("id")
        text = msg_obj.get("text") or msg_obj.get("caption", "")
        
        if not chat_id or not text:
            logger.warning(f"[Telegram] Missing chat_id or text in message")
            return
        
        # Resolve Topic/Agent
        topic_id = str(msg_obj.get("message_thread_id", "1"))
        agent_role = TOPIC_AGENT_MAP.get(topic_id, "nova")
        
        logger.info(f"[Telegram] Processing: chat_id={chat_id}, text={text[:50]}..., agent={agent_role}")
        
        # Route to Brain
        result = await router.handle_message(text, chat_id=chat_id, history=None)
        
        # Send response back to Telegram
        if result:
            await router._send_telegram(chat_id, str(result)[:4096])
    except Exception as e:
        logger.error(f"[Swarm] Worker failed: {e}", exc_info=True)

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Ingest point for Telegram via Queue."""
    data = await request.json()
    logger.info(f"[Telegram] Webhook received update: {list(data.keys())}")
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

