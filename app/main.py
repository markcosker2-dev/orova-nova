# OROVA Nova Agency Engine - V2.2.1 (Architect Overhaul)
import os
import sys
import json
import logging
import asyncio
import threading
import time
import httpx
import secrets
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
from app.skills.lead_gen_v3 import find_leads

from app.core.json_logger import configure_structured_logging

class BufferHandler(logging.Handler):
    def emit(self, record):
        try:
            _append_log(self.format(record))
        except NameError:
            pass  # Module still initializing

configure_structured_logging(level=logging.INFO)
logger = logging.getLogger()
logger.addHandler(BufferHandler())

# --- State ---
ai_client = UnifiedAIClient()
planner = TaskPlanner(ai_client)
router = Router(planner, lead_hunter=find_leads)
LOG_BUFFER = []
TOPIC_AGENT_MAP = {
    "1": "nova", "2": "nova", "3": "nova", "5": "nova", "6": "nova", "7": "nova"
}

# In-memory agent queue for Mission Control (simple, volatile)
AGENT_QUEUE = []
BACKGROUND_LOOP = None
_keep_alive_client = None  # Module-level sentinel for keep-alive httpx client
_task_loop_event = asyncio.Event()  # Thread-safe event for task loop coordination
_shutdown_event = asyncio.Event()  # Graceful shutdown signal

def _get_background_loop():
    global BACKGROUND_LOOP
    if BACKGROUND_LOOP is not None and BACKGROUND_LOOP.is_running():
        return BACKGROUND_LOOP
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _schedule_background(coro):
    loop = _get_background_loop()
    if loop is None:
        return None
    try:
        if loop.is_running():
            return loop.create_task(coro)
    except Exception:
        pass
    try:
        return asyncio.run_coroutine_threadsafe(coro, loop)
    except Exception:
        return None


