import asyncio
import logging
import os
import sys
import time
from datetime import datetime
import pytz
import schedule
import requests
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Add app path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.skills.lead_finder import find_leads
from app.skills.outbound_dialer import trigger_retell_call
from app.skills.agentmail_skill import check_replies
from app.core.database import DatabaseManager

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()

# Initialize database
DatabaseManager.init_db()

# --- CONFIGURATION ---
LEADS_TO_FIND_PER_RUN = 5
HUNT_INTERVAL_MINUTES = 60
APPROVAL_CHECK_MINUTES = 2
REPLY_CHECK_MINUTES = 5
COLD_CALL_CHECK_MINUTES = 30    # Check for cold leads to auto-call
MAX_RUNS_PER_DAY = 10
MAX_CALLS_PER_DAY = 5           # Safety cap for Retell calls
COLD_LEAD_DAYS_THRESHOLD = 5    # Days before escalating to phone call

# Security: Wallet Drain Safeguard
daily_hunt_counter = 0
daily_call_counter = 0
last_reset_day = time.strftime("%d")


def _reset_daily_counters():
    """Reset daily counters at midnight."""
    global daily_hunt_counter, daily_call_counter, last_reset_day
    current_day = time.strftime("%d")
    if current_day != last_reset_day:
        daily_hunt_counter = 0
        daily_call_counter = 0
        last_reset_day = current_day


def _get_sheets_client():
    """Get authorized Google Sheets client."""
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scope)
    return gspread.authorize(creds)


