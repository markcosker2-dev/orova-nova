import schedule
import datetime
import asyncio
import logging
import os
import sys
import json
import signal
import requests
import socket
import sqlite3
import threading
import queue
import schedule
import datetime
import asyncio
import logging
import os
import sys
import json
import signal
import requests
import socket
import sqlite3
import threading
import queue
from collections import deque
import time

# 🚀 [HOTFIX 9] Proxy Purge
for var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]:
    if var in os.environ:
        del os.environ[var]
load_dotenv()

# Prevent "event loop already running" errors in Telegram + FastAPI
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, PicklePersistence
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import queue

# Health check server for Render keep-alive and dashboard API
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 1. Standard Health Check
        if self.path == '/healthz':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK - OROVA is alive')
        
        # 2. Sentinel Health API
        elif self.path == '/api/health':
            try:
                from app.services.sentinel import HEALTH_FILE
                if os.path.exists(HEALTH_FILE):
                    with open(HEALTH_FILE, "r") as f:
                        data = f.read()
                else:
                    data = json.dumps({"status": "warming_up"})
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        # 3. Approvals API
        elif self.path == '/api/approvals':
            try:
                from app.skills.approval_workflow import _pending_approvals
                data = json.dumps(_pending_approvals, default=str)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(data.encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

        # 4. Static Dashboard Server
        else:
            base_dir = os.path.join(os.getcwd(), "mission-control")
            file_path = self.path[1:] if self.path.startswith("/") else self.path
            if not file_path or file_path == "/":
                file_path = "index.html"
            
            full_path = os.path.join(base_dir, file_path)
            if os.path.exists(full_path) and os.path.isfile(full_path):
                self.send_response(200)
                if file_path.endswith(".html"): self.send_header('Content-type', 'text/html')
                elif file_path.endswith(".css"): self.send_header('Content-type', 'text/css')
                elif file_path.endswith(".js"): self.send_header('Content-type', 'text/javascript')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(full_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()

    def do_POST(self):
        if self.path == '/api/approvals':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                params = json.loads(post_data)
                request_id = params.get("id")
                decision = params.get("decision")
                from app.skills.approval_workflow import handle_approval_response
                asyncio.run(handle_approval_response(f"{decision} {request_id}"))
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def start_health_server():
    from app.services.sentinel import sentinel
    def run_sentinel():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(sentinel.start_monitoring())
    threading.Thread(target=run_sentinel, daemon=True).start()
    try:
        server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
        server.serve_forever()
    except Exception: pass

# Sequential Task Queue - prevents OOM crashes on Render Free Tier
class SequentialTaskQueue:
    def __init__(self):
        self.running_tasks = set()
        self.task_lock = threading.Lock()

    def can_run_task(self, task_name: str) -> bool:
        with self.task_lock:
            # Task logic here (omitted for brevity but kept in file)
            scraper_tasks = {"scraper", "scrapling_scraper", "lead_finder"}
            ads_tasks = {"meta_ads_monitor", "meta_ads_agent"}
            invoicer_tasks = {"invoicer", "cashclaw_invoice"}
            task_groups = {"scraping": scraper_tasks, "ads": ads_tasks, "invoicing": invoicer_tasks}
            task_group = next((g for g, ts in task_groups.items() if task_name in ts), None)
            if not task_group: return True
            return len(self.running_tasks.intersection(task_groups[task_group])) == 0

# Global instances
task_queue = SequentialTaskQueue()

# Start health server in background
health_thread = threading.Thread(target=start_health_server, daemon=True)
health_thread.start()

# Add app and parent paths for modular imports
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
parent_path = os.path.dirname(root_path)
sys.path.insert(0, root_path)
sys.path.insert(0, parent_path)

from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner
from app.core.router import Router
from app.core.database import DatabaseManager
from app.skills.lead_finder import find_leads
from app.skills.agentmail_skill import send_outreach, check_replies
from app.skills.calendar_skill import create_event as create_calendar_event
from app.core.signal_protocol import (
    send_revenue_alert, send_mission_pulse, send_critical_exception,
    send_initialization_pulse, run_mission_pulse, set_chat_id, generate_pulse_metrics
)
from app.core.luxury_filter import LuxuryFilter, critique_and_rewrite
from app.skills.definitions import TOOLS
from app.core.hawk import HAWK
from app.core.cashclaw_bridge import CashClawBridge
from app.skills.sheets_skill import GoogleSheetsCommandCenter
def load_vertical(name):
    """Load vertical config by name."""
    v = {"LuxuryRemodeling": {"industry": "Home Remodeling", "clv_range": "$10,000-$50,000"},
         "Automotive": {"industry": "Automotive", "clv_range": "$5,000-$25,000"},
         "HVAC": {"industry": "HVAC Services", "clv_range": "$3,000-$15,000"},
         "Roofing": {"industry": "Roofing", "clv_range": "$5,000-$30,000"}}
    sl = v.get(name, {"industry": name, "clv_range": "$5,000+"})
    return {"vertical_name": name, "scoring_logic": sl}

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Components ---
# [Manager] Load active vertical from ENV or default
VERTICAL_NAME = os.getenv("VERTICAL_NAME", "Automotive").strip()
logger.info(f"ðŸ” DEBUG: VERTICAL_NAME={repr(VERTICAL_NAME)}")

try:
    vertical_config = load_vertical(VERTICAL_NAME)
    logger.info(f"âœ… Loaded Vertical Config: {VERTICAL_NAME}")
except Exception as e:
    logger.error(f"âŒ Failed to load vertical: {e}")
    vertical_config = {"vertical_name": "Fallback"}

ai_client = UnifiedAIClient()
planner = TaskPlanner(ai_client, config=vertical_config)  # Inject Config
router = Router(planner, lead_hunter=find_leads)

# Initialize HAWK persona and business layer
hawk = HAWK()
cashclaw_bridge = CashClawBridge(vertical_config)
sheets_command_center = GoogleSheetsCommandCenter(vertical_config)

# Set CashClaw bridge in the skill module
from app.skills import cashclaw_skill
cashclaw_skill.set_cashclaw_bridge(cashclaw_bridge)

# â”€â”€ Toxic Response Filter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_TOXIC_PHRASES = [
    "tools are dead", "tools are down", "apis are down",
    "system is down", "completely down", "currently offline",
    "experiencing technical", "experiencing system", "system failure",
    "currently down", "not working", "not functioning",
    "will retry", "retry later", "try again later",
    "manual retry", "will need manual",
    "hand me", "share a link", "send me a", "provide me with",
    "qualified remodeler", "top 500", "top 550",
    ".pdf", "pdf or", "pdf file",
    "i can't access", "i don't have access",
    "maps is locked", "bypassing",
    "capabilities are offline", "functions are broken",
    "both send and receive", "email capabilities",
    "cannot be sent", "unable to send",
    "no test email can", "cannot send",
]

def _is_toxic(text: str) -> bool:
    """Check if text contains banned phrases."""
    lower = text.lower()
    return any(p in lower for p in _TOXIC_PHRASES)

def _sanitize_history(history: list) -> list:
    """Remove messages containing toxic/hallucinated content from history."""
    clean = []
    for msg in history:
        content = msg.get("content", "")
        if content and _is_toxic(content):
            # Replace toxic assistant messages with a neutral placeholder
            if msg.get("role") == "assistant":
                clean.append({"role": "assistant", "content": "Searching for results..."})
            # Drop toxic user messages entirely
        else:
            # Keep all clean messages
            clean.append(msg)
    return clean



# GLOBAL DICTIONARY TO STORE PENDING CALLS (TTL-pruned, see _prune_pending)
pending_calls = {}
_PENDING_TTL_SECONDS = 3600  # 1 hour expiry for pending approvals

# Auto-detect Mark's chat ID (fallback if PERSONAL_CHAT_ID not set)
_CEO_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or None

def _get_ceo_chat_id():
    """Get CEO's chat ID with auto-detection fallback."""
    global _CEO_CHAT_ID
    if not _CEO_CHAT_ID:
        # Final fallback: search env for any ID if specific keys are missing
        _CEO_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    return _CEO_CHAT_ID

# --- Telegram Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['history'] = []
    # Auto-detect CEO chat ID
    set_chat_id(str(update.effective_chat.id))
    # MSI-compliant initialization
    try:
        leads = DatabaseManager.get_leads(0)
        verticals = len(set(l.get('vertical', '') for l in leads if l.get('vertical')))
        send_initialization_pulse(len(leads), max(verticals, 1))
    except Exception:
        pass
    await update.message.reply_text(
        "Nova is online. All systems nominal.\n"
        "Awaiting your first directive or standing by for autonomous operation."
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes memory."""
    context.user_data['history'] = []
    await update.message.reply_text("ðŸ§  **Memory Wiped.** Fresh start.")

async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the Mission Control dashboard URL."""
    # Priority: Render URL > SPACE_ID (HuggingFace) > EC2 > localhost
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if render_url:
        url = render_url
    elif os.environ.get("SPACE_ID"):
        user_name = os.environ.get("SPACE_ID").replace("/", "-").lower()
        url = f"https://{user_name}.hf.space"
    else:
        url = "https://orova-nova.onrender.com"
        
    await update.message.reply_text(
        f"ðŸ¢ **OROVA Mission Control**\n\n"
        f"ðŸ”— {url}\n\n"
        f"6 screens: Task Board â€¢ Content Pipeline â€¢ Calendar â€¢ Memory Bank â€¢ Team Structure â€¢ Digital Office"
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the weekly CEO Pulse report."""
    from app.skills.perf_dashboard import generate_weekly_report
    report = generate_weekly_report()
    await update.message.reply_text(report)

async def handle_call_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles YES/NO button clicks for calls."""
    query = update.callback_query
    await query.answer()
    
    call_id = query.data
    if call_id.startswith("approve_"):
        cid = call_id.replace("approve_", "")
        if cid in pending_calls:
            data = pending_calls[cid]
            from app.services.call_manager import execute_call
            await query.edit_message_text(f"â³ **Initiating call to {data['name']}...**")
            
            retell_id = await execute_call(data['phone'], data['name'], data['script'])
            if retell_id:
                await query.edit_message_text(f"âœ… **Call Connected!**\nID: `{retell_id}`\nScript: _{data['script']}_")
            else:
                await query.edit_message_text("âŒ **Call failed to connect.** Check Retell logs.")
            del pending_calls[cid]
        else:
            await query.edit_message_text("âš ï¸ **Call expired or not found.**")
    
    elif call_id.startswith("deny_"):
        cid = call_id.replace("deny_", "")
        if cid in pending_calls:
            del pending_calls[cid]
        await query.edit_message_text("ðŸš« **Call cancelled.**")

async def check_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Simulation: Bot checks calendar and asks for call permission."""
    import time
    user_id = update.effective_user.id
    
    # [SIMULATION DATA]
    prospect = "John Doe"
    phone = "+1234567890" 
    meeting_time = "Tomorrow at 2 PM"
    topic = "Lead Generation Strategy"

    await update.message.reply_text("ðŸ” Checking calendar for upcoming meetings...")
    
    from app.services.call_manager import draft_reminder_call
    script = await draft_reminder_call(prospect, meeting_time, topic)

    call_id = str(int(time.time()))
    pending_calls[call_id] = {
        "phone": phone,
        "name": prospect,
        "script": script
    }

    keyboard = [
        [
            InlineKeyboardButton("âœ… YES", callback_data=f"approve_{call_id}"),
            InlineKeyboardButton("âŒ NO", callback_data=f"deny_{call_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = (
        f"ðŸ“… **Upcoming Meeting Detected**\n"
        f"ðŸ‘¤ **Prospect:** {prospect}\n"
        f"â° **Time:** {meeting_time}\n\n"
        f"ðŸ¤– **Proposed Script:**\n"
        f"\"{script}\"\n\n"
        f"**Shall I make this call?**"
    )
    await update.message.reply_text(message, reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _CEO_CHAT_ID
    user_msg = update.message.text
    chat_id = update.effective_chat.id
    logger.info(f"ðŸ“¨ MESSAGE RECEIVED: '{user_msg}' from {chat_id}")
    
    # Auto-detect CEO chat ID from first message
    if not _CEO_CHAT_ID:
        _CEO_CHAT_ID = str(chat_id)
        logger.info(f"ðŸ”‘ Auto-detected CEO chat ID: {_CEO_CHAT_ID}")
    
    # 1. Initialize Memory
    if 'history' not in context.user_data:
        context.user_data['history'] = []
    history = context.user_data['history']

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Quick responses for simple greetings (no AI needed)
    quick_responses = {
        "hello": "ðŸ‘‹ Nova here. What do you need?",
        "hi": "ðŸ‘‹ Boss. Ready.",
        "hey": "ðŸ‘‹ Nova. Go.",
        "howdy": "ðŸ‘‹ Working.",
        "what's up": "âš¡ At your service.",
        "sup": "âš¡ Ready.",
        "good morning": "ðŸŒ… Morning, Boss. What's the mission?",
        "good evening": "ðŸŒ† Evening. Ready to work.",
        "good night": "ðŸŒ™ Resting if you need me. Otherwise, go.",
    }
    user_msg_lower = user_msg.lower().strip()
    if user_msg_lower in quick_responses or user_msg_lower in ["hello", "hi", "hey", "howdy"]:
        await update.message.reply_text(quick_responses.get(user_msg_lower, "âš¡ Here."))
        return

    # --- NATURAL COMMAND PATTERN MATCHING ---
    import re
    
    # 1. Exact "Run luxury remodeling in Miami" pattern
    if re.search(r"run\s+luxury\s+remodeling\s+in\s+miami", user_msg_lower):
        await update.message.reply_text("âœ… Starting luxury remodeling pipeline in Miami.")
        # Call one-click pipeline here
        # await one_click_pipeline.run("luxury remodeling", "Miami")
        return

    # 2. Generic "I want to run [niche] in [location]"
    match = re.search(r"i\s+want\s+to\s+run\s+(.+)\s+in\s+(.+)", user_msg_lower)
    if match:
        niche = match.group(1).strip()
        location = match.group(2).strip()
        await update.message.reply_text(f"âœ… Starting pipeline for '{niche}' in {location}.")
        # await one_click_pipeline.run(niche, location)
        return

    # 3. "Find leads for [niche]"
    match = re.search(r"find\s+leads\s+for\s+(.+)", user_msg_lower)
    if match:
        niche = match.group(1).strip()
        await update.message.reply_text(f"ðŸ” Initiating lead hunt for '{niche}'.")
        # await lead_hunt.start(niche)
        return

    # 4. "Send emails"
    if re.search(r"send\s+emails?", user_msg_lower):
        await update.message.reply_text("âœ‰ï¸ Running email drafter.")
        # await email_drafter.run()
        return

    # 5. "Status"
    if re.search(r"^status$|what'?s?\s+the\s+status|system\s+status", user_msg_lower):
        await update.message.reply_text("ðŸ“Š Fetching system status...")
        # await system_status.report(chat_id)
        return

    # 6. "Stop" / kill switch
    if re.search(r"^stop$|stop\s+(all|everything|jobs?)|kill\s+(all|everything|jobs?)", user_msg_lower):
        await update.message.reply_text("â›” STOPPING ALL SYSTEMS. Kill switch activated.")
        # await scheduler.stop_all()
        return

    # 7. "Pause" scheduler
    if re.search(r"^pause$|pause\s+(scheduler|jobs?)", user_msg_lower):
        await update.message.reply_text("â¸ï¸ Scheduler paused.")
        # await scheduler.pause()
        return

    # 8. "Resume" scheduler
    if re.search(r"^resume$|resume\s+(scheduler|jobs?)|continue", user_msg_lower):
        await update.message.reply_text("â–¶ï¸ Scheduler resumed.")
        # await scheduler.resume()
        return
    
    try:
        # 2. Sanitize history - strip old toxic responses before feeding to AI
        clean_history = _sanitize_history(history)

        # 3. Pass Clean History to Router
        response, updated_history = await router.route(user_msg, chat_id, clean_history, status_callback=None)
        context.user_data['history'] = updated_history
        
        # 4. Only save to history if response is clean
        history.append({"role": "user", "content": user_msg})
        if not _is_toxic(response):
            history.append({"role": "assistant", "content": response})
        else:
            history.append({"role": "assistant", "content": "Searching for results..."})

        # Keep last 10 turns
        if len(history) > 20:
            context.user_data['history'] = history[-20:]

        # Send
        if len(response) > 4000:
            for i in range(0, len(response), 4000):
                await update.message.reply_text(response[i:i+4000])
        else:
            await update.message.reply_text(response)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"âš ï¸ Error: {str(e)}")

# --- Mission Control API + Static Server ---
MC_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mission-control")
DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG_BUFFER = deque(maxlen=100)  # [FIX-1] Bounded deque replaces unbounded list
MAX_LOG_LINES = 100
_LOG_LOCK = threading.Lock()  # Thread safety for LOG_BUFFER
_BOOT_TIME = time.time()  # Track uptime
_ERROR_COUNT = 0  # Track total errors across all jobs

# â”€â”€ Scheduler Config (must be above class definitions) â”€â”€
LEADS_TO_FIND_PER_RUN = 5
HUNT_INTERVAL_MINUTES = 30
APPROVAL_CHECK_MINUTES = 2
EMAIL_DRAFT_INTERVAL_MINUTES = 30
REPLY_CHECK_MINUTES = 30
MAX_RUNS_PER_DAY = 10
daily_counter = 0
last_reset_day = time.strftime("%d")

# â”€â”€ Pending email drafts awaiting CEO approval â”€â”€
pending_emails = {}


def _prune_pending():
    """[FIX-1] Remove expired entries from pending_calls and pending_emails."""
    now = time.time()
    for store in (pending_calls, pending_emails):
        expired = [k for k, v in store.items()
                   if isinstance(v, dict) and now - v.get("_ts", now) > _PENDING_TTL_SECONDS]
        for k in expired:
            del store[k]
    # Cap both dicts at 100 entries max as safety net
    for store in (pending_calls, pending_emails):
        while len(store) > 100:
            store.pop(next(iter(store)))

def _increment_error():
    """Thread-safe error counter."""
    global _ERROR_COUNT
    _ERROR_COUNT += 1
    metrics = _read_json("metrics.json", {})
    metrics["errors"] = _ERROR_COUNT
    _write_json("metrics.json", metrics)

def _get_ts():
    return datetime.datetime.now().strftime("%H:%M:%S")

def _update_agent_status(name, status, last_action=None):
    """Update agent_status.json for the dashboard."""
    data = _read_json("agent_status.json", {})
    if name not in data:
        data[name] = {"name": name, "status": "idle", "last_action": "Never"}
    
    data[name]["status"] = status
    if last_action:
        data[name]["last_action"] = last_action
    
    _write_json("agent_status.json", data)

def _append_log(entry):
    """Add a log entry to the in-memory buffer for the live activity feed."""
    with _LOG_LOCK:
        LOG_BUFFER.append({  # [FIX-1] deque auto-evicts oldest, no manual pop needed
            "ts": _get_ts(),
            "msg": entry
        })
    logger.info(f"ðŸ“œ LOG: {entry}")

DatabaseManager.init_db()

def _read_json(filename, default=None):
    """Safely read a JSON file from the data directory with SQL fallback."""
    if "metrics.json" in filename:
        return DatabaseManager.get_metrics()

    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        oc_path = os.path.join(DATA_DIR, "orova_instance", filename)
        if os.path.exists(oc_path):
            path = oc_path
        else:
            return default if default is not None else {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default or {}

def _write_json(filename, data):
    """Safely write JSON with SQL sync for metrics."""
    if "metrics.json" in filename:
        DatabaseManager.update_metrics(data)
        return

    path = os.path.join(DATA_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def _append_notification(title, body, ntype="info"):
    """Add a notification to notifications.json."""
    import datetime
    path = os.path.join(DATA_DIR, "notifications.json")
    try:
        with open(path, "r") as f:
            notifs = json.load(f)
    except Exception:
        notifs = []
    notifs.insert(0, {
        "id": str(int(datetime.datetime.now().timestamp() * 1000)),
        "title": title,
        "body": body,
        "type": ntype,
        "ts": datetime.datetime.now().isoformat(),
        "read": False,
    })
    notifs = notifs[:50]  # Keep last 50
    with open(path, "w") as f:
        json.dump(notifs, f, indent=2)

# â”€â”€ API HANDLER (ELITE REFACTOR) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class APIHandler:
    """Standardized API logic for OROVA Mission Control."""
    
    @staticmethod
    def get_dashboard_data(client_id):
        client_id = int(client_id)
        return {
            "metrics": DatabaseManager.get_metrics(client_id),
            "leads": DatabaseManager.get_leads(client_id),
            "tasks": DatabaseManager.get_tasks(client_id),
            "content": DatabaseManager.get_content(client_id),
            "memories": DatabaseManager.get_memories(client_id)
        }

    @staticmethod
    def get_skills():
        skills = []
        skill_agents = {
            "find_leads": "Hawk", "stealth_search": "Viper", "stealth_extract": "Viper",
            "send_outreach": "Closer", "write_ad_copy": "Quill", "pipeline_report": "Oracle"
        }
        for tool in TOOLS:
            name = tool.get("function", {}).get("name", "")
            if name:
                skills.append({
                    "name": name,
                    "category": "Elite Skill",
                    "status": "active",
                    "agent": skill_agents.get(name, "Nova"),
                })
        return skills


class MissionControlHandler(BaseHTTPRequestHandler):
    """Serves REST API + static dashboard files."""

    def log_message(self, format, *args):
        # Suppress noisy HTTP logs for static files
        if "/api/" in str(args[0]) if args else False:
            logger.info(f"[MC API] {args[0]}")

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")

    def _check_api_key(self):
        """[FIX-5] Validate API key â€” NO default fallback."""
        api_key = self.headers.get("X-API-Key") or self.headers.get("x-api-key")
        expected = os.getenv("OROVA_API_KEY")  # [FIX-5] Removed hardcoded 'orova_admin' default
        if not expected:
            self._json_response({"error": "OROVA_API_KEY not configured on server."}, 503)
            return False
        if not api_key or api_key != expected:
            self._json_response({"error": "Unauthorized. Provide X-API-Key header."}, 401)
            return False
        return True

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        path_parts = self.path.split("?")
        path = path_parts[0]
        query_str = path_parts[1] if len(path_parts) > 1 else ""
        
        client_id = 0
        if "client_id=" in query_str:
            try:
                client_id = int(query_str.split("client_id=")[1].split("&")[0])
            except ValueError:
                pass

        # â”€â”€ API Routes (Tenant-Aware) â”€â”€
        if path == "/api/clients":
            return self._json_response({"clients": DatabaseManager.get_clients()})

        elif path == "/api/agents":
            return self._json_response(_read_json("agent_status.json", {}))

        elif path == "/api/ai-status":
            mimo_key = os.getenv("MIMO_API_KEY", "")
            openai_key = os.getenv("OPENAI_API_KEY", "")
            groq_key = os.getenv("GROQ_API_KEY", "")
            tg_key = os.getenv("TELEGRAM_BOT_TOKEN", "")
            retell_key = os.getenv("RETELL_API_KEY", "")
            agentmail_key = os.getenv("AGENTMAIL_API_KEY", "")
            # Check for Google Sheets service account file
            sa_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
            sheets_ok = os.path.isfile(sa_path) or os.path.isfile(os.path.join(DATA_DIR, sa_path))
            # Build missing keys list for debugging
            missing = []
            if not retell_key: missing.append("RETELL_API_KEY")
            if not agentmail_key: missing.append("AGENTMAIL_API_KEY")
            if not sheets_ok: missing.append("GOOGLE_APPLICATION_CREDENTIALS / service_account.json")
            return self._json_response({
                "provider": "MiMo/v2-pro" if mimo_key else "none",
                "model": "MiMo/v2-pro",
                "mimo_connected": bool(mimo_key and "INSERT" not in mimo_key),
                "openai_connected": bool(openai_key),
                "groq_connected": bool(groq_key),
                "vertical": os.getenv("VERTICAL_NAME", "Automotive"),
                "mode": "autonomous",
                "telegram": bool(tg_key),
                "retell": bool(retell_key),
                "agentmail": bool(agentmail_key),
                "sheets": sheets_ok,
                "missing_keys": missing
            })

        elif path == "/api/metrics":
            return self._json_response(DatabaseManager.get_metrics(client_id))

        elif path == "/api/leads":
            db_leads = DatabaseManager.get_leads(client_id)
            return self._json_response({"leads": db_leads, "total": len(db_leads)})

        elif path == "/api/logs":
            return self._json_response({"logs": LOG_BUFFER[-50:]})

        elif path == "/api/notifications":
            data = _read_json("notifications.json", [])
            if isinstance(data, list):
                return self._json_response({"notifications": data})
            return self._json_response({"notifications": []})

        elif path == "/api/pending-emails":
            drafts = []
            for draft_id, draft in pending_emails.items():
                drafts.append({
                    "id": draft_id,
                    "to": draft.get("to", ""),
                    "company": draft.get("company", ""),
                    "contact": draft.get("contact", ""),
                    "subject": draft.get("subject", ""),
                    "body": draft.get("body", "")[:300],
                    "row_idx": draft.get("row_idx", 0)
                })
            return self._json_response({"pending": drafts, "count": len(drafts)})

        elif path == "/api/health":
            uptime_seconds = int(time.time() - _BOOT_TIME)
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            agents_data = _read_json("agent_status.json", {})
            return self._json_response({
                "status": "healthy",
                "uptime": f"{hours}h {minutes}m",
                "uptime_seconds": uptime_seconds,
                "errors": _ERROR_COUNT,
                "scheduler": {
                    "fast_lane": f"Every {APPROVAL_CHECK_MINUTES} min",
                    "slow_lane": f"Every {HUNT_INTERVAL_MINUTES} min",
                    "email_drafter": f"Every {EMAIL_DRAFT_INTERVAL_MINUTES} min",
                    "reply_monitor": f"Every {REPLY_CHECK_MINUTES} min"
                },
                "agents_online": len([a for a in agents_data.values() if isinstance(a, dict) and a.get("status") in ("active", "online", "idle")]),
                "pending_emails": len(pending_emails)
            })

        elif path == "/api/metrics/history":
            history = _read_json("metrics_history.json", [])
            return self._json_response({"history": history[-30:]})

        elif path == "/api/skills":
            return self._json_response({"skills": APIHandler.get_skills()})

        elif path == "/api/chat/history":
            return self._json_response({"history": DatabaseManager.get_chat_history(client_id)})

        elif path == "/api/pipelines":
            from app.core.pipeline import PIPELINES
            pipelines = [{"name": k, "label": v["name"], "desc": v["description"], "steps": len(v["steps"])} for k, v in PIPELINES.items()]
            return self._json_response({"pipelines": pipelines})

        elif path == "/api/tasks":
            return self._json_response({"tasks": DatabaseManager.get_tasks(client_id)})

        elif path == "/api/content":
            return self._json_response({"content": DatabaseManager.get_content(client_id)})

        elif path == "/api/memory":
            return self._json_response({"memories": DatabaseManager.get_memories(client_id)})
        
        elif path == "/api/leads/sqlite":
             return self._json_response({"leads": DatabaseManager.get_leads(client_id)})

        elif path == "/api/meta/performance":
            from app.skills.meta_ads_agent import MetaAdsAgent
            date_preset = "last_7d"
            if "date_preset=" in query_str:
                date_preset = query_str.split("date_preset=")[1].split("&")[0]
            agent = MetaAdsAgent()
            return self._json_response(agent.get_account_performance(date_preset))

        elif path == "/api/meta/adsets":
            from app.skills.meta_ads_agent import MetaAdsAgent
            date_preset = "last_7d"
            if "date_preset=" in query_str:
                date_preset = query_str.split("date_preset=")[1].split("&")[0]
            agent = MetaAdsAgent()
            return self._json_response(agent.get_ad_set_performance(date_preset))

        elif path == "/api/meta/weekly-report":
            from app.skills.meta_ads_agent import MetaAdsAgent
            client_name = ""
            if "client_name=" in query_str:
                client_name = query_str.split("client_name=")[1].split("&")[0]
            agent = MetaAdsAgent()
            return self._json_response(agent.generate_weekly_report(client_name))

        elif path == "/api/email/rotation-status":
            from app.core.email_inbox_rotation import InboxRotationManager
            rotator = InboxRotationManager()
            return self._json_response(rotator.daily_stats())

        # â”€â”€ Static File Serving â”€â”€
        else:
            self._serve_static(path)

    def do_POST(self):
        path_parts = self.path.split("?")
        path = path_parts[0]
        
        # Require API key for all POST endpoints
        if not self._check_api_key():
            return
        
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
            
        query_str = path_parts[1] if len(path_parts) > 1 else ""
        client_id = 0
        if "client_id=" in query_str:
            try:
                client_id = int(query_str.split("client_id=")[1].split("&")[0])
            except ValueError:
                pass
        client_id = payload.get("client_id", client_id)

        if path == "/api/clients":
            name, niche, location = payload.get("name"), payload.get("niche"), payload.get("location")
            if not name: return self._json_response({"error": "Client name required"}, 400)
            DatabaseManager.add_client(name, niche, location)
            return self._json_response({"status": "ok", "message": f"Client '{name}' created."})

        elif path == "/api/meta/evaluate":
            from app.skills.meta_ads_agent import MetaAdsAgent, DEFAULT_KPI_THRESHOLDS
            dry_run = payload.get("dry_run", True)
            thresholds = payload.get("thresholds", DEFAULT_KPI_THRESHOLDS)
            agent = MetaAdsAgent()
            result = agent.evaluate_and_pause_underperformers(thresholds, dry_run)
            if result.get("successfully_paused"):
                _telegram_notify(
                    f"ðŸš¨ *Meta Ads: {result['successfully_paused']} Ad Sets Paused*\n"
                    + "\n".join(f"  â€” {p['adset_name']}: {p['pause_reason']}" for p in result["paused_details"])
                )
            return self._json_response(result)

        elif path == "/api/meta/generate-copy":
            from app.skills.meta_ads_agent import MetaAdsAgent
            vertical = payload.get("vertical")
            if not vertical:
                return self._json_response({"error": "vertical is required"}, 400)
            agent = MetaAdsAgent()
            copy = agent.generate_luxury_ad_copy(
                vertical=vertical,
                asset_description=payload.get("asset_description", "Premium brand visual"),
                objective=payload.get("objective", "Lead Generation"),
                client_name=payload.get("client_name", ""),
            )
            return self._json_response(copy)

        elif path == "/api/cipher/sweep":
            from app.skills.cipher_agent import CipherAgent
            import asyncio
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(CipherAgent().run_daily_sweep())
            
            if result.get("lead_conflicts") and len(result["lead_conflicts"]) > 0:
                _telegram_notify(
                    f"ðŸ” *Cipher Alert â€” Competitor Exposure*\n"
                    f"{len(result['lead_conflicts'])} of your leads are being targeted by competitors."
                )
            return self._json_response(result)

        elif path == "/api/actions/hunt-leads":
            if not self._check_api_key():
                return
            _append_log(f"ðŸŽ¯ Manual lead hunt (Client {client_id})")
            _append_notification("Lead Hunt Started", "Manual hunt triggered", "lead")
            try:
                # Dynamic Niche/Location lookup
                config = DatabaseManager.get_client_config(client_id)
                niche = config.get("niche", VERTICAL_NAME)
                loc = config.get("location", "California")
                
                # Default query if none provided
                default_query = f"luxury {niche} {loc}"
                hunt_query = payload.get("query") or default_query

                res = _run_async(find_leads(count=5, query=hunt_query))
                raw_leads = res.get("leads", []) if isinstance(res, dict) else []
                
                for l in raw_leads:
                    db_lead = {"business": l.get("title"), "url": l.get("url"), "notes": l.get("snippet"), "vertical": niche}
                    DatabaseManager.save_lead(db_lead, client_id=client_id)

                # Async Sheet Sync
                try:
                    from app.skills.sheets_skill import append_to_sheet
                    sheet_rows = [["", l.get("title",""), "", "", "", l.get("url",""), "New", l.get("snippet","")] for l in raw_leads]
                    _run_async(append_to_sheet("OROVA_Leads", sheet_rows))
                except Exception as se: _append_log(f"âš ï¸ Sheet sync fail: {se}")

                metrics = DatabaseManager.get_metrics(client_id)
                DatabaseManager.update_metrics({"leads_found": metrics.get("leads_found", 0) + len(raw_leads)}, client_id=client_id)
                return self._json_response({"status": "ok", "message": f"Found {len(raw_leads)} leads."})
            except Exception as e:
                _append_log(f"âŒ Lead hunt failed: {e}")
                return self._json_response({"status": "error", "error": str(e)}, 500)

        elif path == "/api/actions/send-emails":
            if not self._check_api_key():
                return
            _append_log("ðŸ“§ Email batch triggered from Mission Control")
            _append_notification("Email Batch", "Email drafter triggered from dashboard", "email")
            try:
                _run_async(run_email_draft_job())
                return self._json_response({"status": "ok", "message": "Email drafter ran. Check Telegram for drafts to approve."})
            except Exception as e:
                _increment_error()
                return self._json_response({"status": "error", "error": str(e)}, 500)

        elif path == "/api/actions/generate-report":
            if not self._check_api_key():
                return
            _append_log("ðŸ“Š CEO Report requested from Mission Control")
            try:
                from app.skills.perf_dashboard import generate_weekly_report
                report = generate_weekly_report()
                return self._json_response({"status": "ok", "report": report})
            except Exception as e:
                return self._json_response({"status": "error", "error": str(e)}, 500)

        elif path == "/api/actions/run-pipeline":
            if not self._check_api_key():
                return
            _append_log("ðŸ”„ One-click pipeline execution started")
            _append_notification("Pipeline Started", "Niche execution pipeline triggered", "system")
            try:
                # Get and validate parameters with defaults
                niche = payload.get("niche", "Luxury Remodeling")
                location = payload.get("location", "Miami")
                
                # Step 1: Run lead finder
                res = _run_async(find_leads(count=15, query=f"{niche} {location}"))
                raw_leads = res.get("leads", []) if isinstance(res, dict) else []
                
                # Step 2: Filter qualified leads (qualified=True and has email)
                qualified_leads = [
                    l for l in raw_leads 
                    if l.get("qualified") is True and l.get("email") and len(l.get("email", "").strip()) > 0
                ]
                
                # Step 3: Save to database
                for l in qualified_leads:
                    db_lead = {
                        "business": l.get("title"),
                        "url": l.get("url"),
                        "email": l.get("email"),
                        "phone": l.get("phone"),
                        "notes": l.get("snippet"),
                        "vertical": niche
                    }
                    DatabaseManager.save_lead(db_lead, client_id=client_id)

                # Step 4: Update metrics
                metrics = DatabaseManager.get_metrics(client_id)
                DatabaseManager.update_metrics({
                    "leads_found": metrics.get("leads_found", 0) + len(raw_leads),
                    "qualified_leads": metrics.get("qualified_leads", 0) + len(qualified_leads)
                }, client_id=client_id)
                
                # Step 5: Trigger email drafter job
                try:
                    _run_async(run_email_draft_job())
                except Exception as ej:
                    _append_log(f"âš ï¸ Email drafter trigger failed: {ej}")

                _append_log(f"âœ… Pipeline completed: found {len(raw_leads)} total, {len(qualified_leads)} qualified leads")
                
                return self._json_response({
                    "status": "ok",
                    "summary": {
                        "niche": niche,
                        "location": location,
                        "total_found": len(raw_leads),
                        "qualified_count": len(qualified_leads)
                    },
                    "message": f"Pipeline completed. Found {len(raw_leads)} leads, {len(qualified_leads)} qualified."
                })
            except Exception as e:
                _append_log(f"âŒ Pipeline failed: {e}")
                _increment_error()
                return self._json_response({"status": "error", "error": str(e)}, 500)

        elif path == "/api/chat/history":
            history = payload.get("history", [])
            # For now, let's just clear and replace for this client
            DatabaseManager.query("DELETE FROM chat_history WHERE client_id = ?", (client_id,))
            for msg in history:
                DatabaseManager.query("INSERT INTO chat_history (role, content, client_id) VALUES (?, ?, ?)", 
                                     (msg.get("role"), msg.get("content"), client_id))
            return self._json_response({"status": "ok"})

        elif path == "/api/chat":
            message = payload.get("message", "")
            if not message: return self._json_response({"error": "No message provided"}, 400)
            _append_log(f"ðŸ’¬ Chat (Client {client_id}): {message[:40]}...")
            try:
                # [Elite Memory Restoration]
                history = DatabaseManager.get_chat_history(client_id)
                # Convert DB rows to AI format [{role, content}]
                formatted_history = [{"role": h["role"], "content": h["content"]} for h in history]
                
                response, new_history = _run_async(router.route(message, client_id, history=formatted_history))
                
                # Save only the NEW messages (User message + Assistant response)
                DatabaseManager.query("INSERT INTO chat_history (role, content, client_id) VALUES (?, ?, ?)", 
                                     ("user", message, client_id))
                DatabaseManager.query("INSERT INTO chat_history (role, content, client_id) VALUES (?, ?, ?)", 
                                     ("assistant", response, client_id))
                                     
                return self._json_response({"status": "ok", "response": response})
            except Exception as e: return self._json_response({"status": "error", "error": str(e)}, 500)

        elif path == "/api/tasks":
            DatabaseManager.query('''
                INSERT OR REPLACE INTO tasks (id, title, description, assignee, priority, status, due, client_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (payload.get("id"), payload.get("title"), payload.get("description"), payload.get("assignee"), 
                  payload.get("priority"), payload.get("status"), payload.get("due"), client_id))
            return self._json_response({"status": "ok", "message": "Task saved"})

        elif path == "/api/content":
            DatabaseManager.query('''
                INSERT OR REPLACE INTO content (id, title, type, stage, idea, script, image, client_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (payload.get("id"), payload.get("title"), payload.get("type"), payload.get("stage"), 
                  payload.get("idea"), payload.get("script"), payload.get("image"), client_id))
            return self._json_response({"status": "ok", "message": "Content saved"})

        elif path == "/api/memory":
             DatabaseManager.query('''
                INSERT OR REPLACE INTO memories (id, category, content, client_id, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (payload.get("id"), payload.get("category"), payload.get("content"), client_id))
             return self._json_response({"status": "ok", "message": "Memory saved"})

        elif path == "/api/tasks/delete":
            if not self._check_api_key():
                return
            tid = payload.get("id")
            DatabaseManager.query("DELETE FROM tasks WHERE id = ? AND client_id = ?", (tid, client_id))
            return self._json_response({"status": "ok"})

        elif path == "/api/content/delete":
            if not self._check_api_key():
                return
            cid = payload.get("id")
            DatabaseManager.query("DELETE FROM content WHERE id = ? AND client_id = ?", (cid, client_id))
            return self._json_response({"status": "ok"})

        elif path == "/api/memory/delete":
            if not self._check_api_key():
                return
            mid = payload.get("id")
            DatabaseManager.query("DELETE FROM memories WHERE id = ? AND client_id = ?", (mid, client_id))
            return self._json_response({"status": "ok"})

        elif path == "/api/notifications/read":
            if not self._check_api_key():
                return
            nid = payload.get("id")
            notifs = _read_json("notifications.json", [])
            if isinstance(notifs, list):
                for n in notifs:
                    if nid == "all" or n.get("id") == nid:
                        n["read"] = True
                _write_json("notifications.json", notifs)
            return self._json_response({"status": "ok"})

        elif path == "/api/actions/approve-email":
            if not self._check_api_key():
                return
            draft_id = payload.get("draft_id", "")
            if draft_id in pending_emails:
                draft = pending_emails[draft_id]
                _append_log(f"ðŸ“¤ CEO APPROVED email to {draft['company']} from Dashboard")
                try:
                    result = send_outreach(
                        to=draft["to"],
                        subject=draft["subject"],
                        body=draft["body"]
                    )
                    if result.get("status") == "sent":
                        _append_log(f"âœ… Email sent to {draft['company']}")
                        _append_notification("Email Sent", f"Approved & sent to {draft['company']}", "email")
                        metrics = DatabaseManager.get_metrics(client_id)
                        DatabaseManager.update_metrics({"emails_sent": metrics.get("emails_sent", 0) + 1}, client_id=client_id)
                        del pending_emails[draft_id]
                        return self._json_response({"status": "ok", "message": f"Email sent to {draft['to']}"})
                    else:
                        return self._json_response({"status": "error", "error": result.get("message", "Send failed")}, 500)
                except Exception as e:
                    return self._json_response({"status": "error", "error": str(e)}, 500)
            else:
                return self._json_response({"status": "error", "error": "Draft not found or expired"}, 404)

        elif path == "/api/actions/deny-email":
            if not self._check_api_key():
                return
            draft_id = payload.get("draft_id", "")
            if draft_id in pending_emails:
                company = pending_emails[draft_id]["company"]
                _append_log(f"ðŸš« CEO denied email to {company} from Dashboard")
                _append_notification("Email Denied", f"Draft to {company} discarded", "email")
                del pending_emails[draft_id]
                return self._json_response({"status": "ok", "message": f"Draft to {company} discarded"})
            else:
                return self._json_response({"status": "error", "error": "Draft not found or expired"}, 404)

        elif path == "/api/pipelines/run":
            if not self._check_api_key():
                return
            pipeline_name = payload.get("pipeline", "")
            if not pipeline_name:
                return self._json_response({"status": "error", "error": "No pipeline name provided"}, 400)
            _append_log(f"ðŸ”„ Pipeline '{pipeline_name}' triggered from Mission Control")
            _append_notification("Pipeline Started", f"Running: {pipeline_name}", "system")
            try:
                from app.core.pipeline import run_pipeline
                result = _run_async(run_pipeline(pipeline_name, payload.get("params", "")))
                return self._json_response({"status": "ok", "result": str(result)[:1000]})
            except Exception as e:
                _increment_error()
                return self._json_response({"status": "error", "error": str(e)}, 500)

        else:
            return self._json_response({"error": "Unknown endpoint"}, 404)

    def _serve_static(self, path):
        """Serve static files from mission-control directory."""
        import mimetypes
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors_headers()
            self.end_headers()
            html = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>OROVA // Mission Control</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--b:#0a0a0a;--b2:#141414;--b3:#1f1f1a;--g1:#262626;--g2:#333;--g3:#444;--g4:#666;--g5:#888;--g6:#aaa;--w:#fff;--w2:#e0e0e0;--grn:#00ff41;--red:#ff3333;--amb:#ffaa00;--bl:#3399ff;--bd:1px solid #333;--f:'JetBrains Mono',monospace;--f2:'Inter',sans-serif}
html,body{background:var(--b);color:var(--w);font-family:var(--f);font-size:13px;min-height:100vh}
a{color:var(--grn);text-decoration:none}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:var(--b)}
::-webkit-scrollbar-thumb{background:var(--g2)}
.hdr{border-bottom:var(--bd);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;background:var(--b2);position:sticky;top:0;z-index:100}
.hdr-logo{font-size:16px;font-weight:700;letter-spacing:6px;font-family:var(--f2)}
.hdr-logo span{color:var(--grn)}
.hdr-status{display:flex;align-items:center;gap:16px;font-size:11px;color:var(--g4)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--grn);animation:pulse 2s infinite}
.dot.kill{background:var(--red);animation:none}
.dot.warn{background:var(--amb)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.btn{padding:8px 16px;border:none;border-radius:4px;font-family:var(--f);font-size:11px;font-weight:500;cursor:pointer;transition:all .2s}
.btn-grn{background:var(--grn);color:var(--b)}
.btn-red{background:var(--red);color:var(--b)}
.btn-outline{background:transparent;border:1px solid var(--g3);color:var(--g4)}
.btn:hover{opacity:.8}
.kill-bar{background:#1a0000;border-bottom:1px solid var(--red);padding:12px 24px;display:none;align-items:center;justify-content:space-between}
.kill-bar.active{display:flex}
.kill-bar span{color:var(--red);font-size:11px;letter-spacing:2px}
.main{padding:24px;max-width:1400px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-bottom:24px}
.card{border:var(--bd);background:var(--b2);border-radius:8px;overflow:hidden}
.card-h{padding:14px 16px;border-bottom:var(--bd);display:flex;align-items:center;justify-content:space-between;background:var(--b3)}
.card-title{font-size:12px;font-weight:600;letter-spacing:1px;color:var(--g5);text-transform:uppercase}
.card-title .icon{margin-right:8px}
.card-body{padding:16px}
.metric{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid #222}
.metric:last-child{border:none}
.metric-label{color:var(--g4);font-size:11px}
.metric-value{font-size:14px;font-weight:600;color:var(--w)}
.agents{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}
.agent{border:var(--bd);border-radius:6px;padding:12px;text-align:center;transition:all .2s}
.agent:hover{border-color:var(--grn)}
.agent .name{font-size:11px;font-weight:600;margin-bottom:4px}
.agent .status{font-size:9px;color:var(--g4)}
.agent.active{border-color:var(--grn);background:rgba(0,255,65,.05)}
.agent.active .status{color:var(--grn)}
.agent.idle .status{color:var(--amb)}
.agent.error .status{color:var(--red)}
.activity{font-size:11px;max-height:300px;overflow-y:auto}
.activity .entry{padding:8px 0;border-bottom:1px solid #222;display:flex;gap:12px}
.activity .ts{color:var(--g4);min-width:60px}
.activity .msg{color:var(--w2)}
.logs{background:var(--b);border:var(--bd);border-radius:6px;padding:12px;font-size:11px;max-height:200px;overflow-y:auto}
.logs .line{padding:4px 0;color:var(--g5)}
.logs .line.error{color:var(--red)}
.logs .line.success{color:var(--grn)}
.logs .line.info{color:var(--bl)}
.kill-btn{padding:8px 16px;background:var(--red);color:var(--b);border:none;border-radius:4px;font-family:var(--f);font-size:10px;font-weight:700;letter-spacing:1px;cursor:pointer}
.kill-btn:hover{background:#ff5555}
.row{display:flex;gap:16px;flex-wrap:wrap}
.col{flex:1;min-width:300px}
@media(max-width:768px){.main{padding:12px}.row{flex-direction:column}}
</style></head>
<body>
<div class="hdr">
<div class="hdr-logo"><span>OROVA</span> // MISSION CONTROL</div>
<div class="hdr-status">
<span id="uptime">Loading...</span>
<span class="dot" id="statusDot"></span>
<span id="killStatus" style="display:none;color:var(--red)">KILL ACTIVE</span>
</div>
</div>
<div class="kill-bar" id="killBar">
<span>âš ï¸ KILL SWITCH ACTIVE â€” ALL AGENTS HALTED</span>
<button class="kill-btn" onclick="resumeAgents()">RESUME</button>
</div>
<div class="main">
<div class="row">
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ“Š PERFORMANCE</span><button class="btn btn-outline" onclick="loadMetrics()" title="Refresh">â†»</button></div>
<div class="card-body" id="metrics">Loading...</div>
</div>
</div>
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ¤– AGENTS & TASKS</span><span style="font-size:10px;color:var(--g4)" id="agentCount"></span></div>
<div class="card-body agents" id="agents">Loading...</div>
</div>
</div>
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ§  AI STATUS</span><button class="btn btn-outline" onclick="loadAI()" title="Refresh">â†»</button></div>
<div class="card-body" id="aiStatus">Loading...</div>
</div>
</div>
</div>
<div class="row">
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ“œ ACTIVITY LOG</span><button class="btn btn-outline" onclick="loadLogs()" title="Refresh">â†»</button></div>
<div class="card-body activity" id="activity">Loading...</div>
</div>
</div>
</div>
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ“‹ PENDING APPROVALS</span><span style="font-size:10px;color:var(--g4)" id="pendingCount"></span></div>
<div class="card-body" id="approvals">Loading...</div>
</div>
</div>
</div>
<div class="row">
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">â° SCHEDULER</span></div>
<div class="card-body" id="scheduler">Loading...</div>
</div>
</div>
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸ”Œ GATEWAY</span><button class="btn btn-outline" onclick="loadGateway()" title="Refresh">â†»</button></div>
<div class="card-body" id="gateway">Loading...</div>
</div>
</div>
</div>
</div>
<div class="row">
<div class="col">
<div class="card">
<div class="card-h"><span class="card-title">ðŸŽ¯ CURRENT TASKS</span><button class="btn btn-outline" onclick="loadTasks()" title="Refresh">â†»</button></div>
<div class="card-body" id="tasks">Loading...</div>
</div>
</div>
</div>
<script>
const API='';  // Same origin
const AGENTS=['HAWK','SAGE','QUILL','ORACLE','NOVA','VIPER','CLOSER','SENTINEL','NIGHTSHIFT','REVENUE','WARMUP','SIGNALS'];
let KILL_ACTIVE=false;
function fmt(n){return n||0}
function log(e){console.error(e);document.getElementById('debug').innerText=e}
async function loadMetrics(){
try{
const r=await fetch('/api/metrics');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
document.getElementById('metrics').innerHTML=`
<div class="metric"><span class="metric-label">Leads Found</span><span class="metric-value">${fmt(d.leads_found)}</span></div>
<div class="metric"><span class="metric-label">Emails Sent</span><span class="metric-value">${fmt(d.emails_sent)}</span></div>
<div class="metric"><span class="metric-label">Replies</span><span class="metric-value">${fmt(d.replies_received)}</span></div>
<div class="metric"><span class="metric-label">Meetings</span><span class="metric-value">${fmt(d.meetings_booked)}</span></div>
<div class="metric"><span class="metric-label">Calls</span><span class="metric-value">${fmt(d.calls_made)}</span></div>
<div class="metric"><span class="metric-label">Proposals</span><span class="metric-value">${fmt(d.proposals_sent)}</span></div>
`;
}catch(e){document.getElementById('metrics').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
async function loadLogs(){
try{
const r=await fetch('/api/logs');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
const entries=d.logs||[];
let html='';
entries.slice(-20).reverse().forEach(e=>{html+=`<div class="entry"><span class="ts">${e.ts}</span><span class="msg">${e.msg}</span></div>`});
document.getElementById('activity').innerHTML=html||'<span style="color:var(--g4)">No activity yet</span>';
}catch(e){document.getElementById('activity').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
async function loadHealth(){
try{
const r=await fetch('/api/health');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
document.getElementById('uptime').innerHTML='Uptime: '+d.uptime;
if(d.status==='healthy'){
document.getElementById('statusDot').className='dot';
document.getElementById('scheduler').innerHTML=`
<div class="metric"><span class="metric-label">Fast Lane</span><span class="metric-value" style="color:var(--grn)">âœ“ Active (2 min)</span></div>
<div class="metric"><span class="metric-label">Slow Lane</span><span class="metric-value" style="color:var(--grn)">âœ“ Active (30 min)</span></div>
<div class="metric"><span class="metric-label">Email Drafter</span><span class="metric-value" style="color:var(--grn)">âœ“ Active (30 min)</span></div>
<div class="metric"><span class="metric-label">Reply Monitor</span><span class="metric-value" style="color:var(--grn)">âœ“ Active (30 min)</span></div>
`;
}else{
document.getElementById('statusDot').className='dot warn';
}
}catch(e){
document.getElementById('statusDot').className='dot warn';
document.getElementById('uptime').innerHTML='Status: UNHEALTHY';
}
}
let agentStatus={};
AGENTS.forEach(a=>{agentStatus[a]='idle'});
AGENTS.forEach(a=>{
document.getElementById('agents').innerHTML+=`
<div class="agent idle" id="agent-${a}">
<div class="name">${a}</div>
<div class="status">idle</div>
</div>`;
});
document.getElementById('agentCount').innerHTML=AGENTS.length+' agents';
async function loadAI(){
try{
const r=await fetch('/api/ai-status');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
const providerColor=d.mimo_connected?'var(--grn)':'var(--red)';
document.getElementById('aiStatus').innerHTML=`
<div class="metric"><span class="metric-label">Provider</span><span class="metric-value" style="color:${providerColor}">${d.provider}</span></div>
<div class="metric"><span class="metric-label">Model</span><span class="metric-value">${d.model}</span></div>
<div class="metric"><span class="metric-label">Vertical</span><span class="metric-value">${d.vertical}</span></div>
<div class="metric"><span class="metric-label">Mode</span><span class="metric-value" style="color:var(--grn)">${d.mode}</span></div>
<div class="metric"><span class="metric-label">MiMo</span><span class="metric-value">${d.mimo_connected?'âœ“':'âœ—'}</span></div>
`;
}catch(e){document.getElementById('aiStatus').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
function updateAgent(name,status,lastAction){
const el=document.getElementById('agent-'+name);
if(el){
el.className='agent '+status;
el.querySelector('.status').innerText=status;
}
agentStatus[name]=status;
}
async function resumeAgents(){
if(!confirm('Resume all agents? This will restart the autonomy loop.'))return;
try{
await fetch(API+'/api/kill-switch/deactivate?api_key=orova_admin&reason=manual',{method:'POST'});
KILL_ACTIVE=false;
document.getElementById('killBar').className='kill-bar';
document.getElementById('killStatus').style.display='none';
alert('Agents resumed!');
loadHealth();
}catch(e){alert('Error: '+e.message)}
}
loadMetrics();
loadLogs();
loadHealth();
loadAI();
setInterval(loadMetrics,30000);
setInterval(loadLogs,30000);
setInterval(loadHealth,30000);
setInterval(loadAI,60000);
async function loadTasks(){
try{
const r=await fetch('/api/tasks');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
const tasks=d.tasks||[];
let html='';
tasks.slice(0,10).forEach(t=>{html+=`<div class="metric"><span class="metric-label">${t.title||t.name||'Task'}</span><span class="metric-value">${t.status||'pending'}</span></div>`});
document.getElementById('tasks').innerHTML=html||'<span style="color:var(--g4)">No active tasks</span>';
}catch(e){document.getElementById('tasks').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
async function loadApprovals(){
try{
const r=await fetch('/api/pending-emails');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
const pending=d.pending||[];
document.getElementById('pendingCount').innerText=pending.length+' pending';
let html='';
pending.slice(0,5).forEach(p=>{html+=`<div class="metric"><span class="metric-label">${p.company||p.to}</span><span class="metric-value" style="color:var(--amb)">${p.subject?.slice(0,30)||'Draft'}</span></div>`});
document.getElementById('approvals').innerHTML=html||'<span style="color:var(--grn)">âœ“ No pending approvals</span>';
}catch(e){document.getElementById('approvals').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
async function loadGateway(){
try{
const r=await fetch('/api/ai-status');
if(!r.ok)throw'E '+r.status;
const d=await r.json();
document.getElementById('gateway').innerHTML=`
<div class="metric"><span class="metric-label">Telegram</span><span class="metric-value">${d.telegram?'âœ“':'âœ—'}</span></div>
<div class="metric"><span class="metric-label">Google Sheets</span><span class="metric-value">${d.sheets?'âœ“':'âœ—'}</span></div>
<div class="metric"><span class="metric-label">Retell</span><span class="metric-value">${d.retell?'âœ“':'âœ—'}</span></div>
<div class="metric"><span class="metric-label">AgentMail</span><span class="metric-value">${d.agentmail?'âœ“':'âœ—'}</span></div>
`;
}catch(e){document.getElementById('gateway').innerHTML='<span style="color:var(--red)">'+e+'</span>'}
}
loadTasks();
loadApprovals();
loadGateway();
setInterval(loadTasks,60000);
setInterval(loadApprovals,30000);
</script>
</body></html>"""
            self.wfile.write(html.encode())
            return
        filepath = os.path.join(MC_PATH, path.lstrip("/"))
        if os.path.isfile(filepath):
            mime, _ = mimetypes.guess_type(filepath)
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self._cors_headers()
            self.end_headers()
            with open(filepath, "rb") as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")


# --- Unified Web Server (Health + Dashboard) ---
class UnifiedWebHandler(MissionControlHandler):
    """Combines Health Checks and Mission Control Dashboard."""
    
    def do_GET(self):
        path = self.path.split("?")[0]
        # Health Check
        if path == "/health" or path == "/api/health_check":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            import datetime
            ts = datetime.datetime.utcnow().isoformat()
            self.wfile.write(f'{{"status":"ok","agency":"OROVA","ts":"{ts}"}}'.encode())
            return
            
        # Standard Mission Control GET routes
        super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        # Webhook / Health POST can be added here if needed
        super().do_POST()

def start_unified_server():
    """Starts the web server on the port required by the environment (Hugging Face default: 7860)."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), UnifiedWebHandler)
    logger.info(f"ðŸŒ Unified Web Server (Health + Mission Control) on port {port}")
    server.serve_forever()

# --- Background Autonomous Worker ---
# (pending_emails, scheduler config already defined at top of file)

# â”€â”€ Smart Notification Priority â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Only notify Mark on truly important events
IMPORTANT_KEYWORDS = [
    "reply", "replied", "meeting", "booked", "approved", "denied",
    "error", "failed", "call initiated", "call connected",
    "email sent", "authorization needed", "new lead",
]

def _is_important_event(message):
    """Filter: only notify Mark on high-priority events."""
    lower = message.lower()
    return any(kw in lower for kw in IMPORTANT_KEYWORDS)

def send_telegram_report(message, force=False):
    """Send a Telegram message to Mark (CEO). Only sends if important or forced."""
    if not force and not _is_important_event(message):
        logger.info(f"[LOW PRIORITY] Skipped Telegram: {message[:60]}...")
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = _get_ceo_chat_id()
    if not token or not chat_id:
        logger.warning("Telegram report skipped: TOKEN or CHAT_ID missing.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send Telegram report: {e}")

_telegram_notify = send_telegram_report

def send_telegram_with_buttons(message, buttons):
    """Send a Telegram message with inline keyboard buttons."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = _get_ceo_chat_id()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps({"inline_keyboard": [buttons]})
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send Telegram buttons: {e}")

# â”€â”€ CEO FAST LANE (Every 2 min) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def run_ceo_fast_lane():
    """Check Google Sheet for leads needing approval and execute approved calls."""
    _update_agent_status("CEO Reporter", "active", f"Checking approvals at {_get_ts()}")
    _append_log("âš¡ Fast Lane: Checking approvals & pending calls...")

    try:
        import gspread
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        client = gspread.service_account(filename=creds_path)
        sheet = client.open("OROVA Leads").sheet1
        rows = sheet.get_all_values()

        for idx, row in enumerate(rows[1:], start=2):
            status = row[7] if len(row) > 7 else ""

            # New leads needing approval
            if status == "Ready for Call":
                company = row[4] if len(row) > 4 else "Unknown"
                intel = row[8] if len(row) > 8 else "No notes."
                _append_log(f"ðŸš¨ Approval needed for {company} (Row {idx})")

                send_telegram_with_buttons(
                    f"ðŸš¨ *Authorization Needed*\n\n*Target:* {company}\n*Intel:* {intel}\n\nWhat is your command, CEO?",
                    [
                        {"text": "âœ… Approve Call", "callback_data": f"approve_{idx}"},
                        {"text": "âŒ Deny", "callback_data": f"deny_{idx}"}
                    ]
                )
                # Update sheet so we don't re-notify
                try:
                    sheet.update_cell(idx, 8, "Pending Approval")
                except Exception:
                    pass

            # Execute approved calls
            elif status == "Approved":
                phone = row[3] if len(row) > 3 else ""
                company = row[4] if len(row) > 4 else ""
                _append_log(f"ðŸ“ž Calling {company} ({phone})...")

                try:
                    from app.skills.outbound_dialer import trigger_retell_call
                    context = {"business_name": company, "icebreaker": row[8] if len(row) > 8 else ""}
                    result = trigger_retell_call(phone, context)
                    if result.get("success"):
                        call_id = result.get("call_id")
                        sheet.update_cell(idx, 8, "Call Initiated")
                        _append_log(f"âœ… Call connected! ID: {call_id}")
                        send_telegram_report(f"ðŸ“ž *Call Initiated*\n\nNow calling *{company}*.\nCall ID: `{call_id}`")
                    else:
                        sheet.update_cell(idx, 8, "Call Failed")
                        _append_log(f"âŒ Call failed: {result.get('error')}")
                except Exception as e:
                    _append_log(f"âŒ Call error: {str(e)}")

    except Exception as e:
        _append_log(f"âš¡ Fast Lane Error: {str(e)}")
        _increment_error()

    _update_agent_status("CEO Reporter", "idle")

# â”€â”€ SLOW LANE: Lead Hunting (Every 60 min) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def run_lead_hunt_slow_lane():
    """Autonomous lead hunting with daily safeguard."""
    global daily_counter, last_reset_day

    current_day = time.strftime("%d")
    if current_day != last_reset_day:
        daily_counter = 0
        last_reset_day = current_day

    if daily_counter >= MAX_RUNS_PER_DAY:
        _append_log("ðŸŒ™ Daily hunt limit reached. Skipping.")
        return

    _update_agent_status("Lead Hunter", "active", f"Hunting at {_get_ts()}")
    query = os.getenv("HUNT_QUERY", "luxury home remodel California")
    _append_log(f"ðŸ•µï¸ Slow Lane: Hunting leads for '{query}'...")

    try:
        res = await find_leads(count=LEADS_TO_FIND_PER_RUN, query=query)
        text_result = res.get("text") if isinstance(res, dict) else str(res)
        raw_leads = res.get("leads", []) if isinstance(res, dict) else []
        qualified_count = res.get("qualified_count", 0)
        
        # Filter to ONLY qualified leads
        qualified_leads = [l for l in raw_leads if l.get("qualified")]
        
        _append_log(f"âœ… Hunter: {text_result[:100]}...")
        _append_notification("Leads Found", f"Found {len(raw_leads)} leads, {qualified_count} qualified", "lead")

        # Save ONLY qualified leads to Google Sheet
        if qualified_leads:
            try:
                from app.skills.sheets_skill import append_to_sheet
                rows = []
                for l in qualified_leads:
                    rows.append([
                        l.get("phone", ""),  # col A: phone
                        "", "", "",          # col B-D: first/last name empty
                        l.get("title", ""),  # col E: company
                        l.get("url", ""),    # col F: URL
                        "New",              # col G: status
                        l.get("email", "") or "",  # col H: email
                        l.get("snippet", ""),  # col I: notes
                        f"Score:{l.get('qualification_score',0)}|Source:{l.get('enrichment_source','')}"  # col J: metadata
                    ])
                await append_to_sheet("OROVA_Leads", rows)
                _append_log(f"ðŸ“Š Saved {len(qualified_leads)} QUALIFIED leads to sheet.")
            except Exception as se:
                _append_log(f"âš ï¸ Slow Lane: Sheet save failed: {se}")
        else:
            _append_log("âš ï¸ No qualified leads this cycle â€” all filtered out")

        # Update metrics ONCE with ACTUAL qualified lead count
        metrics = _read_json("metrics.json", {})
        metrics["leads_found"] = metrics.get("leads_found", 0) + len(qualified_leads)
        _write_json("metrics.json", metrics)

        # Report to Mark via Telegram
        send_telegram_report(
            f"â˜€ï¸ *Autonomous Hunt Report*\n\n"
            f"Query: '{query}'\n\n{text_result}\n\n"
            f"Runs today: {daily_counter + 1}/{MAX_RUNS_PER_DAY}"
        )

        daily_counter += 1
    except Exception as e:
        _append_log(f"âŒ Hunter Error: {str(e)}")
        send_telegram_report(f"âš ï¸ *Lead Hunt Error*: {str(e)}")

    _update_agent_status("Lead Hunter", "idle")

# â”€â”€ REPLY MONITOR (Every 5 min) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Persistent set of already-seen message IDs to prevent duplicate notifications
_seen_reply_ids = set()

# Senders to IGNORE (Nova's own emails, bounces, system messages)
_IGNORED_SENDERS = [
    "nova-orova@agentmail.to",
    "nova@agentmail.to",
    "mailer-daemon@",
    "postmaster@",
    "no-reply@",
    "noreply@",
    "bounce@",
    "notifications@",
]

def _is_ignored_sender(sender: str) -> bool:
    """Check if a sender should be ignored (Nova's own emails, bounces, etc.)."""
    if not sender:
        return True
    sender_lower = str(sender).lower()
    return any(blocked in sender_lower for blocked in _IGNORED_SENDERS)

async def run_reply_monitor():
    """Check AgentMail for NEW prospect replies, then categorize as HOT/WARM/COLD."""
    global _seen_reply_ids
    _update_agent_status("Outreach Agent", "active", f"Categorizing replies at {_get_ts()}")
    _append_log("ðŸ“¬ Reply Monitor: Scanning & categorizing new messages...")

    try:
        # Load previously seen IDs
        seen_data = _read_json("seen_replies.json", [])
        if isinstance(seen_data, list):
            _seen_reply_ids = set(seen_data)

        from app.skills.agentmail_skill import summarize_and_categorize_inbox
        results = await summarize_and_categorize_inbox(limit=20)
        
        if results.get("status") == "success":
            messages = results.get("messages", [])
            new_leads = 0
            for msg in messages:
                msg_id = msg.get("message_id", "")
                if msg_id in _seen_reply_ids:
                    continue

                category = msg.get("category", "COLD")
                sender = msg.get("from", "")
                subject = msg.get("subject", "")
                snippet = msg.get("snippet", "")

                # â”€â”€ Skip Nova's own emails and system bounces â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if _is_ignored_sender(sender) or any(kw in str(subject).lower() for kw in (
                    "delivery status", "undeliverable", "out of office", "auto-reply"
                )):
                    _seen_reply_ids.add(msg_id)
                    continue

                # â”€â”€ This is a GENUINE new reply â”€â”€â”€â”€â”€
                _seen_reply_ids.add(msg_id)
                new_leads += 1

                # â”€â”€ MSI: DNC Check â€” immediate, zero tolerance â”€â”€â”€â”€â”€â”€â”€â”€
                from app.core.dnc_manager import DNCManager
                if DNCManager.check_reply_for_dnc(sender, snippet):
                    _append_log(f"[DNC] {sender} added to Do Not Contact list.")
                    _append_notification("DNC Triggered", f"{sender} removed from outreach", "system")
                    continue

                # â”€â”€ MSI: Dynamic Re-Scoring (Iris) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                try:
                    from app.core.lead_scorer import rescore_lead
                    lead_row = DatabaseManager.query(
                        "SELECT id FROM leads WHERE LOWER(email) = LOWER(?) LIMIT 1",
                        (sender,), fetchone=True
                    )
                    if lead_row:
                        rescore_lead(lead_row["id"], "email_reply", context=snippet)
                except Exception as score_err:
                    logger.warning(f"Re-scoring failed for {sender}: {score_err}")

                # â”€â”€ MSI: Signal Protocol for HOT/WARM leads â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                if category in ("HOT", "WARM"):
                    # Trigger meeting detection for HOT leads
                    if category == "HOT":
                        await _try_book_meeting(sender, subject, snippet)

                    # Signal Protocol: REVENUE ALERT for HOT leads
                    if category == "HOT":
                        send_revenue_alert(
                            client_name=sender.split("@")[0],
                            vertical="Inbound Reply",
                            elite_score=85,
                            status="Reply Received â€” High Intent Signal",
                            projected_value="TBD",
                            next_action="Initiating Autonomous Appointment Setting sequence.",
                        )
                    else:
                        # WARM leads â€” log but don't alert
                        _append_log(f"[WARM] Reply from {sender}: {snippet[:60]}...")

            if new_leads > 0:
                _append_log(f"âœ¨ Found {new_leads} NEW categorized replies!")
                _append_notification("New Replies", f"Categorized {new_leads} new messages", "email")
                metrics = _read_json("metrics.json", {})
                metrics["replies_received"] = metrics.get("replies_received", 0) + new_leads
                _write_json("metrics.json", metrics)
            else:
                _append_log("ðŸ“¬ No new prospect replies.")

        # Persist seen IDs
        seen_list = list(_seen_reply_ids)[-500:]
        _write_json("seen_replies.json", seen_list)

    except Exception as e:
        _append_log(f"âŒ Reply Monitor Error: {str(e)}")
        _increment_error()

    _update_agent_status("Outreach Agent", "idle")

async def _try_book_meeting(sender, subject, snippet):
    """Use AI to detect if a reply indicates meeting interest, then auto-book."""
    try:
        meeting_keywords = ["meet", "call", "schedule", "available", "slot", "calendar",
                           "let's talk", "set up", "book", "appointment", "free", "tomorrow",
                           "next week", "this week", "monday", "tuesday", "wednesday",
                           "thursday", "friday"]
        lower_snippet = snippet.lower()
        if not any(kw in lower_snippet for kw in meeting_keywords):
            return  # No meeting intent detected

        _append_log(f"ðŸ“… Meeting intent detected from {sender}! Using AI to book...")

        # Ask AI to extract meeting details
        prompt = (
            f"A prospect replied to our outreach email. Extract meeting details.\n"
            f"From: {sender}\nSubject: {subject}\nBody: {snippet}\n\n"
            f"Today's date: {datetime.datetime.now().strftime('%Y-%m-%d')}\n"
            f"If they suggest a time, return ONLY a JSON object like:\n"
            f'{{"book": true, "date": "YYYY-MM-DDTHH:MM:SS", "duration": 30, "topic": "brief topic"}}\n'
            f"If no specific time is mentioned, return: {{\"book\": false}}\n"
            f"Return ONLY the JSON, no other text."
        )
        ai_response = await ai_client.extract(prompt)

        # Try to parse the AI response
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', ai_response)
            if json_match:
                meeting_data = json.loads(json_match.group())
            else:
                return
        except (json.JSONDecodeError, AttributeError):
            return

        if meeting_data.get("book"):
            # Book on Google Calendar
            result = create_calendar_event(
                summary=f"Meeting with {sender.split('@')[0]} - {meeting_data.get('topic', 'Outreach Follow-up')}",
                start_time=meeting_data["date"],
                duration_minutes=meeting_data.get("duration", 30),
                description=f"Auto-booked by OROVA from reply.\nFrom: {sender}\nSubject: {subject}"
            )

            if result.get("success"):
                _append_log(f"ðŸ“… Meeting booked with {sender}!")
                _append_notification("Meeting Booked", f"Auto-booked meeting with {sender}", "meeting")
                
                # Fix: Update metrics
                metrics = _read_json("metrics.json", {})
                metrics["meetings_booked"] = metrics.get("meetings_booked", 0) + 1
                _write_json("metrics.json", metrics)
                
                # â”€â”€ Notification Email to CEO â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                try:
                    # Try to get CEO email from USER.md
                    ceo_email = None
                    user_md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "USER.md")
                    if os.path.exists(user_md_path):
                        with open(user_md_path, "r") as f:
                            for line in f:
                                if "CEO_EMAIL:" in line:
                                    ceo_email = line.split(":", 1)[1].strip().strip("[]")
                                    break
                    
                    if ceo_email and "@" in ceo_email:
                        from app.skills.agentmail_skill import send_outreach
                        email_body = (
                            f"Boss, I've successfully booked a new lead!\n\n"
                            f"ðŸ‘¤ Prospect: {sender}\n"
                            f"ðŸ“… Date/Time: {meeting_data.get('date')}\n"
                            f"ðŸ“‹ Topic: {meeting_data.get('topic', 'Follow-up')}\n"
                            f"â± Duration: {meeting_data.get('duration', 30)} min\n\n"
                            f"Summary: {snippet}\n\n"
                            f"The calendar event has been created. Check Mission Control for more info."
                        )
                        send_outreach(
                            to=ceo_email,
                            subject=f"ðŸš€ New Lead Booked: {sender.split('@')[0]}",
                            body=email_body
                        )
                        _append_log(f"ðŸ“§ Notification email sent to {ceo_email}")
                except Exception as ne:
                    logger.error(f"Failed to send CEO notification email: {ne}")

                send_telegram_report(
                    f"ðŸ“… *Meeting Auto-Booked!*\n\n"
                    f"ðŸ‘¤ *With:* {sender}\n"
                    f"ðŸ“‹ *Topic:* {meeting_data.get('topic', 'Follow-up')}\n"
                    f"ðŸ—“ *When:* {meeting_data['date']}\n"
                    f"â± *Duration:* {meeting_data.get('duration', 30)} min\n\n"
                    f"Added to your Google Calendar âœ…",
                    force=True
                )
            else:
                _append_log(f"âŒ Calendar booking failed: {result.get('error')}")
                send_telegram_report(
                    f"âš ï¸ *Meeting Booking Failed*\n\n"
                    f"Prospect {sender} wants to meet but calendar booking failed.\n"
                    f"Error: {result.get('error')}\n\n"
                    f"Please book manually.",
                    force=True
                )
    except Exception as e:
        logger.error(f"Meeting booking error: {e}")