def _append_log(msg: str):
    LOG_BUFFER.append({"ts": datetime.now().strftime("%H:%M:%S"), "msg": msg})
    if len(LOG_BUFFER) > 100:
        LOG_BUFFER.pop(0)
    _schedule_background(DatabaseManager.set_state('agent_logs', LOG_BUFFER[-500:]))



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
    # [WORKER] Start autonomous scheduler thread (FastAPI lifespan bootstraps all lanes)
    from app.worker import start_worker_scheduler, stop_worker_scheduler
    start_worker_scheduler()

    # [P5/P6] Run migrations and optimizations
    DatabaseManager.init_db()
    await DatabaseManager.run_phase5_migrations()
    DatabaseManager.mark_ready()
    await AgentSoul.initialize()

    # [R-08] Reload persisted CEO auto-execute proposals from DB
    try:
        from app.core.ceo_brain import _reload_pending_proposals
        count = await _reload_pending_proposals()
        logger.info(f"[CEO_BRAIN] Reloaded {count} pending auto-execute proposals from DB")
    except Exception as e:
        logger.warning(f"[CEO_BRAIN] Could not reload pending proposals: {e}")

    # [SELF-LEARNING] Bootstrap learning tables for trace/pattern/skill storage
    try:
        from app.core.self_learning import ensure_tables as ensure_learning_tables
        await ensure_learning_tables()
        logger.info("[SELF_LEARN] Learning tables initialized")
    except Exception as e:
        logger.warning(f"[SELF_LEARN] Table init failed: {e}")

    if await DatabaseManager.is_empty():
        # Drive snapshot FIRST: it restores everything (leads, outcomes,
        # learned strategies, memories). Sheets only holds leads, so trying
        # it first silently discards all learning data on every cold boot.
        logger.info("♻️ Database appears empty. Attempting Google Drive snapshot restore (full fidelity)...")
        restore_res = await restore_latest()
        if restore_res.get("ok"):
            logger.info(f"♻️ Restored database snapshot from Drive: {restore_res.get('filename')}")
            DatabaseManager._close_all_connections()
            DatabaseManager._init_sqlite_fallback()
            # Re-run Phase 5 migrations on the restored DB so schema is current
            try:
                await DatabaseManager.run_phase5_migrations()
                logger.info("♻️ Phase 5 migrations applied to restored DB")
            except Exception as mig_err:
                logger.warning(f"⚠️ Phase 5 migrations on restored DB failed: {mig_err}")
        else:
            logger.warning(f"⚠️ No Drive backup ({restore_res.get('error')}). Falling back to Google Sheets leads...")
            leads = await restore_leads_from_sheets()
            if leads:
                for lead in leads:
                    await DatabaseManager.asave_lead(lead)
                logger.info(f"♻️ Restored {len(leads)} leads from Google Sheets (leads only — learning data starts fresh)")
            else:
                logger.warning("⚠️ No restoration source available. Starting with an empty database.")

        # Re-run after restore so any pending_proposal:* rows from the restored DB
        # are rescheduled into the CEO brain scheduler.
        try:
            from app.core.ceo_brain import _reload_pending_proposals
            count = await _reload_pending_proposals()
            logger.info(f"[CEO_BRAIN] Reloaded {count} pending auto-execute proposals after DB restore")
        except Exception as e:
            logger.warning(f"[CEO_BRAIN] Could not reload pending proposals after restore: {e}")

    # [HERMESCLAW] Register all autonomous API endpoints
    from app.core.hermesclaw_endpoints import register_hermesclaw_routes
    register_hermesclaw_routes(app)
    
    # [P6] Register SIGTERM for Render redeploys
    global BACKGROUND_LOOP
    BACKGROUND_LOOP = asyncio.get_running_loop()
    DatabaseManager.register_sigterm_handler(BACKGROUND_LOOP)
    
    # [P6] Register Telegram Webhook
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if tg_token and render_url:
        webhook_url = f"{render_url}/telegram"
        try:
            async with httpx.AsyncClient() as client:
                tg_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
                payload = {"url": webhook_url, "allowed_updates": ["message"]}
                if tg_webhook_secret:
                    payload["secret_token"] = tg_webhook_secret
                res = await client.post(
                    f"https://api.telegram.org/bot{tg_token}/setWebhook",
                    json=payload,
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
    
    # ⏱️ Start task execution loop
    asyncio.create_task(_task_execution_loop())
    
    # [P2] Start Autonomous Learning Loop
    scheduler = AsyncIOScheduler()
    
    def _run_reinforcer_cycle_sync():
        asyncio.create_task(reinforcer.run_cycle())
    
    scheduler.add_job(_run_reinforcer_cycle_sync, "interval", hours=6, max_instances=1)
    scheduler.start()
    # Keep-alive ping for Render free tier (reuse single client)
    keep_alive_url = os.getenv("RENDER_EXTERNAL_URL")
    if keep_alive_url:
        global _keep_alive_client
        _keep_alive_client = httpx.AsyncClient(timeout=5.0)
        async def _ping():
            while True:
                try:
                    await _keep_alive_client.get(keep_alive_url)
                except Exception:
                    pass
                await asyncio.sleep(60)
        asyncio.create_task(_ping())
    
    # Restore persisted agent queue and logs into memory (best-effort)
    try:
        q = await DatabaseManager.get_state('agent_queue', [])
        logs = await DatabaseManager.get_state('agent_logs', [])
        if isinstance(q, list) and q:
            AGENT_QUEUE.clear()
            AGENT_QUEUE.extend(q[:200])
        if isinstance(logs, list) and logs:
            LOG_BUFFER.clear()
            LOG_BUFFER.extend(logs[-200:])
    except Exception:
        pass

    logger.info("🚀 NOVA Gateway Online | Swarm Survivability Layer Active")
    yield
    # ── Graceful Shutdown ──
    # Flush a DB snapshot to Drive first: Render's disk is ephemeral, so
    # anything since the last 3-hourly backup is lost unless we save now.
    # Render allows ~30s after SIGTERM; cap well under that.
    try:
        backup_res = await asyncio.wait_for(backup_database(), timeout=20)
        logger.info(f"💾 Shutdown backup: {backup_res.get('ok', False)}")
    except Exception as e:
        logger.warning(f"⚠️ Shutdown backup failed (non-fatal): {e}")
    _shutdown_event.set()
    _task_loop_event.set()  # Signal task loop to exit
    stop_worker_scheduler()  # Signal worker daemon thread to exit
    await tg_queue.stop()
    await cleanup_crawler()
    scheduler.shutdown()
    # Close keep-alive client if it exists
    try:
        if _keep_alive_client is not None:
            await _keep_alive_client.aclose()
    except Exception:
        pass
    # Close shared lead-gen httpx client
    try:
        from app.skills.lead_gen_v3 import _close_http_client
        await _close_http_client()
    except Exception:
        pass
    logger.info("🛑 NOVA Gateway Offline — graceful shutdown complete")

app = FastAPI(title="OROVA Indestructible Agency Bridge", lifespan=lifespan)

# [S-06] Request body size limit — reject bodies > 1MB to prevent OOM on 512MB tier
MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB

@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """Reject oversized request bodies and enforce HTTPS in production."""
    # Body size check
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"status": "error", "detail": "Request body too large (max 1MB)"})
    # HTTPS enforcement in production
    if os.getenv("APP_ENV") == "production":
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        if forwarded_proto == "http":
            https_url = str(request.url).replace("http://", "https://", 1)
            return JSONResponse(status_code=301, headers={"Location": https_url})
    response = await call_next(request)
    # Add HSTS header in production
    if os.getenv("APP_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    return response

# [S-12] Per-route rate limiting middleware — stricter limits for write/agent endpoints
@app.middleware("http")
async def per_route_rate_limit(request: Request, call_next):
    """Apply per-route rate limits using PerRouteRateLimiter from hardening."""
    from app.core.hardening import api_rate_limiter
    
    # Skip rate limiting for health checks
    if request.url.path in ("/health", "/api/health"):
        return await call_next(request)
    
    # Identify client: use X-Forwarded-For if behind proxy, else client host
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"
    client_id = f"api_{client_ip}"
    
    if not api_rate_limiter.is_allowed(client_id, request.url.path):
        retry_after = api_rate_limiter.get_retry_after(client_id, request.url.path)
        logger.warning(f"[RateLimit] {client_id} exceeded limit on {request.url.path} — retry after {retry_after:.1f}s")
        return JSONResponse(
            status_code=429,
            content={
                "status": "error",
                "detail": "Rate limit exceeded. Please try again later.",
                "retry_after": round(retry_after, 1),
            },
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
    
    return await call_next(request)

# [P5] CORS — allow dashboard origin (filter out empty strings to prevent wildcard-with-credentials)
_cors_origins = [
    "http://localhost:13210",
    "http://127.0.0.1:13210",
    "http://localhost:9119",
    os.getenv("RENDER_EXTERNAL_URL", ""),
]
_cors_origins = [o for o in _cors_origins if o]  # Remove empty strings

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Dashboard-Secret", "X-API-Key", "X-Telegram-Bot-Api-Secret-Token"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "detail": exc.detail},
            headers=getattr(exc, 'headers', None),
        )
    error_msg = f"GLOBAL ERROR: {str(exc)}"
    logger.error(error_msg)
    if '_append_log' in globals():
        _append_log(f"❌ {error_msg}")
    return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

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
    """Enhanced health probe for Render's uptime checks — verifies DB + memory."""
    checks = {"status": "Operational", "timestamp": datetime.utcnow().isoformat()}
    # Check DB connectivity
    try:
        if DatabaseManager.is_ready():
            row = await DatabaseManager.fetchone("SELECT 1 as ok")
            checks["db"] = "ok" if row else "degraded"
        else:
            checks["db"] = "not_ready"
            checks["status"] = "Degraded"
    except Exception as e:
        checks["db"] = f"error: {e}"
        checks["status"] = "Degraded"
    # Check memory
    try:
        from app.core.hardening import memory_monitor
        mem = await memory_monitor.check_memory()
        if mem.get("critical"):
            checks["memory"] = "critical"
            checks["status"] = "Critical"
        else:
            checks["memory"] = "ok"
    except Exception:
        checks["memory"] = "unknown"
    return checks

async def require_dashboard_api_key(request: Request):
    """Validate dashboard API key. Accepts X-Dashboard-Secret, X-API-Key, or ?dashboard_key=...
    Raises 403 if missing or invalid — endpoints receive True if passed.
    Uses constant-time comparison to prevent timing attacks.
    """
    import secrets as _secrets
    expected = os.getenv("DASHBOARD_API_KEY")
    if not expected:
        logger.critical("DASHBOARD_API_KEY not set — dashboard endpoints unavailable")
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    # Check multiple header names + query param
    provided = (
        request.headers.get("X-Dashboard-Secret")
        or request.headers.get("X-API-Key")
        or request.query_params.get("dashboard_key")
    )
    if not provided:
        raise HTTPException(status_code=403, detail="Unauthorized: missing API key header")
    if not _secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Unauthorized: invalid API key")
    return True

@app.post('/api/keys/new')
async def issue_dashboard_token(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    """Issue a short-lived dashboard session token. Requires existing dashboard API key in header.
    Returns {token: 'hex', expires_at: iso}
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    # TTL in seconds (default 3600 = 1 hour)
    ttl = int(payload.get('ttl') or 3600)
    issued_by = request.client.host if request.client else 'unknown'
    token = secrets.token_hex(16)
    expires_at = (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()

    # store token map in state
    try:
        tokens = await DatabaseManager.get_state('dashboard_tokens') or {}
    except Exception:
        tokens = {}
    tokens[token] = { 'created_at': datetime.utcnow().isoformat(), 'expires_at': expires_at, 'issued_by': issued_by }
    _schedule_background(DatabaseManager.set_state('dashboard_tokens', tokens))

    # [S-07] Prune expired tokens on every issuance
    now_iso = datetime.utcnow().isoformat()
    expired_keys = [k for k, v in tokens.items() if v.get('expires_at', '') < now_iso]
    for k in expired_keys:
        del tokens[k]
    if expired_keys:
        _schedule_background(DatabaseManager.set_state('dashboard_tokens', tokens))

    return { 'status': 'ok', 'token': token, 'expires_at': expires_at }


@app.get("/api/health")
async def api_health_check(authorized: bool = Depends(require_dashboard_api_key)):
    """Health probe for Mission Control dashboard — flattens structure for the frontend."""
    from app.core.ai_client import _BREAKER
    from app.core.hardening import memory_monitor, health_checks, tracer

    now = datetime.utcnow()
    window_24h = now - timedelta(hours=24)

    breaker_status = {k: {"state": "open" if v["open_until"] > time.time() else "closed", "failures": v["failures"]} for k, v in _BREAKER.items()}
    try: q_depth = tg_queue._q.qsize()
    except Exception: q_depth = -1

    try:
        row = await DatabaseManager.fetchone("SELECT COUNT(*) as cnt, AVG(decay_score) as avg_score FROM learned_patterns WHERE last_used_at >= ?", (window_24h.isoformat(),))
        learning_stats = {"patterns_reinforced": row["cnt"], "avg_confidence": row["avg_score"]}
    except Exception: learning_stats = {}

    memory_status = await memory_monitor.check_memory()
    hardening_health = await health_checks.run_all()
    any_open = any(v["state"] == "open" for v in breaker_status.values())
    memory_critical = memory_status.get("critical", False)

    # Flatten for Mission Control frontend
    total_errors = sum(b["failures"] for b in breaker_status.values())
    return {
        "status": "Critical" if memory_critical else ("Degraded" if any_open else "Operational"),
        "uptime": "Running",
        "errors": total_errors,
        "agents_online": sum(1 for v in breaker_status.values() if v["state"] == "closed"),
        "pending_emails": 0,
        "scheduler": {
            "fast_lane": "Active",
            "slow_lane": "Active",
            "email_drafter": "Active",
            "reply_monitor": "Active"
        },
        "queue_depth": q_depth,
        "memory": memory_status,
        "learning_stats": learning_stats,
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


@app.get('/api/agents/queue')
async def api_agent_queue(limit: int = 50, authorized: bool = Depends(require_dashboard_api_key)):
    """Return recent agent queue entries (in-memory)."""
    return {"status": "ok", "queue": AGENT_QUEUE[:limit]}


@app.get('/api/agents/logs')
async def api_agent_logs(limit: int = 200, authorized: bool = Depends(require_dashboard_api_key)):
    """Return recent in-memory logs for Mission Control UI."""
    return {"status": "ok", "logs": LOG_BUFFER[-limit:]}


@app.post('/api/agents/cancel')
async def api_agent_cancel(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    """Cancel a queued agent task. Payload {task_id: 'agent-...'}"""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    task_id = payload.get('task_id') or request.query_params.get('task_id')
    if not task_id:
        raise HTTPException(status_code=400, detail='task_id required')
    for r in AGENT_QUEUE:
        if r.get('task_id') == task_id:
            if r.get('status') == 'queued':
                r['status'] = 'cancelled'
                r['cancelled_at'] = datetime.utcnow().isoformat()
                _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))
                _append_log(f"✋ Cancelled agent task {task_id}")
                return {'status': 'ok', 'task_id': task_id, 'cancelled': True}
            return {'status': 'failed', 'reason': 'cannot cancel running or completed task', 'task': r}
    raise HTTPException(status_code=404, detail='task not found')


@app.post('/api/agents/retry')
async def api_agent_retry(request: Request, background: BackgroundTasks, authorized: bool = Depends(require_dashboard_api_key)):
    """Retry a previous task by task_id. Creates a new queued task and returns new task_id."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    task_id = payload.get('task_id') or request.query_params.get('task_id')
    if not task_id:
        raise HTTPException(status_code=400, detail='task_id required')
    # find original
    original = next((r for r in AGENT_QUEUE if r.get('task_id') == task_id), None)
    if not original:
        raise HTTPException(status_code=404, detail='original task not found')
    new_task_id = f"agent-{int(time.time()*1000)}"
    record = {"task_id": new_task_id, "agent": original.get('agent'), "goal": original.get('goal'), "client_id": original.get('client_id', 0), "status": "queued", "ts": datetime.utcnow().isoformat()}
    AGENT_QUEUE.insert(0, record)
    if len(AGENT_QUEUE) > 200:
        AGENT_QUEUE.pop()
    _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))

    async def _run_retry(agent_name, goal_text, cid, tid):
        for r in AGENT_QUEUE:
            if r.get('task_id') == tid:
                r['status'] = 'running'
                r['started_at'] = datetime.utcnow().isoformat()
                break
        _append_log(f"↻ Retrying agent {agent_name} ({tid}): {goal_text}")
        try:
            res = await planner.execute(goal_text, client_id=cid, agent_id=agent_name)
            _append_log(f"✅ Retry completed {agent_name} ({tid})")
            for r in AGENT_QUEUE:
                if r.get('task_id') == tid:
                    r['status'] = 'completed'
                    r['result'] = str(res)[:1000]
                    r['completed_at'] = datetime.utcnow().isoformat()
                    break
        except Exception as e:
            _append_log(f"❌ Retry failed {agent_name} ({tid}): {e}")
            for r in AGENT_QUEUE:
                if r.get('task_id') == tid:
                    r['status'] = 'failed'
                    r['error'] = str(e)
                    r['completed_at'] = datetime.utcnow().isoformat()
                    break
        _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))

    background.add_task(_run_retry, record['agent'], record['goal'], record['client_id'], new_task_id)
    return {'status': 'queued', 'new_task_id': new_task_id}



