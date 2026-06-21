import asyncio
import logging
import os
import sys
import threading
import time
from datetime import datetime
import pytz
import schedule
import httpx
import json
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

# Add app path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.skills.lead_gen_v3 import find_leads
from app.skills.outbound_dialer import trigger_retell_call
from app.skills.agentmail_skill import check_replies, send_outreach
from app.core.database import DatabaseManager
from app.skills.light_enrich import enrich_lead_lite
from app.skills.lead_validator import score_lead
from app.skills.opportunity_scanner import scan_opportunity
from app.skills.email_sequence_skill import start_drip_campaign

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def _run_async(coro):
    """Run an async coroutine safely. Prefers the running loop if available."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Use run_coroutine_threadsafe to avoid deadlock when called from
        # a thread that shares the main event loop (e.g., schedule jobs).
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=120)
    return asyncio.run(coro)


# ─── SHEETS COLUMNS CONFIGURATION ─────────────────────────────
# 0-indexed Python row list indices
COL_IDX_ID = 0
COL_IDX_COMPANY = 1      # Business (Company)
COL_IDX_OWNER = 2        # Owner (Contact Name)
COL_IDX_EMAIL = 3        # Email
COL_IDX_PHONE = 4        # Phone
COL_IDX_WEBSITE = 5      # Website
COL_IDX_URL = 6          # URL
COL_IDX_STATUS = 7       # Status
COL_IDX_SCORE = 8        # Score
COL_IDX_SOURCE = 9       # Source
COL_IDX_DATE = 10        # Date
COL_IDX_NOTES = 11       # Notes

# 1-indexed Google Sheets column numbers for updates
COL_SHEET_STATUS = 8     # Column H
COL_SHEET_NOTES = 12     # Column L
COL_SHEET_CALL_ID = 13   # Column M (Place Call ID here)

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
MAX_CALLS_PER_DAY = int(os.getenv("MAX_CALLS_PER_DAY", "5"))           # Safety cap for Retell calls
COLD_LEAD_DAYS_THRESHOLD = int(os.getenv("COLD_LEAD_DAYS_THRESHOLD", "5"))    # Days before escalating to phone call
MAX_DAILY_COST = 5.0            # $5.00 daily safety cap

# Security: Wallet Drain Safeguard
daily_hunt_counter = 0
daily_call_counter = 0
_hunt_counter_lock = threading.Lock()
_call_counter_lock = threading.Lock()
_pst_tz = pytz.timezone('America/Los_Angeles')
last_reset_day = datetime.now(_pst_tz).day


def _reset_daily_counters():
    """Reset daily counters at midnight PST (thread-safe)."""
    global daily_hunt_counter, daily_call_counter, last_reset_day
    _pst_tz = pytz.timezone('America/Los_Angeles')
    current_day = datetime.now(_pst_tz).day
    if current_day != last_reset_day:
        with _hunt_counter_lock:
            daily_hunt_counter = 0
        with _call_counter_lock:
            daily_call_counter = 0
        last_reset_day = current_day


def _get_sheets_client():
    """Get authorized Google Sheets client using env vars or file."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_b64:
        import base64
        creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
    return gspread.authorize(creds)


# Cached at module level
_TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_TG_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")

async def send_telegram_report(message):
    """Send a report to Mark via Telegram (async, non-blocking)."""
    if not _TG_TOKEN or not _TG_CHAT_ID:
        logger.warning("Telegram report skipped: TOKEN or CHAT_ID missing.")
        return
    url = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, data={"chat_id": _TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})
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
        loop = asyncio.get_running_loop()
        client_auth = await loop.run_in_executor(None, _get_sheets_client)
        sheet_name = os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")
        sheet = await loop.run_in_executor(None, lambda: client_auth.open(sheet_name).sheet1)
        rows = await loop.run_in_executor(None, sheet.get_all_values)

        for idx, row in enumerate(rows[1:], start=2):
            status = row[COL_IDX_STATUS] if len(row) > COL_IDX_STATUS else ""
            
            # --- Execute approved calls ---
            if status == "Approved":
                # Lock row immediately to prevent duplicate Retell escalation races
                await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Processing"))
                await _execute_approved_call(sheet, row, idx, client_id=client_id)

    except Exception as e:
        logger.error(f"Fast Lane Error (Client {client_id}): {e}")