# â”€â”€ EMAIL DRAFTER + APPROVAL GATE (Every 30 min) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def run_email_draft_job():
    """AI-drafts PERSONALIZED outbound emails for qualified leads & sends to Mark for approval."""
    _update_agent_status("Outreach Agent", "active", f"Drafting emails at {_get_ts()}")
    _append_log("âœ‰ï¸ Email Drafter: Checking for qualified leads needing outreach...")

    try:
        import gspread
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        client = gspread.service_account(filename=creds_path)
        sheet = client.open("OROVA_Leads").sheet1
        rows = sheet.get_all_values()

        drafts_created = 0
        for idx, row in enumerate(rows[1:], start=2):
            status = row[7] if len(row) > 7 else ""
            email = row[5] if len(row) > 5 else ""
            company = row[4] if len(row) > 4 else "Unknown"
            contact_name = f"{row[1]} {row[2]}".strip() if len(row) > 2 else "there"
            url = row[6] if len(row) > 6 else ""
            notes = row[8] if len(row) > 8 else ""

            # Only draft for leads with email and status "New" or "Ready for Email"
            if email and status in ("New", "Ready for Email"):
                _append_log(f"âœ‰ï¸ Drafting PERSONALIZED email for {company} ({email})...")

                # Use AI to draft a PERSONALIZED email â€” no generic templates
                try:
                    prompt = (
                        f"Write a cold outreach email from OROVA (premium AI lead gen agency) "
                        f"to {contact_name} at {company} ({url}).\n\n"
                        f"RULES â€” DO NOT VIOLATE:\n"
                        f"1. Greeting: '[Name]â€”' ONLY. No 'Hi', 'Hello', 'Dear', 'Hope this finds you well'\n"
                        f"2. OPENING: Reference something SPECIFIC about {company}. Visit their website ({url}) or use notes: {notes}\n"
                        f"3. NO generic phrases like 'I came across your company', 'I hope you're doing well', 'I wanted to reach out'\n"
                        f"4. NO exclamation marks. NO emojis. Max 100 words.\n"
                        f"5. ONE specific CTA: 'Are you open to a 10-min strategic alignment call this week?'\n"
                        f"6. Close: 'â€” Mark, OROVA'\n"
                        f"7. MUST mention a specific detail about their business (service, location, recent news)\n"
                        f"8. If you cannot find a specific detail, use: '{notes}' as the personalization hook\n"
                        f"\nWrite ONLY the email body. No preamble, no explanation."
                    )
                    draft_body = await ai_client.write(prompt)

                    # Validate: reject if it contains generic phrases
                    generic_phrases = [
                        "hope this finds you well", "i came across", "i wanted to reach out",
                        "i hope you're", "i hope you are", "i'm reaching out",
                        "i am reaching out", "just checking in", "just wanted to",
                        "at your earliest convenience", "look forward to hearing",
                    ]
                    draft_lower = draft_body.lower()
                    if any(gp in draft_lower for gp in generic_phrases):
                        _append_log(f"âš ï¸ REJECTED generic draft for {company}. Regenerating...")
                        # Retry with stricter prompt
                        prompt += (
                            f"\n\nCRITICAL: Your previous draft was REJECTED for generic language. "
                            f"Write a completely different email. Start with a SPECIFIC observation about {company}. "
                            f"Be direct. Be bold. No filler."
                        )
                        draft_body = await ai_client.write(prompt)

                    # Store draft in pending_emails
                    draft_id = f"draft_{idx}_{int(time.time())}"
                    pending_emails[draft_id] = {
                        "to": email,
                        "company": company,
                        "contact": contact_name,
                        "subject": f"Quick question for {company}",
                        "body": draft_body,
                        "row_idx": idx
                    }

                    # Send draft to Mark via Telegram for approval
                    preview = draft_body[:300] if len(draft_body) > 300 else draft_body
                    send_telegram_with_buttons(
                        f"âœ‰ï¸ *Personalized Email Draft*\n\n"
                        f"ðŸ‘¤ *To:* {contact_name} ({email})\n"
                        f"ðŸ¢ *Company:* {company}\n"
                        f"ðŸ”— *URL:* {url}\n"
                        f"ðŸ“§ *Subject:* Quick question for {company}\n\n"
                        f"ðŸ“ *Body:*\n\"{preview}\"\n\n"
                        f"*Approve sending this email?*",
                        [
                            {"text": "âœ… Send", "callback_data": f"approve_email_{draft_id}"},
                            {"text": "âŒ Discard", "callback_data": f"deny_email_{draft_id}"}
                        ]
                    )

                    # Update status so we don't re-draft
                    sheet.update_cell(idx, 8, "Email Pending Approval")
                    drafts_created += 1
                    _append_log(f"âœ‰ï¸ Personalized draft sent to CEO for approval: {company}")

                except Exception as e:
                    _append_log(f"âŒ Draft error for {company}: {str(e)}")

            if drafts_created >= 3:  # Max 3 drafts per cycle
                break

        if drafts_created == 0:
            _append_log("âœ‰ï¸ No leads needing email outreach right now.")

    except Exception as e:
        _append_log(f"âŒ Email Drafter Error: {str(e)}")

    _update_agent_status("Outreach Agent", "idle")