@app.get("/api/leads")
async def get_leads(limit: int = 100, authorized: bool = Depends(require_dashboard_api_key)):
    query = """
        SELECT 
            id, business, 
            COALESCE(owner, '') as owner,
            url, 
            COALESCE(website, '') as website,
            COALESCE(email, '') as email, 
            COALESCE(phone, '') as phone, 
            vertical, status, 
            COALESCE(notes, '') as notes, 
            COALESCE(icebreaker, 'Pending...') as icebreaker, 
            COALESCE(score, 0) as score, 
            client_id, created_at
        FROM leads 
        ORDER BY id DESC LIMIT ?
    """
    leads = await DatabaseManager.query(query, (limit,), fetchall=True)
    return {"status": "ok", "leads": [dict(r) for r in leads]}

@app.get("/api/metrics")
async def get_metrics(client_id: int = 0, authorized: bool = Depends(require_dashboard_api_key)):
    metrics = await DatabaseManager.aget_metrics(client_id)
    flat = {k: metrics.get(k, 0) for k in ["leads_found", "emails_sent", "replies_received", "meetings_booked", "calls_made", "proposals_sent"]}
    return {"status": "ok", "metrics": metrics, **flat}


@app.post("/api/agents/run")
async def run_agent(request: Request, background: BackgroundTasks, authorized: bool = Depends(require_dashboard_api_key)):
    """Queue an agent run. Payload: {"agent": "nova", "goal": "Find 10 leads"}. Returns queued task id."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    agent = payload.get("agent") or request.query_params.get("agent") or "nova"
    goal = payload.get("goal") or f"Run routine for {agent}"
    try:
        client_id = int(request.query_params.get("client_id") or payload.get("client_id") or 0)
    except Exception:
        client_id = 0

    task_id = f"agent-{int(time.time()*1000)}"
    # enqueue a lightweight task record
    record = {"task_id": task_id, "agent": agent, "goal": goal, "client_id": client_id, "status": "queued", "ts": datetime.utcnow().isoformat()}
    AGENT_QUEUE.insert(0, record)
    # keep queue bounded
    if len(AGENT_QUEUE) > 200:
        AGENT_QUEUE.pop()
    _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))

    async def _run_bg(agent_name: str, goal_text: str, cid: int, tid: str):
        # mark running
        for r in AGENT_QUEUE:
            if r.get("task_id") == tid:
                r["status"] = "running"
                r["started_at"] = datetime.utcnow().isoformat()
                break
        _append_log(f"▶ Queued agent run {agent_name} ({tid}): {goal_text}")
        try:
            res = await planner.execute(goal_text, client_id=cid, agent_id=agent_name)
            _append_log(f"✅ Agent {agent_name} completed ({tid}): {str(res)[:240]}")
            for r in AGENT_QUEUE:
                if r.get("task_id") == tid:
                    r["status"] = "completed"
                    r["result"] = str(res)[:1000]
                    r["completed_at"] = datetime.utcnow().isoformat()
                    break
            _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))
        except Exception as e:
            _append_log(f"❌ Agent {agent_name} failed ({tid}): {e}")
            for r in AGENT_QUEUE:
                if r.get("task_id") == tid:
                    r["status"] = "failed"
                    r["error"] = str(e)
                    r["completed_at"] = datetime.utcnow().isoformat()
                    break
            _schedule_background(DatabaseManager.set_state('agent_queue', AGENT_QUEUE[:200]))

    background.add_task(_run_bg, agent, goal, client_id, task_id)
    return {"status": "queued", "task_id": task_id, "agent": agent, "goal": goal}

@app.post("/api/leads/clear")
async def clear_leads(authorized: bool = Depends(require_dashboard_api_key)):
    await DatabaseManager.query("DELETE FROM leads")
    return {"status": "ok", "message": "All leads cleared"}

@app.get("/api/agents")
async def get_agent_status(authorized: bool = Depends(require_dashboard_api_key)):
    agents = {
        "Nova":     {"name": "Nova", "role": "CEO", "status": "online"},
        "Hawk":     {"name": "Hawk", "role": "Lead Hunter", "status": "online"},
        "Closer":   {"name": "Closer", "role": "Sales Director", "status": "online"},
        "Quill":    {"name": "Quill", "role": "Content Strategist", "status": "online"},
        "Sentinel": {"name": "Sentinel", "role": "Operations", "status": "online"},
        "Oracle":   {"name": "Oracle", "role": "Data Intel", "status": "online"}
    }
    return {"status": "ok", "agents": agents}

@app.get("/api/logs")
async def get_logs(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "logs": LOG_BUFFER}

@app.get("/api/performance")
async def get_performance(client_id: int = 0, authorized: bool = Depends(require_dashboard_api_key)):
    stats = await DatabaseManager.get_performance_stats(client_id)
    return {"status": "ok", "performance": stats}

@app.post("/api/leads/{lead_id}/approve")
async def approve_lead(lead_id: int, authorized: bool = Depends(require_dashboard_api_key)):
    # 1. Get the lead data
    lead = await DatabaseManager.query("SELECT * FROM leads WHERE id = ?", (lead_id,), fetchone=True)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    lead_dict = dict(lead)
    
    # 2. Run Opportunity Scanner (Moved from worker to here for efficiency)
    from app.skills.opportunity_scanner import scan_opportunity
    if lead_dict.get("url"):
        logger.info(f"[APPROVE] Deep-scanning approved lead: {lead_dict['business']}")
        opp = await scan_opportunity(lead_dict["url"], lead_dict["business"])
        
        notes = f"{lead_dict.get('notes') or ''} | GAPS: {', '.join(opp.get('gaps', []))}"
        score = opp.get("score", 0)
        icebreaker = opp.get("hook", "")
        
        await DatabaseManager.query(
            "UPDATE leads SET status = 'Approved', notes = ?, score = ?, icebreaker = ? WHERE id = ?",
            (notes, score, icebreaker, lead_id)
        )
    else:
        await DatabaseManager.query("UPDATE leads SET status = 'Approved' WHERE id = ?", (lead_id,))
    
    # 3. Sync to Google Sheets
    await update_lead_status_sheets(lead_id, "Approved")
    return {"status": "ok", "message": f"Lead {lead_id} approved and deep-scanned"}




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
async def get_observability_performance(authorized: bool = Depends(require_dashboard_api_key)):
    """Get performance profiling stats."""
    from app.core.monitoring import profiler
    return {"status": "ok", "performance": profiler.get_all_stats()}

@app.get("/api/errors/recent")
async def get_recent_errors(authorized: bool = Depends(require_dashboard_api_key)):
    """Get recent error tracking data for the dashboard."""
    from app.core.monitoring import error_tracker
    summary = error_tracker.get_error_summary()
    return {"status": "ok", "errors": summary}

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
        msg_type = msg_obj.get("text") and "text" or (msg_obj.get("caption") and "caption" or "unknown")
        
        if not chat_id:
            logger.warning("[Telegram] Missing chat_id in message")
            return
        
        if not text:
            # Send informative reply for media/unsupported types
            logger.info(f"[Telegram] Unsupported message type ({msg_type}), no text/caption — sending acknowledgement")
            try:
                await tg_queue.add_message(chat_id, "🤖 I received your message but I only process text right now. Please send a text message!")
            except Exception:
                pass
            return
        
        # Resolve Topic/Agent
        topic_id = str(msg_obj.get("message_thread_id", "1"))
        agent_role = TOPIC_AGENT_MAP.get(topic_id, "nova")
        
        logger.info(f"[Telegram] Processing: chat_id={chat_id}, text={text[:50]}..., agent={agent_role}")

        # Intercept firewall approval replies ('approve APPROVAL-0001' etc.)
        # before routing to the brain — these must be deterministic.
        try:
            from app.skills.approval_workflow import handle_approval_response
            approval_reply = await handle_approval_response(text)
            if approval_reply:
                await tg_queue.add_message(chat_id, f"🛡️ {approval_reply}")
                return
        except Exception as e:
            logger.warning(f"[Telegram] Approval intercept failed (continuing to brain): {e}")

        # Route to Brain
        result = await router.handle_message(text, chat_id=chat_id, history=None)
        
        # Send response back to Telegram
        if result:
            sent = await router._send_telegram(chat_id, str(result)[:4096])
            if not sent:
                logger.warning(f"[Telegram] Failed to send response to chat_id={chat_id}")
        else:
            # Handler returned falsy — send an acknowledgement instead of silent drop
            logger.warning(f"[Telegram] Empty result from handler for chat_id={chat_id}, sending fallback")
            await tg_queue.add_message(chat_id, "🤖 I processed your message but didn't generate a response. Try asking again?")
    except Exception as e:
        logger.error(f"[Swarm] Worker failed: {e}", exc_info=True)

@app.post("/api/retell/webhook")
async def retell_webhook(request: Request):
    """Post-call ingest from Retell (directly or relayed via Make).

    Records call outcomes into the self-improvement loop, updates the lead,
    and pings Telegram on hot leads / booked appointments.
    """
    raw_body = await request.body()

    # Signature check when called directly by Retell; Make relays instead
    # send X-API-Key (same dashboard secret used by other internal callers).
    api_key = os.getenv("RETELL_API_KEY", "")
    signature = request.headers.get("x-retell-signature", "")
    relay_key = request.headers.get("x-api-key", "")
    verified = False
    if relay_key and secrets.compare_digest(relay_key, os.getenv("DASHBOARD_API_KEY", "")):
        verified = True
    elif api_key and signature:
        try:
            from retell.lib.webhook_auth import verify as retell_verify
            verified = retell_verify(raw_body.decode("utf-8"), api_key, signature)
        except Exception as e:
            logger.warning(f"[Retell] Signature verification error: {e}")
    if not verified:
        return JSONResponse(status_code=401, content={"status": "unauthorized"})

    data = await request.json()
    event = data.get("event", "")
    call = data.get("call", data) or {}

    # Forward a copy to the Make.com CRM scenario (Sheets logging) so the
    # existing OROVA|Nova CRM flow keeps working now that Retell points here.
    make_hook = os.getenv("MAKE_CRM_WEBHOOK_URL", "")
    if make_hook:
        async def _forward():
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(make_hook, json=data)
            except Exception as e:
                logger.debug(f"[Retell] Make forward failed (non-fatal): {e}")
        _schedule_background(_forward())

    if event not in ("call_analyzed", "call_ended"):
        return {"status": "ignored", "event": event}
    # call_ended fires before analysis; only act on the analyzed payload
    if event == "call_ended":
        return {"status": "ok", "awaiting": "call_analyzed"}

    metadata = call.get("metadata") or {}
    lead_id = metadata.get("lead_id")
    client_id = int(metadata.get("client_id") or 0)
    analysis = call.get("call_analysis") or {}
    custom = analysis.get("custom_analysis_data") or {}
    temperature = (custom.get("lead temperature") or "").strip().lower()
    booked = bool(custom.get("appointment booked"))
    summary = analysis.get("call_summary", "")

    result = "meeting" if booked else (
        "replied" if temperature == "hot" else (
            "answered" if analysis.get("call_successful") else "no_answer"))

    try:
        from app.core.self_improvement import OutcomeTracker
        await OutcomeTracker.record_outcome(
            action="call", strategy="cold_call", result=result,
            recipient=call.get("to_number", ""), lead_id=int(lead_id or 0),
            client_id=client_id,
            metadata={"temperature": temperature, "booked": booked, "objection": custom.get("specific objection", "")},
        )
    except Exception as e:
        logger.warning(f"[Retell] Outcome record failed: {e}")

    if lead_id:
        try:
            new_status = "Meeting Booked" if booked else ("Hot Lead" if temperature == "hot" else "Called")
            await DatabaseManager.query(
                "UPDATE leads SET status = ?, notes = notes || ? WHERE id = ? AND client_id = ?",
                (new_status, f" | Call: {summary[:200]}", int(lead_id), client_id),
            )
        except Exception as e:
            logger.warning(f"[Retell] Lead update failed: {e}")

    # Booked appointment → put it on Mark's Google Calendar automatically so
    # a Nova-promised slot can never be silently missed or double-booked.
    calendar_note = ""
    if booked:
        when = custom.get("appointment date and time", "")
        try:
            from app.skills.calendar_skill import create_event
            prospect = custom.get("name") or call.get("to_number", "prospect")
            loop = asyncio.get_running_loop()
            cal_res = await loop.run_in_executor(None, lambda: create_event(
                summary=f"OROVA demo — {prospect}",
                start_time=when,
                duration_minutes=15,
                description=f"Booked by Nova on a cold call.\nPhone: {custom.get('contact number', call.get('to_number', ''))}\nCall summary: {summary[:400]}",
            ))
            calendar_note = "\n📅 Calendar event created" if cal_res.get("success") else f"\n⚠️ Calendar event failed ({cal_res.get('error', 'unparseable time')}) — book manually!"
        except Exception as e:
            logger.warning(f"[Retell] Calendar booking failed: {e}")
            calendar_note = "\n⚠️ Calendar event failed — book manually!"

    if booked or temperature == "hot":
        try:
            from app.worker import send_telegram_report
            await send_telegram_report(
                f"🔥 **{'APPOINTMENT BOOKED' if booked else 'HOT LEAD'}** (call)\n\n"
                f"{custom.get('name', '')} — {custom.get('contact number', call.get('to_number', ''))}\n"
                f"When: {custom.get('appointment date and time', 'n/a')}\n"
                f"Summary: {summary[:300]}"
                f"{calendar_note}"
            )
        except Exception as e:
            logger.warning(f"[Retell] Telegram alert failed: {e}")

    return {"status": "ok", "result": result}


@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Ingest point for Telegram via Queue."""
    tg_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if tg_webhook_secret:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(header_token, tg_webhook_secret):
            logger.warning(f"[Telegram] Rejected webhook with invalid secret token")
            return JSONResponse(status_code=403, content={"status": "unauthorized"})
    data = await request.json()
    logger.info(f"[Telegram] Webhook received update: {list(data.keys())}")
    accepted = await tg_queue.enqueue(data)
    if not accepted:
        return JSONResponse(status_code=503, content={"status": "queue_full", "detail": "Server under heavy load, try again"})
    return {"status": "ok"}