async def _execute_approved_call(sheet, row, idx, client_id=0):
    """Execute a call for an approved lead."""
    global daily_call_counter
    _reset_daily_counters()
    loop = asyncio.get_running_loop()

    # SAFETY: Do not call outside of 9 AM - 5 PM California time (PST)
    pst_tz = pytz.timezone('America/Los_Angeles')
    now_pst = datetime.now(pst_tz)
    if now_pst.hour < 9 or now_pst.hour >= 17:
        logger.info(f"⏳ [FAST Lane] Call queued for {row[COL_IDX_COMPANY]}, but it is outside PST business hours ({now_pst.strftime('%H:%M')}). Waiting.")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Approved"))  # Release lock
        return

    with _call_counter_lock:
        if daily_call_counter >= MAX_CALLS_PER_DAY:
            logger.info(f"📞 Daily call limit ({MAX_CALLS_PER_DAY}) reached. Skipping.")
            await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Approved"))  # Release lock
            return
        # Reserve the slot atomically
        daily_call_counter += 1

    phone = row[COL_IDX_PHONE] if len(row) > COL_IDX_PHONE else ""
    company = row[COL_IDX_COMPANY] if len(row) > COL_IDX_COMPANY else ""
    contact = row[COL_IDX_OWNER] if len(row) > COL_IDX_OWNER else ""
    intel = row[COL_IDX_NOTES] if len(row) > COL_IDX_NOTES else ""

    logger.info(f"📞 [CALL] Triggering Retell for {company} ({phone})...")

    context = {
        "business_name": company,
        "contact_name": contact,
        "icebreaker": intel,
        "offer_gap": "",
    }

    # Run trigger_retell_call (check if async/coroutine, else run in thread pool executor)
    import inspect
    if inspect.iscoroutinefunction(trigger_retell_call):
        result = await trigger_retell_call(phone, context)
    else:
        result = await loop.run_in_executor(None, trigger_retell_call, phone, context)

    if result.get("success"):
        call_id = result.get("call_id")
        logger.info(f"✅ [CALL] Success! ID: {call_id}")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Call Initiated"))
        # Ensure enough columns
        while len(row) < COL_SHEET_CALL_ID:
            row.append("")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_CALL_ID, call_id))

        await loop.run_in_executor(None, lambda: send_telegram_report(
            f"📞 **Call Initiated**\n\n"
            f"I am now calling **{company}** ({contact}).\n"
            f"Call ID: `{call_id}`"
        ))

        # Update SQLite metrics
        try:
            metrics = await DatabaseManager.aget_metrics(client_id)
            await DatabaseManager.aupdate_metrics({"calls_made": metrics.get("calls_made", 0) + 1}, client_id=client_id)
        except Exception:
            pass
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"❌ [CALL] Failed: {error}")
        with _call_counter_lock:
            daily_call_counter -= 1  # Release slot on failure
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Call Failed"))
        await loop.run_in_executor(None, lambda: send_telegram_report(f"⚠️ **Call Failed**\n\nError calling **{company}**: {error}"))