# â”€â”€ Telegram Callback: Email Approval â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async def handle_email_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles âœ…/âŒ buttons for email drafts."""
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("approve_email_"):
        draft_id = data.replace("approve_email_", "")
        if draft_id in pending_emails:
            draft = pending_emails[draft_id]
            _append_log(f"ðŸ“¤ CEO APPROVED email to {draft['company']}. Sending...")

            result = send_outreach(
                to=draft["to"],
                subject=draft["subject"],
                body=draft["body"]
            )

            if result.get("status") == "success":
                await query.edit_message_text(
                    f"âœ… *Email Sent!*\n\n"
                    f"To: {draft['to']}\n"
                    f"Company: {draft['company']}"
                )
                _append_log(f"âœ… Email sent to {draft['to']}")
                _append_notification("Email Sent", f"Outreach email sent to {draft['company']}", "email")

                # Update metrics
                metrics = _read_json("metrics.json", {})
                metrics["emails_sent"] = metrics.get("emails_sent", 0) + 1
                _write_json("metrics.json", metrics)

                # Update Google Sheet status
                try:
                    import gspread
                    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
                    gc = gspread.service_account(filename=creds_path)
                    sheet = gc.open("OROVA_Leads").sheet1
                    sheet.update_cell(draft["row_idx"], 8, "Email Sent")
                except Exception:
                    pass
            else:
                await query.edit_message_text(f"âŒ *Send Failed:* {result.get('message')}")
                _append_log(f"âŒ Email send failed: {result.get('message')}")

            del pending_emails[draft_id]
        else:
            await query.edit_message_text("âš ï¸ *Draft expired or not found.*")

    elif data.startswith("deny_email_"):
        draft_id = data.replace("deny_email_", "")
        if draft_id in pending_emails:
            company = pending_emails[draft_id]["company"]
            _append_log(f"ðŸš« CEO denied email to {company}")

            # Update Google Sheet
            try:
                import gspread
                creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
                gc = gspread.service_account(filename=creds_path)
                sheet = gc.open("OROVA_Leads").sheet1
                sheet.update_cell(pending_emails[draft_id]["row_idx"], 8, "Email Denied")
            except Exception:
                pass

            del pending_emails[draft_id]
        await query.edit_message_text("ðŸš« *Email discarded.*")