def send_telegram_report(message):
    """Send a report to Mark via Telegram."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram report skipped: TOKEN or CHAT_ID missing.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        logger.error(f"Failed to send Telegram report: {e}")


# ═══════════════════════════════════════════════════════
# LANE 1: FAST LANE — Approval checks + execute calls
# Runs every 2 minutes
# ═══════════════════════════════════════════════════════
async def run_ceo_fast_lane(client_id=0):
    """⚡ Check for leads needing approval and execute approved calls."""
    logger.info(f"⚡ [FAST LANE] [Client {client_id}] Checking approvals and pending calls...")

    try:
        # For now, we utilize a single master sheet, but filter by client_id in the notes/metadata
        # Future: support client-specific sheet names stored in the 'clients' table
        client_auth = _get_sheets_client()
        sheet = client_auth.open("OROVA Leads").sheet1
        rows = sheet.get_all_values()

        for idx, row in enumerate(rows[1:], start=2):
            status = row[7] if len(row) > 7 else ""
            
            # --- Execute approved calls ---
            if status == "Approved":
                _execute_approved_call(sheet, row, idx, client_id=client_id)

    except Exception as e:
        logger.error(f"Fast Lane Error (Client {client_id}): {e}")


def _execute_approved_call(sheet, row, idx, client_id=0):
    """Execute a call for an approved lead."""
    global daily_call_counter
    _reset_daily_counters()

    # SAFETY: Do not call outside of 9 AM - 5 PM California time (PST)
    pst_tz = pytz.timezone('America/Los_Angeles')
    now_pst = datetime.now(pst_tz)
    if now_pst.hour < 9 or now_pst.hour >= 17:
        logger.info(f"⏳ [FAST Lane] Call queued for {row[4]}, but it is outside PST business hours ({now_pst.strftime('%H:%M')}). Waiting.")
        return

    if daily_call_counter >= MAX_CALLS_PER_DAY:
        logger.info(f"📞 Daily call limit ({MAX_CALLS_PER_DAY}) reached. Skipping.")
        return

    phone = row[3]
    company = row[4]
    contact = f"{row[1]} {row[2]}".strip() if len(row) > 2 else ""
    intel = row[8] if len(row) > 8 else ""

    logger.info(f"📞 [CALL] Triggering Retell for {company} ({phone})...")

    context = {
        "business_name": company,
        "contact_name": contact,
        "icebreaker": intel,
        "offer_gap": "",
    }

    result = trigger_retell_call(phone, context)

    if result.get("success"):
        call_id = result.get("call_id")
        logger.info(f"✅ [CALL] Success! ID: {call_id}")
        sheet.update_cell(idx, 8, "Call Initiated")
        # Ensure enough columns
        while len(row) < 10:
            row.append("")
        sheet.update_cell(idx, 10, call_id)
        daily_call_counter += 1

        send_telegram_report(
            f"📞 **Call Initiated**\n\n"
            f"I am now calling **{company}** ({contact}).\n"
            f"Call ID: `{call_id}`"
        )

        # Update SQLite metrics
        try:
            metrics = DatabaseManager.get_metrics(client_id)
            DatabaseManager.update_metrics({"calls_made": metrics.get("calls_made", 0) + 1}, client_id=client_id)
        except Exception:
            pass
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"❌ [CALL] Failed: {error}")
        sheet.update_cell(idx, 8, "Call Failed")
        send_telegram_report(f"⚠️ **Call Failed**\n\nError calling **{company}**: {error}")


# ═══════════════════════════════════════════════════════
# LANE 2: SLOW LANE — Lead hunting
# Runs every 60 minutes
# ═══════════════════════════════════════════════════════
async def run_lead_hunt_slow_lane(client_id=0, niche=None, location=None):
    """🕵️ Hunt for new leads via multi-tier search."""
    global daily_hunt_counter
    _reset_daily_counters()

    if daily_hunt_counter >= MAX_RUNS_PER_DAY:
        logger.info(f"🌙 [SLOW LANE] [Client {client_id}] Daily limit reached. Skipping lead hunt.")
        return

    import random
    if client_id == 0 or not niche:
        niches = [
            "luxury car dealers california",
            "luxury home remodeling california",
            "high end custom home builders california",
            "private aviation charter california",
            "small plane rentals california",
            "helicopter charter services california"
        ]
        query = random.choice(niches)
    else:
        query = f"{niche} {location if location else ''}".strip()

    logger.info(f"🕵️ [SLOW LANE] [Client {client_id}] Hunting for leads: {query}")

    try:
        result = await find_leads(count=LEADS_TO_FIND_PER_RUN, query=query)

        # result is a dict with 'leads' key (list) and 'text' key (string)
        leads = []
        summary_text = ""
        if isinstance(result, dict):
            leads = result.get("leads", [])
            summary_text = result.get("text", "")
        elif isinstance(result, str):
            summary_text = result

        if leads:
            count = len(leads)
            logger.info(f"   -> Found {count} leads. Saving to SQLite...")

            # Save each lead to SQLite
            for lead in leads:
                if isinstance(lead, dict):
                    DatabaseManager.save_lead(lead, client_id=client_id)

            # Update metrics
            try:
                metrics = DatabaseManager.get_metrics(client_id)
                DatabaseManager.update_metrics({
                    "leads_found": metrics.get("leads_found", 0) + count
                }, client_id=client_id)
            except Exception:
                pass

            send_telegram_report(
                f"☀️ **Lead Hunt Complete**\n\n"
                f"Found **{count}** new leads for '{query}'.\n\n"
                f"{summary_text[:500]}"
            )
        else:
            logger.info("   -> No leads found this shift.")

        daily_hunt_counter += 1
        logger.info(f"   -> Hunt complete. Total runs today: {daily_hunt_counter}")

    except Exception as e:
        logger.error(f"   !!! ERROR in Slow Lane: {e}")
        send_telegram_report(f"⚠️ **Lead Hunt Error**: {str(e)}")


# ═══════════════════════════════════════════════════════
# LANE 3: REPLY MONITOR — Check for prospect responses
# Runs every 5 minutes
# ═══════════════════════════════════════════════════════
async def run_reply_monitor(client_id=0):
    """📬 Check AgentMail for new prospect replies."""
    logger.info(f"📬 [REPLY MONITOR] [Client {client_id}] Checking for new messages...")
    try:
        # Note: check_replies currently uses a global email account. 
        # For Phase 10, we at least isolate the Metric updates to the client.
        res = check_replies(limit=5)
        if res.get("status") == "success" and res.get("count", 0) > 0:
            for msg in res.get("messages", []):
                sender = msg.get("from")
                subject = msg.get("subject")
                snippet = msg.get("snippet")

                logger.info(f"✨ New reply from {sender}: {subject}")

                report = (
                    f"📬 **New Outreach Reply!** [Client {client_id}]\n\n"
                    f"👤 **From:** {sender}\n"
                    f"📧 **Subject:** {subject}\n"
                    f"📝 **Snippet:** \"{snippet}...\"\n\n"
                    f"Shall I check the calendar and propose a slot?"
                )
                send_telegram_report(report)

                # Update reply metrics
                try:
                    metrics = DatabaseManager.get_metrics(client_id)
                    DatabaseManager.update_metrics({
                        "replies_received": metrics.get("replies_received", 0) + 1
                    }, client_id=client_id)
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Reply Monitor Error: {e}")


# ═══════════════════════════════════════════════════════
# LANE 4: COLD LEAD ESCALATION — Auto-call via Retell.AI
# Runs every 30 minutes
# When leads don't open/reply to emails after X days,
# automatically escalate to phone call.
# ═══════════════════════════════════════════════════════

async def run_cold_lead_escalation(client_id=0):
    """📞 Identify leads that haven't replied and escalate to phone call."""
    logger.info(f"📞 [ESCALATION] [Client {client_id}] Checking for cold leads...")
    try:
        pst_tz = pytz.timezone('America/Los_Angeles')
        now_pst = datetime.now(pst_tz)
        
        # Give a little buffer for cold calls: 10 AM to 4 PM PST
        if now_pst.hour < 10 or now_pst.hour >= 16:
            logger.info(f"⏳ [ESCALATION] Outside prime calling hours ({now_pst.strftime('%I:%M %p')} PST). Suspending escalations.")
            return

        cold_leads = DatabaseManager.get_cold_leads(COLD_LEAD_DAYS_THRESHOLD, client_id=client_id)
        if not cold_leads:
            logger.info(f"📞 [ESCALATION] [Client {client_id}] No true cold leads to escalate.")
            return

        cold_business_names = {l["business"].lower() for l in cold_leads if l.get("business")}

        client_auth = _get_sheets_client()
        sheet = client_auth.open("OROVA Leads").sheet1
        rows = sheet.get_all_values()

        escalated = 0
        for idx, row in enumerate(rows[1:], start=2):
            if daily_call_counter >= MAX_CALLS_PER_DAY:
                break

            status = row[7] if len(row) > 7 else ""
            company = row[4] if len(row) > 4 else "Unknown"
            contact = f"{row[1]} {row[2]}".strip() if len(row) > 2 else ""

            # Only escalate leads for this specific client and matching names
            if status in ("Email Sent", "Contacted") and company.lower() in cold_business_names:
                logger.info(f"📞 [ESCALATION] [Client {client_id}] True cold lead detected: {company}. Escalating to call.")

                # Mark as Ready for Call (requires CEO approval in Fast Lane)
                sheet.update_cell(idx, 8, "Ready for Call")
                notes = row[8] if len(row) > 8 else ""
                sheet.update_cell(idx, 9, f"{notes} | Client {client_id} Auto-escalated: {COLD_LEAD_DAYS_THRESHOLD}+ days no reply")

                # Update SQLite to match so it doesn't get flagged again
                DatabaseManager.query("UPDATE leads SET status = 'Ready for Call' WHERE LOWER(business) = ? AND client_id = ?", (company.lower(), int(client_id)))

                escalated += 1

                send_telegram_report(
                    f"📞 **Cold Lead Auto-Escalation** [Client {client_id}]\n\n"
                    f"**{company}** ({contact}) has not replied to emails for {COLD_LEAD_DAYS_THRESHOLD}+ days.\n"
                    f"Marked as **Ready for Call**. Approve in Fast Lane."
                )

        if escalated > 0:
            logger.info(f"📞 [ESCALATION] [Client {client_id}] Escalated {escalated} cold leads to call queue.")
        else:
            logger.info(f"📞 [ESCALATION] [Client {client_id}] No matching cold leads found in Sheets.")

    except Exception as e:
        logger.error(f"Cold Lead Escalation Error (Client {client_id}): {e}")