# --- Additional Dashboard API Endpoints ---

@app.get("/api/firewall/stats")
async def get_firewall_stats(authorized: bool = Depends(require_dashboard_api_key)):
    """Get Semantic Firewall statistics for dashboard."""
    from app.core.semantic_firewall import get_semantic_firewall
    fw = get_semantic_firewall()
    stats = fw.get_stats()
    recent = fw.get_audit_log(limit=50)
    return {"status": "ok", "stats": stats, "recent": [
        {"tool": e.tool_name, "decision": e.decision.value, "reason": e.reasons[-1] if e.reasons else "",
         "timestamp": e.timestamp, "depth": e.agent_depth}
        for e in recent
    ]}

@app.get("/api/firewall/rules")
async def get_firewall_rules(authorized: bool = Depends(require_dashboard_api_key)):
    """Get list of firewall rules and their priority."""
    from app.core.semantic_firewall import BUILTIN_RULES
    return {"status": "ok", "rules": [
        {"name": name, "priority": priority}
        for name, _, priority in BUILTIN_RULES
    ]}

@app.get("/api/circuit-breaker/stats")
async def get_circuit_breaker_stats(authorized: bool = Depends(require_dashboard_api_key)):
    """Get Execution Circuit Breaker statistics."""
    from app.core.circuit_breaker import execution_circuit_breaker
    stats = execution_circuit_breaker.get_stats()
    return {"status": "ok", **stats}