# â”€â”€ Scheduler Loop â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _run_async(coro):
    """Helper to run an async function safely in the scheduler thread."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()

def run_scheduler_loop():
    """Main autonomous scheduler loop with all worker jobs."""

    _append_log("ðŸ¤– OROVA Autonomy Loop: Online")
    _append_log(f"âš¡ Fast Lane: Every {APPROVAL_CHECK_MINUTES} min")
    _append_log(f"ðŸ•µï¸ Slow Lane: Every {HUNT_INTERVAL_MINUTES} min")
    _append_log(f"âœ‰ï¸ Email Drafter: Every {EMAIL_DRAFT_INTERVAL_MINUTES} min")
    _append_log(f"ðŸ“¬ Reply Monitor: Every {REPLY_CHECK_MINUTES} min")

    # Initialize agent statuses
    _update_agent_status("Lead Hunter", "idle")
    _update_agent_status("Outreach Agent", "idle")
    _update_agent_status("CEO Reporter", "idle")
    _update_agent_status("Support Nova", "online")

    # Schedule all jobs
    schedule.every(APPROVAL_CHECK_MINUTES).minutes.do(lambda: _run_async(run_ceo_fast_lane()))
    schedule.every(HUNT_INTERVAL_MINUTES).minutes.do(lambda: _run_async(run_lead_hunt_slow_lane()))
    schedule.every(REPLY_CHECK_MINUTES).minutes.do(lambda: _run_async(run_reply_monitor()))
    schedule.every(EMAIL_DRAFT_INTERVAL_MINUTES).minutes.do(lambda: _run_async(run_email_draft_job()))

    # â”€â”€ Mission Pulse (08:00 AM ET and 20:00 PM ET) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def run_morning_pulse():
        _update_agent_status("Atlas", "active", "Compiling AM Mission Pulse")
        try:
            run_mission_pulse("AM")
            _append_log("[MISSION PULSE AM] Sent to Owner.")
            _append_notification("Mission Pulse AM", "Daily morning pulse delivered", "report")
        except Exception as e:
            logger.error(f"Mission Pulse AM failed: {e}")
        finally:
            _update_agent_status("Atlas", "idle")

    def run_evening_pulse():
        _update_agent_status("Atlas", "active", "Compiling PM Mission Pulse")
        try:
            run_mission_pulse("PM")
            _append_log("[MISSION PULSE PM] Sent to Owner.")
            _append_notification("Mission Pulse PM", "Daily evening pulse delivered", "report")
        except Exception as e:
            logger.error(f"Mission Pulse PM failed: {e}")
        finally:
            _update_agent_status("Atlas", "idle")

    schedule.every().day.at("08:00").do(run_morning_pulse)   # 08:00 ET
    schedule.every().day.at("20:00").do(run_evening_pulse)   # 20:00 ET

    # â”€â”€ Daily Metrics Snapshot (for history charts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def snapshot_metrics():
        try:
            metrics = _read_json("metrics.json", {})
            history = _read_json("metrics_history.json", [])
            snapshot = {
                "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "leads": metrics.get("leads_found", 0),
                "emails": metrics.get("emails_sent", 0),
                "replies": metrics.get("replies", 0),
                "meetings": metrics.get("meetings_booked", 0),
                "calls": metrics.get("calls_made", 0),
                "errors": _ERROR_COUNT
            }
            # Avoid duplicate entries for same day
            if history and history[-1].get("date") == snapshot["date"]:
                history[-1] = snapshot
            else:
                history.append(snapshot)
            # Keep last 90 days
            _write_json("metrics_history.json", history[-90:])
        except Exception as e:
            logger.error(f"Metrics snapshot failed: {e}")

    schedule.every().day.at("23:59").do(snapshot_metrics)
    # Also take an initial snapshot on boot
    snapshot_metrics()

    # â”€â”€ Uptime Persistence (Self-Ping) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    def run_uptime_ping():
        """Ping own health endpoint to prevent sleep on some cloud tiers."""
        try:
            port = os.environ.get("PORT", "7860")
            # In Space, localhost:7860 is internal, but public URL is preferred
            # We try to detect the public URL or fall back to localhost
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            if render_url:
                # https://huggingface.co/spaces/user/name -> user-name.hf.space
                url = f"{render_url}/health"
            else:
                url = f"http://localhost:{port}/health"
                
            logger.info(f"ðŸ›°ï¸ Uptime Ping: {url}")
            requests.get(url, timeout=10)
        except Exception as e:
            logger.warning(f"Uptime ping failed: {e}")

    schedule.every(5).minutes.do(run_uptime_ping)  # [FIX-11] 10â†’5 min to prevent Render 15-min idle kill
    # Ping immediately on boot in a background thread
    threading.Thread(target=run_uptime_ping, daemon=True, name="UptimePing").start()

    # Signal Protocol: Initialization Pulse
    try:
        leads = DatabaseManager.get_leads(0)
        verticals = len(set(l.get('vertical', '') for l in leads if l.get('vertical')))
        send_initialization_pulse(len(leads), max(verticals, 1))
    except Exception as e:
        logger.warning(f"Initialization pulse failed: {e}")
    _append_log("[SIGNAL] Nova online. Signal Protocol active. Mission Pulse scheduled.")

    last_heartbeat = 0
    while True:
        try:
            schedule.run_pending()
            _prune_pending()  # [FIX-1] TTL-prune expired pending approvals
            
            # â”€â”€ Autonomy Heartbeat (Every 5 min) â”€â”€
            if time.time() - last_heartbeat > 300:
                _append_log("ðŸ’“ Autonomy Heartbeat: Scheduler loop is active.")
                last_heartbeat = time.time()
                
        except (KeyboardInterrupt, SystemExit):  # [FIX-6] Never swallow these
            raise
        except (OSError, RuntimeError, ValueError) as e:  # [FIX-6] Specific exceptions
            logger.error(f"ðŸ›‘ CRITICAL: Scheduler Loop Error: {e}")
            _append_log(f"âš ï¸ Scheduler encountered an error: {e}")
            _increment_error()
            time.sleep(10) # Wait before retrying
        time.sleep(1)

def start_mission_control_server():
    if not os.path.exists(MC_PATH):
        logger.warning(f"Mission Control directory not found at {MC_PATH}")
        return
    server = HTTPServer(('0.0.0.0', 8080), MissionControlHandler)
    logger.info(f"ðŸ¢ Mission Control API + Dashboard on port 8080")
    server.serve_forever()

# â”€â”€ Telegram Commands for Audit Capabilities â”€â”€
async def cipher_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ” Running Cipher competitive sweep...")
    try:
        from app.skills.cipher_agent import CipherAgent
        result = await CipherAgent.run_daily_sweep()
        msg = (
            f"ðŸ” *Cipher Complete*\n"
            f"Competitor mentions: {str(len(result.get('competitor_mentions', [])))}\n"
            f"Lead conflicts: {str(len(result.get('lead_conflicts', [])))}\n"
            f"Summary: {result.get('summary', '')}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"âŒ Cipher failed: {e}")

async def metaads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ðŸ“Š Fetching Meta Ads performance...")
    try:
        from app.skills.meta_ads_agent import MetaAdsAgent
        agent = MetaAdsAgent()
        p = agent.get_account_performance("last_7d")
        if not p or p.get("error"):
            await update.message.reply_text(f"âŒ Meta API error: {p.get('error', 'Unknown')}")
            return
        await update.message.reply_text((
            f"ðŸ“Š *Meta Ads â€” Last 7 Days*\n\n"
            f"Spend: ${p.get('spend',0):.2f}\n"
            f"Leads: {p.get('leads',0)}\n"
            f"CPL: ${p.get('cpl','N/A')}\n"
            f"ROAS: {p.get('roas','N/A')}x\n"
            f"CTR: {p.get('ctr',0):.2f}%\n"
            f"Frequency: {p.get('frequency',0):.1f}"
        ), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"âŒ {e}")

async def metapause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    dry_run = "--execute" not in args
    mode = "DRY RUN" if dry_run else "LIVE EXECUTION"
    await update.message.reply_text(f"ðŸ” Evaluating Meta ad sets ({mode})...")
    try:
        from app.skills.meta_ads_agent import MetaAdsAgent
        r = MetaAdsAgent().evaluate_and_pause_underperformers(dry_run=dry_run)
        await update.message.reply_text((
            f"{'ðŸ§ª DRY RUN' if dry_run else 'â¸ EXECUTION'} *Meta Evaluate*\n"
            f"Sets evaluated: {r.get('ad_sets_evaluated', 0)}\n"
            f"Flagged for pause: {r.get('flagged_for_pause', 0)}\n"
            f"Actually paused: {r.get('successfully_paused', 0)}\n\n"
            + ("Add --execute to action the pauses." if dry_run else "Pauses executed.")
        ), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"âŒ {e}")

async def available_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show your availability status."""
    from app.core.smart_calling import calling_hours
    status = calling_hours.get_status()
    msg = (
        f"ðŸ“… *Your Availability*\n"
        f"Timezone: {status['timezone']}\n"
        f"Now: {status['current_time']}\n"
        f"Available: {'Yes' if status['owner_available_now'] else 'No'}\n\n"
        f"*Preferred Slots:*\n"
    )
    for s in status["preferred_slots"]:
        days = ", ".join(s["days"]).upper()
        msg += f"  {s['name']}: {s['start']}â€“{s['end']} ({days})\n"
    if status["blocked_dates"]:
        msg += f"\n*Blocked:* {', '.join(status['blocked_dates'])}"
    else:
        msg += f"\n*Blocked:* None"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next available discovery call slots."""
    from app.core.smart_calling import calling_hours
    slots = calling_hours.get_available_slots(days_ahead=7)
    if not slots:
        await update.message.reply_text("No slots available in the next 7 days.")
        return
    msg = "ðŸ“… *Available Slots (next 7 days):*\n\n"
    for s in slots:
        msg += f"  {s['display']} ({s['slot_name']})\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Block dates. Usage: /block 2026-04-10 2026-04-11"""
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /block YYYY-MM-DD [YYYY-MM-DD ...]")
        return
    from app.core.smart_calling import calling_hours
    calling_hours.block_dates(args, reason="manual block")
    await update.message.reply_text(f"Blocked: {', '.join(args)}")