# ═══════════════════════════════════════════════════════
# SCHEDULE WRAPPERS
# ═══════════════════════════════════════════════════════
def fast_lane_job():
    clients = DatabaseManager.get_clients()
    # Always include internal OROVA client 0
    client_list = [{"id": 0}] + (clients if clients else [])
    for client in client_list:
        asyncio.run(run_ceo_fast_lane(client_id=client.get("id", 0)))

def slow_lane_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    for client in client_list:
        asyncio.run(run_lead_hunt_slow_lane(
            client_id=client.get("id", 0), 
            niche=client.get("niche"), 
            location=client.get("target_location")
        ))

def reply_monitor_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    for client in client_list:
        asyncio.run(run_reply_monitor(client_id=client.get("id", 0)))

def cold_escalation_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    for client in client_list:
        asyncio.run(run_cold_lead_escalation(client_id=client.get("id", 0)))

def cloud_backup_job():
    logger.info("☁️ [LANE 5] Triggering Google Drive Database Backup...")
    try:
        from app.core.database import DB_PATH
        from app.skills.drive_backup import upload_database
        upload_database(DB_PATH)
    except Exception as e:
        logger.error(f"[LANE 5] Backup Error: {e}")


# ═══════════════════════════════════════════════════════
# THE SCHEDULE — 4 Autonomous Lanes
# ═══════════════════════════════════════════════════════
schedule.every(APPROVAL_CHECK_MINUTES).minutes.do(fast_lane_job)     # Lane 1: Approvals + calls
schedule.every(REPLY_CHECK_MINUTES).minutes.do(reply_monitor_job)     # Lane 3: Reply monitoring
schedule.every(COLD_CALL_CHECK_MINUTES).minutes.do(cold_escalation_job) # Lane 4: Cold lead → call
schedule.every(HUNT_INTERVAL_MINUTES).minutes.do(slow_lane_job)       # Lane 2: Lead hunting
schedule.every(6).hours.do(cloud_backup_job)                          # Lane 5: Google Drive Backup

if __name__ == "__main__":
    logger.info("🚀 OROVA Autonomous Worker Initiated.")
    logger.info(f"   -> Lane 1 (Fast):       Every {APPROVAL_CHECK_MINUTES} min")
    logger.info(f"   -> Lane 2 (Hunt):       Every {HUNT_INTERVAL_MINUTES} min")
    logger.info(f"   -> Lane 3 (Replies):    Every {REPLY_CHECK_MINUTES} min")
    logger.info(f"   -> Lane 4 (Escalation): Every {COLD_CALL_CHECK_MINUTES} min")
    logger.info(f"   -> Lane 5 (Cloud Backup): Every 6 hours")
    logger.info(f"   -> Daily call cap: {MAX_CALLS_PER_DAY}")
    logger.info(f"   -> Daily hunt cap: {MAX_RUNS_PER_DAY}")

    # Run immediately on startup
    fast_lane_job()
    slow_lane_job()

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"🚨 FATAL RUNTIME ERROR in worker loop: {e}. Worker is persisting.")
            time.sleep(10) # Wait before resuming to prevent tight crash looping
        time.sleep(1)