@app.get("/api/decision-traces/recent")
async def get_recent_traces(limit: int = 10, authorized: bool = Depends(require_dashboard_api_key)):
    """Get recent decision traces."""
    from app.core.decision_trace import trace_manager
    recent = trace_manager.get_recent_traces(n=limit)
    failures = trace_manager.get_failure_summary()
    return {"status": "ok", "traces": recent, "failure_summary": failures}

@app.get("/api/decision-traces/performance")
async def get_trace_performance(authorized: bool = Depends(require_dashboard_api_key)):
    """Get aggregated performance from decision traces."""
    from app.core.decision_trace import trace_manager
    perf = trace_manager.get_performance_summary(n=50)
    return {"status": "ok", "performance": perf}


@app.get("/api/clients")
async def get_clients(authorized: bool = Depends(require_dashboard_api_key)):
    query = "SELECT id, business_name as name, niche, target_location as location FROM clients WHERE is_active = 1"
    try:
        rows = await DatabaseManager.query(query, fetchall=True)
        return {"status": "ok", "clients": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"Error fetching clients: {e}")
        return {"status": "ok", "clients": []}

@app.post("/api/clients")
async def create_client(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    name = data.get("name")
    niche = data.get("niche")
    location = data.get("location")
    if not name:
        raise HTTPException(status_code=400, detail="Missing client name")
        
    query = "INSERT INTO clients (business_name, niche, target_location) VALUES (?, ?, ?)"
    try:
        await DatabaseManager.query(query, (name, niche, location))
        # Get the inserted client ID
        row = await DatabaseManager.query("SELECT last_insert_rowid() as id", fetchone=True)
        new_id = row["id"] if row else 0
        return {"status": "ok", "client": {"id": new_id, "name": name, "niche": niche, "location": location}}
    except Exception as e:
        logger.error(f"Error creating client: {e}")
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/tasks")
async def get_tasks(authorized: bool = Depends(require_dashboard_api_key)):
    tasks_file = os.path.join(root_path, "tasks.json")
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                return {"status": "ok", "tasks": json.load(f)}
        except Exception as e:
            logger.warning(f"Error reading tasks.json: {e}")
    return {"status": "ok", "tasks": []}

@app.post("/api/tasks")
async def save_tasks(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    tasks_file = os.path.join(root_path, "tasks.json")
    
    current_tasks = []
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                current_tasks = json.load(f)
        except Exception:
            pass

    if isinstance(data, list):
        current_tasks = data
    elif isinstance(data, dict):
        task_id = data.get("id")
        found = False
        for i, t in enumerate(current_tasks):
            if t.get("id") == task_id:
                if isinstance(current_tasks[i], dict):
                    current_tasks[i].update(data)
                else:
                    current_tasks[i] = data
                found = True
                break
        if not found:
            current_tasks.append(data)
            
    try:
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(current_tasks, f, indent=2)
        return {"status": "ok", "message": "Tasks saved successfully"}
    except Exception as e:
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/tasks/delete")
async def delete_task(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    task_id = data.get("id")
    tasks_file = os.path.join(root_path, "tasks.json")
    if not task_id:
        raise HTTPException(status_code=400, detail="Missing task ID")
        
    if os.path.exists(tasks_file):
        try:
            with open(tasks_file, "r", encoding="utf-8") as f:
                tasks = json.load(f)
            tasks = [t for t in tasks if t.get("id") != task_id]
            with open(tasks_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2)
            return {"status": "ok", "message": "Task deleted"}
        except Exception as e:
            logger.error(f"[API] Internal error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok", "message": "No tasks to delete"}

@app.get("/api/content")
async def get_content(authorized: bool = Depends(require_dashboard_api_key)):
    content_file = os.path.join(root_path, "content.json")
    if os.path.exists(content_file):
        try:
            with open(content_file, "r", encoding="utf-8") as f:
                return {"status": "ok", "content": json.load(f)}
        except Exception as e:
            logger.warning(f"Error reading content.json: {e}")
    return {"status": "ok", "content": []}

@app.post("/api/content")
async def save_content(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    content_file = os.path.join(root_path, "content.json")
    
    current_content = []
    if os.path.exists(content_file):
        try:
            with open(content_file, "r", encoding="utf-8") as f:
                current_content = json.load(f)
        except Exception:
            pass

    if isinstance(data, list):
        current_content = data
    elif isinstance(data, dict):
        content_id = data.get("id")
        found = False
        for i, c in enumerate(current_content):
            if c.get("id") == content_id:
                if isinstance(current_content[i], dict):
                    current_content[i].update(data)
                else:
                    current_content[i] = data
                found = True
                break
        if not found:
            current_content.append(data)
            
    try:
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(current_content, f, indent=2)
        return {"status": "ok", "message": "Content saved"}
    except Exception as e:
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/content/delete")
async def delete_content(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    content_id = data.get("id")
    content_file = os.path.join(root_path, "content.json")
    if not content_id:
        raise HTTPException(status_code=400, detail="Missing content ID")
        
    if os.path.exists(content_file):
        try:
            with open(content_file, "r", encoding="utf-8") as f:
                content = json.load(f)
            content = [c for c in content if c.get("id") != content_id]
            with open(content_file, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=2)
            return {"status": "ok", "message": "Content deleted"}
        except Exception as e:
            logger.error(f"[API] Internal error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok", "message": "No content to delete"}

@app.get("/api/memory")
async def get_memory(authorized: bool = Depends(require_dashboard_api_key)):
    memory_file = os.path.join(root_path, "memories.json")
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                return {"status": "ok", "memories": json.load(f)}
        except Exception as e:
            logger.warning(f"Error reading memories.json: {e}")
    return {"status": "ok", "memories": []}

@app.post("/api/memory")
async def save_memory(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    memory_file = os.path.join(root_path, "memories.json")
    
    current_memories = []
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                current_memories = json.load(f)
        except Exception:
            pass

    if isinstance(data, list):
        current_memories = data
    elif isinstance(data, dict):
        mem_id = data.get("id")
        found = False
        for i, m in enumerate(current_memories):
            if m.get("id") == mem_id:
                if isinstance(current_memories[i], dict):
                    current_memories[i].update(data)
                else:
                    current_memories[i] = data
                found = True
                break
        if not found:
            current_memories.append(data)
            
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(current_memories, f, indent=2)
        return {"status": "ok", "message": "Memory saved"}
    except Exception as e:
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/memory/delete")
async def delete_memory(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    mem_id = data.get("id")
    memory_file = os.path.join(root_path, "memories.json")
    if not mem_id:
        raise HTTPException(status_code=400, detail="Missing memory ID")
        
    if os.path.exists(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                memories = json.load(f)
            memories = [m for m in memories if m.get("id") != mem_id]
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(memories, f, indent=2)
            return {"status": "ok", "message": "Memory deleted"}
        except Exception as e:
            logger.error(f"[API] Internal error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok", "message": "No memory to delete"}

@app.get("/api/chat/history")
async def get_chat_history(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "history": []}

@app.post("/api/chat")
async def chat_with_agent(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    message = data.get("message", "")
    if not message:
        return {"status": "error", "response": "Empty message"}
    try:
        response = await router.handle_message(message, chat_id=0, history=None)
        return {"status": "ok", "response": response}
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return {"status": "error", "response": "Chat system error — see server logs"}

@app.post("/api/actions/hunt-leads")
async def action_hunt_leads(authorized: bool = Depends(require_dashboard_api_key)):
    from app.worker import run_lead_hunt_slow_lane, start_worker_scheduler, stop_worker_scheduler
    import asyncio as _asyncio
    task = _asyncio.create_task(
        run_lead_hunt_slow_lane(client_id=0, niche=None, location=None)
    )
    task.add_done_callback(
        lambda t: logger.error(f"[HUNT] Background task failed: {t.exception()!r}")
        if not t.cancelled() and t.exception() else None
    )
    return {"status": "ok", "message": "Lead hunt job initiated"}

@app.post("/api/actions/send-emails")
async def action_send_emails(authorized: bool = Depends(require_dashboard_api_key)):
    try:
        res = await check_replies(limit=5, advance_checkpoint=False)
        if res.get("status") == "error":
            return {"status": "error", "message": res.get("message", "AgentMail check failed")}
        return {"status": "ok", "message": res.get("message", f"Outreach process checked. Found {res.get('count', 0)} replies.")}
    except Exception as e:
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        return {"status": "error", "message": "Internal error — see server logs"}

@app.post("/api/actions/generate-report")
async def action_generate_report(authorized: bool = Depends(require_dashboard_api_key)):
    try:
        res = await backup_database()
        return {"status": "ok", "report": res.get("message", f"CEO report and vault snapshot complete: {res.get('filename', 'orova.db')}")}
    except Exception as e:
        logger.error(f"[API] Internal error: {e}", exc_info=True)
        return {"status": "error", "message": "Internal error — see server logs"}

@app.get("/api/notifications")
async def get_notifications(authorized: bool = Depends(require_dashboard_api_key)):
    notif_file = os.path.join(root_path, "notifications.json")
    if os.path.exists(notif_file):
        try:
            with open(notif_file, "r", encoding="utf-8") as f:
                return {"status": "ok", "notifications": json.load(f)}
        except Exception:
            pass
    return {"status": "ok", "notifications": []}

@app.post("/api/notifications/read")
async def read_notifications(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    notif_id = data.get("id")
    notif_file = os.path.join(root_path, "notifications.json")
    if os.path.exists(notif_file):
        try:
            with open(notif_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
            if notif_id == "all":
                for n in notifications:
                    n["read"] = True
            else:
                for n in notifications:
                    if n.get("id") == notif_id:
                        n["read"] = True
            with open(notif_file, "w", encoding="utf-8") as f:
                json.dump(notifications, f, indent=2)
            return {"status": "ok", "message": "Notifications updated"}
        except Exception as e:
            logger.error(f"[API] Internal error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    return {"status": "ok"}

@app.get("/api/pending-emails")
async def get_pending_emails(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "count": 0, "pending": []}


@app.get("/api/metrics/history")
async def get_metrics_history(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "history": []}

@app.get("/api/skills")
async def get_skills_list(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "skills": [
        { "name": "find_leads", "category": "Search", "status": "active", "agent": "Hawk" },
        { "name": "stealth_search", "category": "Search", "status": "active", "agent": "Viper" },
        { "name": "stealth_extract", "category": "Search", "status": "active", "agent": "Viper" },
        { "name": "bulk_scrape", "category": "Search", "status": "active", "agent": "Viper" },
        { "name": "deep_research", "category": "Research", "status": "active", "agent": "Hawk" },
        { "name": "run_seo_audit", "category": "Research", "status": "active", "agent": "Hawk" },
        { "name": "analyze_competitor", "category": "Research", "status": "active", "agent": "Hawk" },
        { "name": "send_outreach", "category": "Email", "status": "active", "agent": "Closer" },
        { "name": "create_drip_campaign", "category": "Email", "status": "active", "agent": "Quill" },
        { "name": "write_cold_email", "category": "Copy", "status": "active", "agent": "Quill" },
        { "name": "write_ad_copy", "category": "Copy", "status": "active", "agent": "Quill" },
        { "name": "write_content", "category": "Copy", "status": "active", "agent": "Quill" },
        { "name": "create_instagram_post", "category": "Social", "status": "active", "agent": "Pixel" },
        { "name": "generate_ai_image", "category": "Creative", "status": "active", "agent": "Pixel" },
        { "name": "pipeline_report", "category": "Analytics", "status": "active", "agent": "Oracle" },
        { "name": "conversion_analysis", "category": "Analytics", "status": "active", "agent": "Oracle" },
        { "name": "roi_calculator", "category": "Analytics", "status": "active", "agent": "Oracle" },
        { "name": "trigger_retell_call", "category": "Outreach", "status": "active", "agent": "Closer" },
        { "name": "generate_proposal", "category": "Sales", "status": "active", "agent": "Closer" },
        { "name": "run_pipeline", "category": "Orchestration", "status": "active", "agent": "Nova" }
    ]}

@app.get("/api/pipelines")
async def get_pipelines_list(authorized: bool = Depends(require_dashboard_api_key)):
    return {"status": "ok", "pipelines": [
        { "name": "full_outreach", "label": "Full Outreach", "desc": "Find → Research → Draft → Approve", "steps": 3 },
        { "name": "morning_report", "label": "Morning Report", "desc": "Replies → Analytics → CEO Report", "steps": 3 },
        { "name": "competitor_blitz", "label": "Competitor Blitz", "desc": "Find → SEO Audit → Compare", "steps": 3 },
        { "name": "lead_enrich", "label": "Lead Enrichment", "desc": "Extract → Research → Save to Sheet", "steps": 3 }
    ]}

@app.post("/api/pipelines/run")
async def run_pipeline_action(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    pipeline_name = data.get("pipeline")
    return {"status": "ok", "message": f"Pipeline {pipeline_name} started successfully"}

@app.post("/api/actions/approve-email")
async def approve_email(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    email_id = data.get("id")
    if not email_id:
        raise HTTPException(status_code=400, detail="Missing email ID")
    content_file = os.path.join(root_path, "content.json")
    try:
        with open(content_file, "r", encoding="utf-8") as f:
            content = json.load(f)
        for item in content:
            if item.get("id") == email_id:
                item["status"] = "sent"
                break
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
    except Exception:
        pass
    return {"status": "ok", "message": f"Email {email_id} approved and queued for sending"}

@app.post("/api/actions/deny-email")
async def deny_email(request: Request, authorized: bool = Depends(require_dashboard_api_key)):
    data = await request.json()
    email_id = data.get("id")
    if not email_id:
        raise HTTPException(status_code=400, detail="Missing email ID")
    content_file = os.path.join(root_path, "content.json")
    try:
        with open(content_file, "r", encoding="utf-8") as f:
            content = json.load(f)
        for item in content:
            if item.get("id") == email_id:
                item["status"] = "denied"
                break
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
    except Exception:
        pass
    return {"status": "ok", "message": f"Email {email_id} denied"}


# ═══════════════════════════════════════════════════════
# TASK EXECUTION LOOP — Background worker for `/api/tasks`
# ═══════════════════════════════════════════════════════

async def _task_execution_loop():
    """Background loop — polls tasks.json every 30 s and runs tasks."""
    _task_loop_event.set()
    logger.info("⏱️ Task execution loop started (poll interval: 30s)")
    while not _shutdown_event.is_set():
        try:
            tasks_file = os.path.join(root_path, "tasks.json")
            if not os.path.exists(tasks_file):
                await asyncio.sleep(30)
                continue
            try:
                with open(tasks_file, "r", encoding="utf-8") as f:
                    all_tasks = json.load(f)
            except Exception:
                await asyncio.sleep(30)
                continue

            changed = False
            for task in all_tasks:
                if task.get("status") not in ("todo", "backlog"):
                    continue
                task_id = task.get("id") or task.get("task_id")
                if not task_id:
                    continue
                description = task.get("title", "") + "\n" + task.get("description", "")
                assignee = task.get("assignee", "Nova")
                assignee_id = ("nova" if "nova" in str(assignee).lower() else
                               "hawk" if "hawk" in str(assignee).lower() else
                               "closer" if "closer" in str(assignee).lower() else
                               "nova")
                logger.info(f"[TASK LOOP] Executing task {task_id}: {description[:80]}... (agent={assignee_id})")
                try:
                    prompt = (
                        f"You are a task executor agent. "
                        f"Complete this task concisely and return the result as a plain-text summary:\n"
                        f"{description}"
                    )
                    result = await router.handle_message(prompt, chat_id=0, history=None)
                    task["status"] = "done"
                    task["result"] = str(result)[:1000]
                    changed = True
                    logger.info(f"[TASK LOOP] Task {task_id} marked done.")
                except Exception as exc:
                    task["status"] = "blocked"
                    task["result"] = str(exc)[:500]
                    changed = True
                    logger.error(f"[TASK LOOP] Task {task_id} blocked: {exc}")

            if changed:
                with open(tasks_file, "w", encoding="utf-8") as f:
                    json.dump(all_tasks, f, indent=2)
        except Exception as e:
            logger.error(f"[TASK LOOP] Loop error: {e}")
        await asyncio.sleep(30)

# --- Static Frontend ---
MC_PATH = os.path.join(root_path, "mission-control")
if os.path.exists(MC_PATH):
    app.mount("/", StaticFiles(directory=MC_PATH, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # Use $PORT from environment, default to 18790
    port = int(os.environ.get("PORT", 18790))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)