# ═══════════════════════════════════════════════════════
# LANE 2: SLOW LANE — Lead hunting
# Runs every 60 minutes
# ═══════════════════════════════════════════════════════
async def run_lead_hunt_slow_lane(client_id=0, niche=None, location=None):
    """🕵️ Hunt for new leads via multi-tier search."""
    global daily_hunt_counter
    _reset_daily_counters()
    loop = asyncio.get_running_loop()

    with _call_counter_lock:
        if daily_hunt_counter >= MAX_RUNS_PER_DAY:
            logger.info(f"🌙 [SLOW LANE] [Client {client_id}] Daily limit reached. Skipping lead hunt.")
            return
        daily_hunt_counter += 1  # Reserve slot atomically

    # Check Cost Guardrail
    metrics = await DatabaseManager.aget_metrics(client_id)
    if float(metrics.get("cost", 0)) >= MAX_DAILY_COST:
        logger.warning(f"🛑 [WALLET] Daily cost limit (${MAX_DAILY_COST}) reached for Client {client_id}. Halting.")
        with _call_counter_lock:
            daily_hunt_counter -= 1  # Release slot
        return

    import random
    if not niche:
        niche = os.getenv("TARGET_NICHE") or None
        location = location or os.getenv("TARGET_LOCATION") or None

    if not niche:
        niches = [
            'exotic car dealer california',
            'luxury car dealership california',
            'high end car tuning california',
            'exotic car rental california',
            'custom vehicle wrapping california',
            'hypercar dealer california',
            'luxury car storage california',
            'high end car restoration california',
            'custom home builder california',
            'private jet california',
            'yacht charter california'
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

            # Map new field names from lead_gen_v3 to expected field names
            for lead in leads:
                if isinstance(lead, dict):
                    if lead.get("owner_name") and not lead.get("owner"):
                        lead["owner"] = lead["owner_name"]

            # Save each lead to SQLite
            for lead in leads:
                if isinstance(lead, dict):
                    # ── [NEW] Yelp URL owner name from slug (pre-enrichment) ──
                    # Example yelp.com/biz/casey-martin → owner "Casey Martin"
                    yelp_url = lead.get("url", "").lower()
                    if "yelp.com/biz/" in yelp_url and not lead.get("owner_name"):
                        biz_slug = yelp_url.split("/biz/")[-1].split("?")[0].split("#")[0]
                        slug_parts = [p for p in biz_slug.split("-") if p]
                        words = [w for w in slug_parts if w and not w.isdigit()]
                        if 2 <= len(words) <= 4 and not any(kw in biz_slug.lower() for kw in ["auto", "tint", "wrap", "detail", "pro"]):
                            candidate = " ".join(w.title() for w in words[:2])
                            lead["owner_name"] = candidate
                            logger.info(f"[ENRICH] → Owner from Yelp slug: {candidate}")
                            # Map to owner for enrich_lead_lite compatibility
                            lead["owner"] = candidate
                    # ─────────────────────────────────────────────────────────

                    # [Enrichment] Find owner, email, phone, website
                    lead = await enrich_lead_lite(lead)

                    # ── [NEW] Run actual AI scoring ──
                    try:
                        score_result = score_lead(
                            company_name=lead.get("business", ""),
                            company_size="unknown",
                            industry=lead.get("vertical", niche) or "unknown",
                            contact_type="unknown",
                            response_signals=None,
                        )
                        lead["score"] = score_result.get("score", 0)
                    except Exception as e:
                        logger.warning(f"[SCORE] Lead scoring failed: {e}")
                        lead["score"] = 0
                    # ──────────────────────────────────────────

                    lead["icebreaker"] = "Pending review..."

                    # Populate CRM Metadata
                    lead["source"] = lead.get("source_type", "Yelp Direct" if "yelp.com" in (lead.get("url") or "") else "Web Search")
                    lead["date"] = datetime.now().strftime("%Y-%m-%d")
                    lead["vertical"] = niche
                    
                    lead_id = await DatabaseManager.asave_lead(lead, default_vertical=niche, client_id=client_id)

                    # ── [PIPELINE] Send outreach email + enroll in drip ──
                    if lead_id and lead_id != -1:
                        lead_email = lead.get("email", "").strip()
                        lead_phone = lead.get("phone", "").strip()
                        lead_owner = lead.get("owner") or lead.get("owner_name") or "there"
                        lead_biz = lead.get("business", "your business")

                        # Send initial cold outreach email
                        if lead_email:
                            try:
                                subject = f"Quick question about {lead_biz}"
                                body = (
                                    f"Hi {lead_owner},\n\n"
                                    f"I came across {lead_biz} and was really impressed by what you're doing. "
                                    f"I'd love to learn more about your operations and see if there's a way we could help streamline things.\n\n"
                                    f"Would you be open to a quick 15-minute chat this week?\n\n"
                                    f"Best,\nNova @ OROVA"
                                )
                                outreach_result = await send_outreach(
                                    to=lead_email,
                                    subject=subject,
                                    body=body,
                                    recipient_context=f"Owner of {lead_biz} in {niche} vertical",
                                    lead_id=lead_id,
                                    strategy="cold_intro",
                                    niche=niche,
                                    client_id=client_id,
                                )
                                if outreach_result.get("status") == "success":
                                    logger.info(f"   -> ✅ Outreach email sent to {lead_email} (lead {lead_id})")
                                    lead["status"] = "Email Sent"
                                else:
                                    logger.warning(f"   -> ⚠️ Outreach email failed for {lead_email}: {outreach_result.get('error','unknown')}")
                            except Exception as email_err:
                                logger.warning(f"   -> ⚠️ Outreach email error for {lead_email}: {email_err}")

                        # Enroll in cold_intro_drip for automated follow-ups
                        try:
                            drip_result = await start_drip_campaign(lead_id, sequence_type="cold_intro_drip")
                            if drip_result.get("status") == "success":
                                logger.info(f"   -> 📧 Enrolled lead {lead_id} in cold_intro_drip sequence")
                            else:
                                logger.warning(f"   -> ⚠️ Drip enrollment failed for lead {lead_id}: {drip_result.get('error','unknown')}")
                        except Exception as drip_err:
                            logger.warning(f"   -> ⚠️ Drip enrollment error for lead {lead_id}: {drip_err}")
                    # ────────────────────────────────────────────────────────

            # Update metrics
            try:
                metrics = await DatabaseManager.aget_metrics(client_id)
                await DatabaseManager.aupdate_metrics({
                    "leads_found": metrics.get("leads_found", 0) + count
                }, client_id=client_id)
            except Exception:
                pass

            await loop.run_in_executor(None, lambda: send_telegram_report(
                f"☀️ **Lead Hunt Complete**\n\n"
                f"Found **{count}** new leads for '{query}'.\n\n"
                f"{summary_text[:500]}"
            ))
        else:
            logger.info("   -> No leads found this shift.")

        logger.info(f"   -> Hunt complete. Total runs today: {daily_hunt_counter}")

    except Exception as e:
        logger.error(f"   !!! ERROR in Slow Lane: {e}")
        await loop.run_in_executor(None, lambda: send_telegram_report(f"⚠️ **Lead Hunt Error**: {str(e)}"))


# ═══════════════════════════════════════════════════════
# LANE 3: REPLY MONITOR — Check for prospect responses
# Runs every 5 minutes
# ═══════════════════════════════════════════════════════
async def run_reply_monitor(client_id=0):
    """📬 Check AgentMail for new prospect replies."""
    logger.info(f"📬 [REPLY MONITOR] [Client {client_id}] Checking for new messages...")
    try:
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(None, lambda: check_replies(limit=5))
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
                await loop.run_in_executor(None, lambda: send_telegram_report(report))

                # Update reply metrics
                try:
                    metrics = await DatabaseManager.aget_metrics(client_id)
                    await DatabaseManager.aupdate_metrics({
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
    """📞 Identify leads that haven't replied and auto-trigger RetellAI calls."""
    global daily_call_counter
    _reset_daily_counters()
    logger.info(f"📞 [ESCALATION] [Client {client_id}] Checking for cold leads...")
    try:
        loop = asyncio.get_running_loop()
        pst_tz = pytz.timezone('America/Los_Angeles')
        now_pst = datetime.now(pst_tz)

        # Give a little buffer for cold calls: 10 AM to 4 PM PST
        if now_pst.hour < 10 or now_pst.hour >= 16:
            logger.info(f"⏳ [ESCALATION] Outside prime calling hours ({now_pst.strftime('%I:%M %p')} PST). Suspending escalations.")
            return

        if daily_call_counter >= MAX_CALLS_PER_DAY:
            logger.info(f"📞 [ESCALATION] Daily call cap ({MAX_CALLS_PER_DAY}) reached. Skipping.")
            return

        cold_leads = await DatabaseManager.aget_cold_leads(COLD_LEAD_DAYS_THRESHOLD, client_id=client_id)
        if not cold_leads:
            logger.info(f"📞 [ESCALATION] [Client {client_id}] No true cold leads to escalate.")
            return

        escalated = 0
        called = 0

        for lead in cold_leads:
            if daily_call_counter >= MAX_CALLS_PER_DAY:
                logger.info(f"📞 [ESCALATION] Daily call cap reached mid-batch. Stopping.")
                break

            business = lead.get("business", "Unknown")
            phone = lead.get("phone", "")
            contact = lead.get("owner", "")
            email = lead.get("email", "")
            lead_id = lead.get("id", 0)

            # ── [PIPELINE] Try email re-engagement BEFORE phone call ──
            if email:
                try:
                    re_subject = f"Re: Quick question about {business}"
                    re_body = (
                        f"Hi {contact or 'there'},\n\n"
                        f"Just circling back on my earlier note about {business}. "
                        f"I know things get busy — no pressure at all, but I'd still love to connect if you have 10 minutes this week.\n\n"
                        f"Best,\nNova @ OROVA"
                    )
                    email_result = await send_outreach(
                        to=email,
                        subject=re_subject,
                        body=re_body,
                        recipient_context=f"Re-engagement for cold lead: {business}",
                        lead_id=lead_id,
                        strategy="cold_escalation",
                        niche=lead.get("vertical", ""),
                        client_id=client_id,
                    )
                    if email_result.get("status") == "success":
                        logger.info(f"📧 [ESCALATION] Re-engagement email sent to {email} for {business}")
                        await DatabaseManager.query(
                            "UPDATE leads SET status = 'Re-Engaged' WHERE id = ? AND client_id = ?",
                            (int(lead_id), int(client_id))
                        )
                        escalated += 1
                        continue  # Email sent — skip phone call, give them time to reply
                    else:
                        logger.warning(f"⚠️ [ESCALATION] Re-engagement email failed for {email}: {email_result.get('error','')}")
                except Exception as email_err:
                    logger.warning(f"⚠️ [ESCALATION] Email re-engagement error for {business}: {email_err}")

            if not phone:
                logger.info(f"📞 [ESCALATION] Skipping {business} — no phone number on file.")
                # Still mark as "Ready for Call" so it shows up in dashboard
                await DatabaseManager.query(
                    "UPDATE leads SET status = 'Ready for Call' WHERE LOWER(business) = ? AND client_id = ?",
                    (business.lower(), int(client_id))
                )
                escalated += 1
                continue

            # Trigger RetellAI call directly
            logger.info(f"📞 [ESCALATION] Triggering cold call for {business} ({phone})...")
            context = {
                "business_name": business,
                "contact_name": contact,
                "icebreaker": f"Following up on our email about improving your online presence",
                "call_type": "cold_escalation",
            }

            try:
                import inspect
                if inspect.iscoroutinefunction(trigger_retell_call):
                    result = await trigger_retell_call(phone, context)
                else:
                    result = await loop.run_in_executor(None, trigger_retell_call, phone, context)

                if result.get("success"):
                    call_id = result.get("call_id")
                    called += 1
                    logger.info(f"✅ [ESCALATION] Cold call triggered for {business}. Call ID: {call_id}")

                    # Update lead status in SQLite
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Cold Call Initiated' WHERE LOWER(business) = ? AND client_id = ?",
                        (business.lower(), int(client_id))
                    )

                    await loop.run_in_executor(None, lambda: send_telegram_report(
                        f"📞 **Cold Lead Auto-Call** [Client {client_id}]\n\n"
                        f"**{business}** ({contact}) — no reply for {COLD_LEAD_DAYS_THRESHOLD}+ days.\n"
                        f"Phone: `{phone}`\n"
                        f"Call ID: `{call_id}`"
                    ))
                else:
                    error = result.get("error", "Unknown")
                    logger.warning(f"⚠️ [ESCALATION] Cold call failed for {business}: {error}")
                    # Mark as "Ready for Call" as fallback
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Ready for Call' WHERE LOWER(business) = ? AND client_id = ?",
                        (business.lower(), int(client_id))
                    )
            except Exception as call_err:
                logger.error(f"❌ [ESCALATION] Call trigger error for {business}: {call_err}")
                await DatabaseManager.query(
                    "UPDATE leads SET status = 'Ready for Call' WHERE LOWER(business) = ? AND client_id = ?",
                    (business.lower(), int(client_id))
                )

            escalated += 1

            # Rate limit: wait between calls
            if called < MAX_CALLS_PER_DAY:
                await asyncio.sleep(5)

        logger.info(f"📞 [ESCALATION] [Client {client_id}] Processed {escalated} cold leads, triggered {called} calls.")

        if called > 0:
            await loop.run_in_executor(None, lambda: send_telegram_report(
                f"📞 **Cold Lead Escalation Complete** [Client {client_id}]\n\n"
                f"Triggered **{called}** auto-calls for leads that went cold after {COLD_LEAD_DAYS_THRESHOLD} days."
            ))

    except Exception as e:
        logger.error(f"Cold Lead Escalation Error (Client {client_id}): {e}")


# ═══════════════════════════════════════════════════════
# SCHEDULE WRAPPERS
# ═══════════════════════════════════════════════════════
def fast_lane_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_ceo_fast_lane(client_id=c.get("id", 0)) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def slow_lane_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_lead_hunt_slow_lane(
            client_id=c.get("id", 0), 
            niche=c.get("niche"), 
            location=c.get("target_location")
        ) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def reply_monitor_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_reply_monitor(client_id=c.get("id", 0)) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def cold_escalation_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_cold_lead_escalation(client_id=c.get("id", 0)) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def cloud_backup_job():
    logger.info("☁️ [LANE 5] Triggering Google Drive Database Backup...")
    try:
        from app.core.database import DB_PATH
        from app.skills.drive_backup import upload_database
        upload_database(DB_PATH)
    except Exception as e:
        logger.error(f"[LANE 5] Backup Error: {e}")

def ceo_brain_job():
    logger.info("[LANE 6] Triggering Nova CEO Brain Morning Brief...")
    from app.core.ceo_brain import CEOBrain
    brain = CEOBrain()
    _run_async(brain.morning_brief())

def health_check_job():
    logger.info("[LANE 7] Triggering Pipeline Health Check...")
    from app.core.ceo_brain import CEOBrain
    brain = CEOBrain()
    _run_async(brain.pipeline_health_check())

def self_improvement_job():
    logger.info("[LANE 8] Triggering Self-Improvement Loop...")
    from app.core.self_improvement import ImprovementLoop
    loop = ImprovementLoop()
    _run_async(loop.run())

def sequence_drip_job():
    logger.info("[LANE 9] Triggering Drip Sequence Sender...")
    from app.skills.email_sequence_skill import send_pending_drip_emails
    _run_async(send_pending_drip_emails())

def reply_and_drip_check_job():
    logger.info("[REPLY & DRIP CHECK] Checking replies and processing drips...")
    reply_monitor_job()
    from app.skills.email_sequence_skill import check_drip_replies_and_process
    _run_async(check_drip_replies_and_process())


# ═══════════════════════════════════════════════════════
# THE SCHEDULE — 9 Autonomous Lanes
# ═══════════════════════════════════════════════════════
schedule.every(APPROVAL_CHECK_MINUTES).minutes.do(fast_lane_job)      # Lane 1: Approvals + calls
schedule.every(HUNT_INTERVAL_MINUTES).minutes.do(slow_lane_job)        # Lane 2: Lead hunting
schedule.every(REPLY_CHECK_MINUTES).minutes.do(reply_and_drip_check_job) # Lane 3: Reply + Drip monitoring
schedule.every(COLD_CALL_CHECK_MINUTES).minutes.do(cold_escalation_job)  # Lane 4: Cold lead → call
schedule.every(6).hours.do(cloud_backup_job)                           # Lane 5: Google Drive Backup
schedule.every().day.at("17:00").do(ceo_brain_job)                     # Lane 6: CEO Morning Brief (17:00 UTC = ~9-10 AM Pacific)
schedule.every(2).hours.do(health_check_job)                           # Lane 7: Pipeline Health Check
schedule.every(6).hours.do(self_improvement_job)                       # Lane 8: Strategy Self-Improvement
schedule.every(1).hours.do(sequence_drip_job)                          # Lane 9: Drip Sequence Sender


# ── Graceful shutdown event ──────────────────────────────────
_stop_event = threading.Event()


def start_worker_scheduler() -> threading.Thread:
    """Start the schedule loop in a daemon thread. Safe to call from FastAPI lifespan."""
    _stop_event.clear()
    th = threading.Thread(target=_scheduler_loop, daemon=True)
    th.start()
    return th


def stop_worker_scheduler():
    """Signal the scheduler loop to stop gracefully."""
    logger.info("🛑 Signaling worker scheduler to stop...")
    _stop_event.set()


def _scheduler_loop():
    import schedule
    logger.info("⏱️ Worker scheduler loop started.")
    while not _stop_event.is_set():
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"[SCHED] Scheduler error: {e}")
        # Sleep in small increments so we can respond to stop signal quickly
        _stop_event.wait(1)


if __name__ == "__main__":
    logger.error("🚨 app/worker.py is designed to run as a library imported by app.main:app (via lifespan). Running it directly re-introduces the duplicate-scheduler bug. Start the FastAPI app instead: uvicorn app.main:app")
    import sys
    sys.exit(1)