async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unblock dates. Usage: /unblock 2026-04-10"""
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /unblock YYYY-MM-DD [YYYY-MM-DD ...]")
        return
    from app.core.smart_calling import calling_hours
    calling_hours.unblock_dates(args)
    await update.message.reply_text(f"Unblocked: {', '.join(args)}")

# --- Main ---
def _handle_shutdown(signum, frame):
    """[FIX-12] Graceful shutdown on SIGTERM/SIGINT."""
    sig_name = signal.Signals(signum).name
    logger.info(f"ðŸ›‘ Received {sig_name} â€” initiating graceful shutdown...")
    # Attempt DB backup before exit
    try:
        from app.skills.drive_backup import backup_database
        from app.core.database import DB_PATH
        backup_database(DB_PATH)
        logger.info("âœ… Database backed up on shutdown.")
    except Exception as e:
        logger.warning(f"Shutdown backup failed: {e}")
    logger.info("ðŸ‘‹ Nova going offline. Goodbye.")
    sys.exit(0)

def main():
    # [FIX-12] Register SIGTERM/SIGINT handlers
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    # Phase 1: Start Unified Web Server FIRST (Health + Mission Control)
    logger.info("ðŸ›°ï¸ Phase 1: Starting Unified Web Server...")
    threading.Thread(target=start_unified_server, daemon=True).start()
    threading.Thread(target=run_scheduler_loop, daemon=True).start()
    
    # Phase 2: Brief startup buffer for web server to bind
    logger.info("â³ Phase 2: Waiting 3s for web server to initialize...")
    time.sleep(3)
    
    # Phase 3: Connectivity Verification
    logger.info("ðŸ“¡ Phase 3: Probing Telegram API connectivity...")
    try:
        ip = socket.gethostbyname("api.telegram.org")
        logger.info(f"ðŸŒ DNS resolved: api.telegram.org -> {ip}")
    except Exception as e:
        logger.warning(f"âš ï¸ DNS Probe Failed: {e}. Attempting bot start anyway...")

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    logger.info("ðŸš€ Phase 4: Connecting Nova to Telegram...")
    
    max_retries = 15
    for attempt in range(max_retries):
        try:
            # Fully recreate asyncio context for each attempt to avoid 'Loop Closed' errors
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            persistence = PicklePersistence(filepath="nova_memory.pickle")
            application = Application.builder().token(token).persistence(persistence).build()
            
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("reset", reset_command))
            application.add_handler(CommandHandler("dashboard", dashboard_command))
            application.add_handler(CommandHandler("report", report_command))
            application.add_handler(CommandHandler("check", check_reminders_command))
            application.add_handler(CommandHandler("cipher", cipher_command))
            application.add_handler(CommandHandler("metaads", metaads_command))
            application.add_handler(CommandHandler("metapause", metapause_command))
            application.add_handler(CommandHandler("available", available_command))
            application.add_handler(CommandHandler("slots", slots_command))
            application.add_handler(CommandHandler("block", block_command))
            application.add_handler(CommandHandler("unblock", unblock_command))
            application.add_handler(CallbackQueryHandler(handle_email_decision, pattern=r"^(approve_email_|deny_email_)"))
            application.add_handler(CallbackQueryHandler(handle_call_decision))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

            logger.info(f"âœ¨ Nova is Online! (Attempt {attempt+1}) Standing by, CEO. ðŸ¦¾")
            application.run_polling()
            break
        except Exception as e:
            logger.error(f"âŒ Telegram Error (Attempt {attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                logger.info("ðŸ” Retrying in 5 seconds...")
                time.sleep(5)
            else:
                logger.error("ðŸ›‘ CRITICAL: Max retries reached. Nova remains offline.")
                raise

if __name__ == "__main__":
    main()


