import asyncio
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
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
from app.skills.lead_validator import score_lead_icp
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
PHONE_FIRST_CHECK_MINUTES = int(os.getenv("PHONE_FIRST_CHECK_MINUTES", "20"))
PHONE_FIRST_BATCH = int(os.getenv("PHONE_FIRST_BATCH", "25"))   # rows evaluated per pass
MAX_RUNS_PER_DAY = 10
MAX_CALLS_PER_DAY = int(os.getenv("MAX_CALLS_PER_DAY", "5"))           # Safety cap for Retell calls
COLD_LEAD_DAYS_THRESHOLD = int(os.getenv("COLD_LEAD_DAYS_THRESHOLD", "5"))    # Days before escalating to phone call
MAX_DAILY_COST = 5.0            # $5.00 daily safety cap

# Hunt-report Telegram debounce (2026-08-02). Same shape as the health lane's
# debounce in ceo_brain (#122): a state key plus a cooldown, keyed on a
# fingerprint of what was actually found. 24h is deliberately long — the hunt
# runs many times a day and rediscovers the same businesses after every deploy
# wipe, which is exactly the spam the owner reported.
HUNT_REPORT_STATE_KEY = "hunt_report_debounce"
HUNT_REPORT_COOLDOWN_S = float(os.getenv("HUNT_REPORT_COOLDOWN_S", str(24 * 3600)))

# Default hunt rotation — mirrors business_context.json's primary_verticals
# (profitability-plan §2.1/§5.2, owner-approved 2026-07-10). Exotic auto is
# split into sub-niches so the champion/challenger loop can learn WHICH
# sub-vertical converts, not just the top-level niche. Private jet / yacht
# charter removed from the rotation: decision-makers there are family
# offices/brokerages, not owners reachable by cold email — still huntable
# via an explicit TARGET_NICHE override.
DEFAULT_HUNT_NICHES = [
    # Re-ranked 2026-07-23 (ADR-0012) by the qualifying test: does ONE extra
    # closed deal per month more than cover the ~$6.5-7.5K all-in monthly cost?
    #
    # LEAD vertical — custom homes / high-end remodeling. A $100K+ job grosses
    # $20-50K, so a single extra job pays 4-7 months of retainer; the price
    # objection dies on the call. Owner-operated, already buys marketing.
    # NOTE: the hunt picks with random.choice() — UNIFORMLY. So the number of
    # entries per vertical IS the weighting. Composition below is deliberate:
    # ~78% homes/remodel, ~22% luxury RE.
    #
    # Med spas removed from the rotation 2026-08-09 (ADR-0015 supersedes the
    # ADR-0012 ranking) on the owner's direct statement: "our ICP was never med
    # spas." They were 3 of 12 entries, so a QUARTER of every hunt's discovery
    # budget was being spent on a vertical we do not sell to — while the actual
    # pipeline stood at 5 contractors. This is the automotive removal above,
    # repeated for the same reason and with the same remedy: the cheapest
    # control is not to search for it. Still reachable via TARGET_NICHE if that
    # decision is ever revisited.
    #
    # Automotive removed from the rotation 2026-08-02 on owner report ("why is
    # nova in telegram always sending me automotive leads?"). It was 2 of 14
    # entries, so ~14% of every hunt was an automotive search — and the ICP gate
    # did not catch the results, for two reasons proven by probe:
    #   1. worker.py sets lead["vertical"] = niche, i.e. the QUERY STRING. The
    #      query 'exotic car dealer california' contains "exotic", which tripped
    #      the ADR-0012 opportunistic exemption for EVERY lead it returned —
    #      including plain dealers and repair shops that are nothing of the kind.
    #   2. 'ceramic coating auto detailing california' returns detailing/tint/
    #      wrap/PPF shops, none of which appear in any off-ICP list.
    # Both holes are fixed in lead_validator, but the cheapest control is not to
    # search for it: ADR-0012 ranks exotic auto "opportunistic only", and a
    # rotation slot spends discovery budget on it every seventh run.
    # Exotic/luxury auto remains reachable via an explicit TARGET_NICHE override.
    'custom home builder california',
    'luxury home remodeling california',
    'high end kitchen remodeler california',
    'high end bathroom remodeler california',
    'custom home builder los angeles',
    'luxury home builder san diego',
    'whole home remodel contractor california',
    # SECOND (~22%) — luxury real estate top producers & premium design.
    'luxury real estate agent california',
    'luxury interior designer california',
]


def _parse_niche_range(raw: str) -> list:
    """TARGET_NICHE may hold a RANGE of niches (comma / semicolon / newline
    separated), e.g. 'exotic car dealer, luxury remodel, luxury real estate'.
    Split it so the hunt rotates ONE niche per run — cramming the whole string
    into a single SerpAPI query returns generic junk (live-observed 2026-07-12).
    Returns [] for an empty/blank value so the caller falls back to the
    curated DEFAULT_HUNT_NICHES rotation."""
    if not raw:
        return []
    normalized = raw.replace(";", ",").replace("\n", ",")
    return [n.strip() for n in normalized.split(",") if n.strip()]

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
        "owner_name": contact,
        "icebreaker": intel,
        "offer_gap": "",
        "client_id": client_id,
    }

    # Run trigger_retell_call (check if async/coroutine, else run in thread pool executor)
    import inspect
    if inspect.iscoroutinefunction(trigger_retell_call):
        result = await trigger_retell_call(phone, context)
    else:
        result = await loop.run_in_executor(None, trigger_retell_call, phone, context)

    if result.get("skipped"):
        logger.info(f"⏭️ [CALL] Retell not configured — skipping call for {company}. Set RETELL_API_KEY to enable.")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Ready for Call"))
        return
    if result.get("success"):
        call_id = result.get("call_id")
        logger.info(f"✅ [CALL] Success! ID: {call_id}")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Call Initiated"))
        # Ensure enough columns
        while len(row) < COL_SHEET_CALL_ID:
            row.append("")
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_CALL_ID, call_id))

        await send_telegram_report(
            f"📞 **Call Initiated**\n\n"
            f"I am now calling **{company}** ({contact}).\n"
            f"Call ID: `{call_id}`"
        )

        # Update SQLite metrics
        try:
            metrics = await DatabaseManager.aget_metrics(client_id)
            await DatabaseManager.aupdate_metrics({"calls_made": metrics.get("calls_made", 0) + 1}, client_id=client_id)
        except Exception:
            pass

        # Per-lead call counter — the Leads sheet's "Called" column reads this.
        # Incremented ONLY here, after Retell accepted the call, so a lead the
        # consent or DNC gate blocked still reads as never-called. A blocked
        # lead has not been worked and must not look like it has.
        try:
            _lid = (context or {}).get("lead_id")
            if _lid:
                await DatabaseManager.query(
                    "UPDATE leads SET call_count = COALESCE(call_count,0) + 1, "
                    "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (_lid,))
        except Exception as _cc_err:
            logger.warning(f"[CALL] call_count not incremented for lead "
                           f"{(context or {}).get('lead_id')}: {_cc_err}")
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"❌ [CALL] Failed: {error}")
        with _call_counter_lock:
            daily_call_counter -= 1  # Release slot on failure
        await loop.run_in_executor(None, lambda: sheet.update_cell(idx, COL_SHEET_STATUS, "Call Failed"))
        await send_telegram_report(f"⚠️ **Call Failed**\n\nError calling **{company}**: {error}")


# ═══════════════════════════════════════════════════════
# LANE 2: SLOW LANE — Lead hunting
# Runs every 60 minutes
# ═══════════════════════════════════════════════════════
async def run_lead_hunt_slow_lane(client_id=0, niche=None, location=None, state=None):
    """🕵️ Hunt for new leads via multi-tier search.

    `state` is the JURISDICTION (a two-letter code) and decides which licence
    registry the discovery layer queries. It is deliberately separate from
    `niche`/`location`, which are free-text SEARCH terms: the hunt lane knows
    perfectly well which state it is targeting, and making discovery re-derive
    that by substring-matching the search string is what left California
    falling through to the legacy scrapers. Falls back to TARGET_STATE, then to
    query inference, so an unset env keeps today's behaviour exactly.
    """
    global daily_hunt_counter
    _reset_daily_counters()
    loop = asyncio.get_running_loop()

    with _hunt_counter_lock:
        if daily_hunt_counter >= MAX_RUNS_PER_DAY:
            logger.info(f"🌙 [SLOW LANE] [Client {client_id}] Daily limit reached. Skipping lead hunt.")
            return
        daily_hunt_counter += 1  # Reserve slot atomically

    # Check Cost Guardrail
    metrics = await DatabaseManager.aget_metrics(client_id)
    if float(metrics.get("cost", 0)) >= MAX_DAILY_COST:
        logger.warning(f"🛑 [WALLET] Daily cost limit (${MAX_DAILY_COST}) reached for Client {client_id}. Halting.")
        with _hunt_counter_lock:
            daily_hunt_counter -= 1  # Release slot
        return

    import random
    if not niche:
        location = location or os.getenv("TARGET_LOCATION") or None
        # Rotate through TARGET_NICHE's range (one per run); [] -> curated list.
        target_niches = _parse_niche_range(os.getenv("TARGET_NICHE") or "")
        niche = random.choice(target_niches) if target_niches else None

    if not niche:
        query = random.choice(DEFAULT_HUNT_NICHES)
    else:
        query = f"{niche} {location if location else ''}".strip()

    # Jurisdiction, explicitly. Caller > TARGET_STATE env > let discovery infer.
    hunt_state = (state or os.getenv("TARGET_STATE") or "").strip().upper()

    logger.info(f"🕵️ [SLOW LANE] [Client {client_id}] Hunting for leads: {query}"
                f"{f' [state={hunt_state}]' if hunt_state else ''}")

    try:
        result = await find_leads(count=LEADS_TO_FIND_PER_RUN, query=query,
                                  state=hunt_state)

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

                    # [Decision-maker waterfall] Keep hunting the real buyer
                    # across sources (email-name inference, registry, team
                    # pages, search) instead of accepting the first pass. Runs
                    # before scoring so a discovered owner earns its +25.
                    try:
                        from app.skills.contact_waterfall import resolve_decision_maker, apply_decision_maker
                        if int(lead.get("owner_confidence") or 0) < 70:
                            dm = await resolve_decision_maker(lead)
                            apply_decision_maker(lead, dm)
                            if dm.name:
                                logger.info(f"[WATERFALL] {lead.get('business','?')}: "
                                            f"{dm.name} ({dm.title or 'role?'}) "
                                            f"conf={dm.confidence} via {dm.source}")
                    except Exception as e:
                        logger.warning(f"[WATERFALL] decision-maker resolve failed (non-fatal): {e}")

                    # ── Deterministic ICP scoring (fields enrichment actually
                    # collects; the old scorer got "unknown" for everything and
                    # returned a flat 50 for every live lead) ──
                    try:
                        score_result = score_lead_icp(lead)
                        lead["score"] = score_result.get("score", 0)
                        logger.info(f"[SCORE] {lead.get('business','?')}: {lead['score']} — {score_result.get('recommendation','')}")
                    except Exception as e:
                        logger.warning(f"[SCORE] Lead scoring failed: {e}")
                        lead["score"] = 0
                    # ──────────────────────────────────────────

                    lead["icebreaker"] = "Pending review..."

                    # ── Dossier (Analyst, stage-gated): deep research ONLY for
                    # HOT leads — research time/quota is spent where outreach
                    # will actually go. Gives the composer a real, verifiable
                    # icebreaker instead of a generic opener. Fail-open.
                    dossier = {}
                    try:
                        from app.skills.dossier import build_dossier, DOSSIER_MIN_SCORE
                        if lead.get("score", 0) >= DOSSIER_MIN_SCORE:
                            dossier = await build_dossier(lead)
                            if dossier.get("icebreaker"):
                                lead["icebreaker"] = dossier["icebreaker"]
                                logger.info(f"[DOSSIER] {lead.get('business','?')}: {dossier['icebreaker'][:80]}")
                            if dossier:
                                lead["notes"] = ((lead.get("notes") or "") + " | DOSSIER: "
                                                 + json.dumps(dossier, ensure_ascii=False)[:800]).strip(" |")
                    except Exception as e:
                        logger.warning(f"[DOSSIER] skipped (non-fatal): {e}")

                    # Populate CRM Metadata
                    from urllib.parse import urlparse as _urlparse
                    _host = _urlparse(lead.get("url") or "").netloc.lower()
                    _is_yelp = _host == "yelp.com" or _host.endswith(".yelp.com")  # dot-anchored: 'notyelp.com' must not match
                    lead["source"] = lead.get("source_type", "Yelp Direct" if _is_yelp else "Web Search")
                    lead["date"] = datetime.now().strftime("%Y-%m-%d")
                    # Only fall back to the search query — never overwrite a
                    # vertical the SOURCE actually knows (2026-08-09). Licence
                    # registries publish the real trade (specialtycode1desc:
                    # "General", "Roofing", "Masonry"); the niche is just the
                    # string we searched with. Clobbering the former with the
                    # latter is what put "custom home builder california" in
                    # the Niche column, and it is the same query-string-as-data
                    # confusion that made the ICP scorer rank nytimes.com level
                    # with a real contractor.
                    lead["vertical"] = lead.get("vertical") or niche

                    lead_id = await DatabaseManager.asave_lead(lead, default_vertical=niche, client_id=client_id)

                    # Unified event log (ADR-0007): Scout discovered a prospect.
                    if lead_id and lead_id != -1:
                        from app.core.event_log import alog_event
                        await alog_event(lead_id, "lead_discovered", "scout",
                                         payload={"source": lead.get("source", "hunt"),
                                                  "niche": niche, "score": lead.get("score", 0)})
                        if dossier:
                            await alog_event(lead_id, "dossier_built", "analyst",
                                             payload={"icebreaker": dossier.get("icebreaker", ""),
                                                      "observations": dossier.get("observations", [])})

                    # ── [PIPELINE] Send outreach email + enroll in drip ──
                    if lead_id and lead_id != -1:
                        lead_email = lead.get("email", "").strip()
                        lead_phone = lead.get("phone", "").strip()
                        lead_owner = lead.get("owner") or lead.get("owner_name") or "there"
                        lead_biz = lead.get("business", "your business")
                        email_status = lead.get("email_status", "")

                        # Guessed emails bounce ~40% of the time and poison sender
                        # reputation — route those leads to the call lane instead.
                        if lead_email and email_status == "guessed":
                            logger.info(f"   -> ⏭️ Email for lead {lead_id} is guessed ({lead_email}); skipping cold email, call lane will pick it up")

                        # Send initial cold outreach email — AI-personalized,
                        # framework picked by the champion/challenger loop so
                        # every send feeds real A/B data back into learning.
                        if lead_email and email_status != "guessed":
                            try:
                                from app.skills.outreach_orchestrator import compose_premium_outreach
                                from app.core.approval_gate import gate_allows
                                composed = await compose_premium_outreach(lead, niche=niche, client_id=client_id)
                                # Approval gate: cold email needs Mark's OK unless
                                # OUTREACH_AUTOPILOT=1. Skips send until approved.
                                if not await gate_allows(
                                    "email",
                                    {"lead_id": lead_id, "to": lead_email},
                                    reason=f"Cold email to {lead_biz} <{lead_email}> — subject: {composed['subject']}",
                                ):
                                    logger.info(f"   -> 🛡️ Cold email to {lead_email} awaiting approval; sends once Mark approves")
                                    lead["status"] = "Awaiting Approval"
                                else:
                                    outreach_result = await send_outreach(
                                        to=lead_email,
                                        subject=composed["subject"],
                                        body=composed["body"],
                                        recipient_context=f"{lead_owner} ({lead.get('owner_title') or 'Owner'}) of {lead_biz} in {niche} vertical",
                                        lead_id=lead_id,
                                        strategy=composed["framework"],
                                        niche=niche,
                                        client_id=client_id,
                                        # Already gated three lines up. Without this the
                                        # chokepoint gate would request approval a SECOND
                                        # time and, because approvals are single-use, the
                                        # one Mark just granted would already be spent —
                                        # so an approved email would never send.
                                        _approval_checked=True,
                                    )
                                    if outreach_result.get("status") == "success":
                                        logger.info(f"   -> ✅ Outreach email sent to {lead_email} (lead {lead_id})")
                                        lead["status"] = "Email Sent"
                                    else:
                                        logger.warning(f"   -> ⚠️ Outreach email failed for {lead_email}: {outreach_result.get('error','unknown')}")
                            except Exception as email_err:
                                logger.warning(f"   -> ⚠️ Outreach email error for {lead_email}: {email_err}")

                            # Enroll in cold_intro_drip for automated follow-ups.
                            #
                            # MOVED INSIDE the `if lead_email and email_status !=
                            # "guessed"` branch. It used to sit outside it and ran
                            # unconditionally, so leads with NO email address at all —
                            # which is most licence-registry rows — were enrolled in an
                            # email sequence that could never send to them, and leads
                            # with a pattern-GUESSED address were enrolled despite #124
                            # establishing that a guessed address must never be emailed.
                            #
                            # A follow-up sequence presupposes something to follow up ON.
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

            # ── Hunt-report debounce (2026-08-02) ────────────────────────────
            # Owner report: "i need Nova to stop spamming me with the thing
            # only once and done". This send was unconditional, and the lead
            # dedupe it relies on lives in the DB (main.py) — which is wiped by
            # every deploy on Render's ephemeral disk. So the same businesses
            # were rediscovered and re-announced indefinitely.
            #
            # Debounced on a fingerprint of the BUSINESS-NAME SET, reusing the
            # same state_store mechanism the health lane already uses (#122) —
            # an extension, not a second bookkeeping system. A genuinely
            # different batch pages immediately; an identical one stays quiet.
            # Fail-open: a state read/write error must send, never swallow.
            #
            # Honest limit: the state store is that same wiped-on-deploy DB, so
            # a redeploy resets the memory. It collapses the steady-state spam,
            # it does not survive a restart. The durable fix is the Drive
            # restore (owner action) — without it nothing in Nova remembers.
            import hashlib as _hashlib
            _names = sorted({(l.get("business") or "").strip().lower()
                             for l in leads if (l.get("business") or "").strip()})
            _fingerprint = _hashlib.sha256(
                "|".join(_names).encode("utf-8")).hexdigest()[:16]
            _should_report = True
            try:
                _prev = await DatabaseManager.get_state(HUNT_REPORT_STATE_KEY) or {}
                if not isinstance(_prev, dict):
                    _prev = {}
                _age_s = time.time() - float(_prev.get("sent_at") or 0)
                if (_prev.get("fingerprint") == _fingerprint
                        and _age_s < HUNT_REPORT_COOLDOWN_S):
                    _should_report = False
                    logger.info(
                        f"   -> 🔕 Hunt report unchanged ({_fingerprint}, "
                        f"{_age_s/3600:.1f}h ago) — suppressing duplicate Telegram "
                        f"report for the same {count} business(es)."
                    )
            except Exception as _dbe:
                logger.debug(f"   -> Hunt report debounce unavailable ({_dbe}); sending.")

            if _should_report:
                await send_telegram_report(
                    f"☀️ **Lead Hunt Complete**\n\n"
                    f"Found **{count}** new leads for '{query}'.\n\n"
                    f"{summary_text[:500]}"
                )
                try:
                    await DatabaseManager.set_state(
                        HUNT_REPORT_STATE_KEY,
                        {"fingerprint": _fingerprint, "sent_at": time.time(),
                         "count": count, "query": query},
                    )
                except Exception as _dbe:
                    logger.debug(f"   -> Could not persist hunt report state: {_dbe}")

            # Durability ladder (canonical helper, ADR-0010/SSoT): Drive
            # snapshot, Sheets fallback on failure. Extracted 2026-07-21 —
            # the hunt, CSV import, and reenrich paths all lost work to
            # disk wipes before sharing this one entry point. Fail-open.
            try:
                from app.core.durability import persist_leads_durably
                await persist_leads_durably(recent_count=count, source="hunt")
            except Exception as bk_err:
                logger.warning(f"   -> ⚠️ Post-hunt persistence error (non-fatal): {bk_err}")
        else:
            logger.info("   -> No leads found this shift.")

        logger.info(f"   -> Hunt complete. Total runs today: {daily_hunt_counter}")

    except Exception as e:
        logger.error(f"   !!! ERROR in Slow Lane: {e}")
        await send_telegram_report(f"⚠️ **Lead Hunt Error**: {str(e)}")


# ═══════════════════════════════════════════════════════
# LANE 3: REPLY MONITOR — Check for prospect responses
# Runs every 5 minutes
# ═══════════════════════════════════════════════════════
# HOT replies auto-progress to a booking-link reply, but the send is gated on
# Mark's approval (unless REPLIES_AUTOPILOT=1). Because the reply monitor advances
# a checkpoint and never re-reads a message, we can't rely on the outreach lane's
# "re-scan pending leads each cycle" pattern — so HOT replies are parked in a
# durable state-store queue and drained by process_pending_booking_replies().
_BOOKING_QUEUE_KEY = "pending_booking_replies"
_BOOKING_QUEUE_TTL_S = 3 * 24 * 3600     # give up auto-sending after 3 days
_MAX_BOOKING_ATTEMPTS = 6                 # ~one lane cycle apart; caps failures

_FROM_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _parse_email(from_field: str) -> str:
    """Pull the bare address out of a From header like 'Jane <jane@acme.com>'."""
    m = _FROM_EMAIL_RE.search(from_field or "")
    return m.group(0).lower() if m else ""


def _parse_name(from_field: str) -> str:
    """Pull the display name out of a From header, '' if it's just an address."""
    if not from_field:
        return ""
    name = from_field.split("<")[0].strip().strip('"').strip()
    return "" if ("@" in name or not name) else name


async def _lookup_lead_by_email(email: str):
    """Qualify a reply: match the sender to a known lead row, or None."""
    if not email:
        return None
    try:
        row = await DatabaseManager.query(
            "SELECT id, business, owner, email, client_id, status FROM leads "
            "WHERE lower(email) = lower(?) ORDER BY id DESC LIMIT 1",
            (email,), fetchone=True,
        )
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"[REPLY MONITOR] Lead lookup failed for {email}: {e}")
        return None


async def _enqueue_booking_replies(items):
    """Append HOT-reply booking jobs to the durable queue, de-duped by message_id.

    Callers must invoke this sequentially (never inside an asyncio.gather) so the
    read-modify-write of the shared state key can't race — reply_monitor_job runs
    the per-client monitors one at a time for exactly this reason.
    """
    if not items:
        return
    queue = await DatabaseManager.get_state(_BOOKING_QUEUE_KEY, []) or []
    existing = {i.get("message_id") for i in queue}
    added = 0
    for it in items:
        mid = it.get("message_id")
        if mid and mid not in existing:
            queue.append(it)
            existing.add(mid)
            added += 1
    if added:
        await DatabaseManager.set_state(_BOOKING_QUEUE_KEY, queue)
        logger.info(f"[REPLY MONITOR] Queued {added} HOT reply(ies) for booking-link send.")


async def run_reply_monitor(client_id=0):
    """📬 Check AgentMail for new prospect replies; auto-progress HOT ones.

    Every new reply is classified (HOT/WARM/COLD) and Mark is alerted. HOT replies
    are qualified against the lead DB and queued for a booking-link auto-reply.
    Returns the list of HOT items queued (used by tests / callers).
    """
    logger.info(f"📬 [REPLY MONITOR] [Client {client_id}] Checking for new messages...")
    hot_items = []
    try:
        res = await check_replies(limit=5, advance_checkpoint=False)
        if res.get("status") == "success" and res.get("count", 0) > 0:
            from app.skills.agentmail_skill import classify_reply_intent
            for msg in res.get("messages", []):
                sender = msg.get("from") or ""
                subject = msg.get("subject") or ""
                snippet = msg.get("snippet") or ""
                message_id = msg.get("message_id")

                try:
                    intent = await classify_reply_intent(subject, snippet, sender)
                except Exception as e:
                    logger.warning(f"[REPLY MONITOR] Classify failed ({e}); defaulting WARM.")
                    intent = "WARM"

                logger.info(f"✨ New reply from {sender}: {subject} [{intent}]")

                email = _parse_email(sender)
                lead = await _lookup_lead_by_email(email)

                # ── Record an opt-out so it is HONOURED, not just noticed ─────
                # The classifier already resolves opt-out language to COLD, which
                # stops an auto-reply on THIS message. It did not stop the next
                # drip cycle: nothing persisted the address, and send_outreach had
                # no pre-send check. Both halves are needed — CAN-SPAM requires
                # honouring an opt-out, not merely detecting one.
                if intent == "COLD" and email:
                    try:
                        from app.skills.agentmail_skill import is_optout_reply
                        from app.core.dnc import add_email_suppression
                        if is_optout_reply(subject, snippet):
                            await add_email_suppression(email, reason="reply opt-out")
                            logger.info("[REPLY MONITOR] Opt-out honoured — "
                                        "address added to the email suppression list.")
                    except Exception as e:
                        logger.error(f"[REPLY MONITOR] FAILED to record email "
                                     f"opt-out — MUST be actioned manually: {e}")

                if intent == "HOT" and message_id:
                    hot_items.append({
                        "message_id": message_id,
                        "sender": sender,
                        "email": email,
                        "name": (lead or {}).get("owner") or _parse_name(sender) or "there",
                        "business": (lead or {}).get("business", ""),
                        "lead_id": (lead or {}).get("id", 0),
                        "client_id": (lead or {}).get("client_id", client_id),
                        "subject": subject,
                        "created_at": time.time(),
                        "attempts": 0,
                    })
                    action_line = "🔥 HOT — queued a booking-link reply (sends on approval / autopilot)."
                    if lead:
                        try:
                            await DatabaseManager.query(
                                "UPDATE leads SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                ("Hot Reply", lead["id"]),
                            )
                        except Exception:
                            pass
                else:
                    action_line = "Review and reply manually if it's worth pursuing."

                emoji = {"HOT": "🔥", "WARM": "🌤️", "COLD": "❄️"}.get(intent, "📬")
                report = (
                    f"{emoji} **New Reply — {intent}** [Client {client_id}]\n\n"
                    f"👤 **From:** {sender}\n"
                    f"📧 **Subject:** {subject}\n"
                    f"📝 **Snippet:** \"{snippet[:200]}...\"\n\n"
                    f"{action_line}"
                )
                await send_telegram_report(report)

                # Update reply metrics
                try:
                    metrics = await DatabaseManager.aget_metrics(client_id)
                    await DatabaseManager.aupdate_metrics({
                        "replies_received": metrics.get("replies_received", 0) + 1
                    }, client_id=client_id)
                except Exception:
                    pass

            # Queue HOT items (sequential caller → race-free) before advancing.
            await _enqueue_booking_replies(hot_items)

            # Advance checkpoint only after all side effects (alerts, metrics) succeed
            latest_ts = res.get("latest_ts")
            if latest_ts:
                try:
                    from app.skills.agentmail_skill import _set_last_reply_check
                    ts_str = latest_ts.replace("Z", "+00:00")
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ok = await _set_last_reply_check(ts)
                    if not ok:
                        logger.error(f"[REPLY MONITOR] Checkpoint write failed for {latest_ts} — will retry next cycle.")
                except Exception as e:
                    logger.error(f"[REPLY MONITOR] Failed to advance checkpoint: {e}")
    except Exception as e:
        logger.error(f"Reply Monitor Error: {e}")
    return hot_items


async def process_pending_booking_replies():
    """Drain the HOT-reply queue: send each a booking-link reply once Mark approves
    (or REPLIES_AUTOPILOT is on). The Google Calendar event itself is created later,
    when the prospect actually books via the link (Cal.com webhook → cal_booking).

    Single sequential coroutine (its own worker pass) so the state read-modify-write
    can't race with the enqueue side.
    """
    queue = await DatabaseManager.get_state(_BOOKING_QUEUE_KEY, []) or []
    if not queue:
        return

    from app.core.approval_gate import gate_allows
    from app.skills.cal_booking import generate_meeting_intro_email, get_booking_link
    from app.skills.agentmail_skill import reply_to_email

    now = time.time()
    remaining = []
    for item in queue:
        message_id = item.get("message_id")
        if not message_id:
            continue  # malformed — drop
        if now - item.get("created_at", 0) > _BOOKING_QUEUE_TTL_S:
            logger.info(f"[BOOKING] Expiring stale HOT reply {message_id}.")
            continue
        if item.get("attempts", 0) >= _MAX_BOOKING_ATTEMPTS:
            logger.warning(f"[BOOKING] Giving up on {message_id} after {item['attempts']} tries.")
            await send_telegram_report(
                f"⚠️ Couldn't auto-send a booking link to {item.get('sender')} "
                f"after {item.get('attempts')} tries — please reply manually."
            )
            continue

        params = {"message_id": message_id, "to": item.get("email", "")}
        reason = (
            f"Booking-link reply to HOT lead "
            f"{item.get('business') or item.get('name') or item.get('sender')} "
            f"<{item.get('email')}>"
        )
        try:
            allowed = await gate_allows("reply", params, reason)
        except Exception as e:
            logger.error(f"[BOOKING] Gate error for {message_id} ({e}); will retry.")
            item["attempts"] = item.get("attempts", 0) + 1
            remaining.append(item)
            continue

        if not allowed:
            # Gate already pinged Mark (deduped). Keep for the next cycle.
            remaining.append(item)
            continue

        booking_link = get_booking_link(item.get("name", ""), item.get("business", ""))
        body = generate_meeting_intro_email(item.get("name", "there"), item.get("business", ""), booking_link)
        result = await reply_to_email(message_id, body)

        if result.get("status") == "success":
            logger.info(f"[BOOKING] Sent booking link to {item.get('email')} (lead {item.get('lead_id')}).")
            if item.get("lead_id"):
                try:
                    await DatabaseManager.query(
                        "UPDATE leads SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        ("Booking Sent", item["lead_id"]),
                    )
                except Exception:
                    pass
            link_note = f"\n🔗 {booking_link}" if booking_link else "\n(No booking link configured — asked them for times.)"
            await send_telegram_report(
                f"📅 **Booking link sent** to {item.get('name') or item.get('sender')}"
                f"{(' — ' + item.get('business')) if item.get('business') else ''}.{link_note}"
            )
            # success → do not re-queue
        else:
            logger.warning(f"[BOOKING] Reply send failed for {message_id}: {result.get('message') or result.get('error')}")
            item["attempts"] = item.get("attempts", 0) + 1
            remaining.append(item)

    await DatabaseManager.set_state(_BOOKING_QUEUE_KEY, remaining)


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

        with _call_counter_lock:
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
            business = lead.get("business", "Unknown")
            phone = lead.get("phone", "")
            contact = lead.get("owner", "")
            email = lead.get("email", "")
            lead_id = lead.get("id", 0)

            # ── [PIPELINE] Try email re-engagement BEFORE phone call ──
            if email:
                try:
                    # Load business context for consistent signature
                    import json as _json2
                    _ctx_path2 = os.path.join(os.path.dirname(__file__), "core", "business_context.json")
                    _biz_ctx2 = {}
                    try:
                        with open(_ctx_path2, "r") as _f2:
                            _biz_ctx2 = _json2.load(_f2)
                    except Exception:
                        pass
                    _sig2 = _biz_ctx2.get("email_rules", {}).get("signature", "Nova @ OROVA")

                    re_subject = f"Re: Quick question about {business}"
                    re_body = (
                        f"Hi {contact or 'there'},\n\n"
                        f"Just circling back on my earlier note about {business}. "
                        f"One of our clients in a similar space just had their best month after switching to automated lead qualification — happy to share how it works.\n\n"
                        f"No worries if the timing isn't right.\n\n"
                        f"{_sig2}"
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
                    "UPDATE leads SET status = 'Ready for Call' WHERE id = ? AND client_id = ?",
                    (int(lead_id), int(client_id))
                )
                escalated += 1
                continue

            # Trigger RetellAI call directly
            logger.info(f"📞 [ESCALATION] Triggering cold call for {business} ({phone})...")

            # Approval gate: cold calls need Mark's OK unless CALLS_AUTOPILOT=1.
            from app.core.approval_gate import gate_allows
            if not await gate_allows(
                "call",
                {"lead_id": lead_id, "phone": phone},
                reason=f"Cold call to {business} ({phone})",
            ):
                logger.info(f"📞 [ESCALATION] Call to {phone} awaiting approval; calls once Mark approves")
                continue

            # Reserve call slot atomically before invoking Retell
            with _call_counter_lock:
                if daily_call_counter >= MAX_CALLS_PER_DAY:
                    logger.info(f"📞 [ESCALATION] Daily call cap reached mid-batch. Stopping.")
                    break
                daily_call_counter += 1

            context = {
                "business_name": business,
                "contact_name": contact,
                "owner_name": contact,
                "owner_title": lead.get("owner_title", ""),
                "niche": lead.get("vertical", ""),
                "icebreaker": (lead.get("icebreaker") or "").replace("Pending review...", "")
                    or "we emailed about qualifying leads automatically and wanted to reach out directly",
                "call_type": "cold_escalation",
                # Selects which pain step 2 opens on — payroll pressure for a
                # firm with staff, his own calendar for a one-man operation.
                # Free, from the named principals on the state licence.
                "principal_count": lead.get("principal_count", 0),
                "lead_id": lead_id,
                "client_id": client_id,
            }

            try:
                import inspect
                if inspect.iscoroutinefunction(trigger_retell_call):
                    result = await trigger_retell_call(phone, context)
                else:
                    result = await loop.run_in_executor(None, trigger_retell_call, phone, context)

                if result.get("skipped"):
                    logger.info(f"⏭️ [ESCALATION] Retell not configured — skipping call for {business}. Set RETELL_API_KEY to enable.")
                    with _call_counter_lock:
                        daily_call_counter -= 1  # Release reserved slot
                elif result.get("success"):
                    call_id = result.get("call_id")
                    called += 1
                    logger.info(f"✅ [ESCALATION] Cold call triggered for {business}. Call ID: {call_id}")

                    # Update lead status in SQLite
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Cold Call Initiated' WHERE id = ? AND client_id = ?",
                        (int(lead_id), int(client_id))
                    )

                    await send_telegram_report(
                        f"📞 **Cold Lead Auto-Call** [Client {client_id}]\n\n"
                        f"**{business}** ({contact}) — no reply for {COLD_LEAD_DAYS_THRESHOLD}+ days.\n"
                        f"Phone: `{phone}`\n"
                        f"Call ID: `{call_id}`"
                    )
                else:
                    error = result.get("error", "Unknown")
                    logger.warning(f"⚠️ [ESCALATION] Cold call failed for {business}: {error}")
                    # Mark as "Ready for Call" as fallback
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Ready for Call' WHERE id = ? AND client_id = ?",
                        (int(lead_id), int(client_id))
                    )
            except Exception as call_err:
                logger.error(f"❌ [ESCALATION] Call trigger error for {business}: {call_err}")
                await DatabaseManager.query(
                    "UPDATE leads SET status = 'Ready for Call' WHERE id = ? AND client_id = ?",
                    (int(lead_id), int(client_id))
                )

            escalated += 1

            # Rate limit: wait between calls
            if called < MAX_CALLS_PER_DAY:
                await asyncio.sleep(5)

        logger.info(f"📞 [ESCALATION] [Client {client_id}] Processed {escalated} cold leads, triggered {called} calls.")

        if called > 0:
            await send_telegram_report(
                f"📞 **Cold Lead Escalation Complete** [Client {client_id}]\n\n"
                f"Triggered **{called}** auto-calls for leads that went cold after {COLD_LEAD_DAYS_THRESHOLD} days."
            )

    except Exception as e:
        logger.error(f"Cold Lead Escalation Error (Client {client_id}): {e}")


# ═══════════════════════════════════════════════════════
# LANE 4b: PHONE-FIRST — call leads that were never emailed
# ═══════════════════════════════════════════════════════
async def run_phone_first_lane(client_id=0):
    """Dial never-contacted leads. The channel that actually works.

    Why this lane exists (2026-07-30): Lane 4 above is an ESCALATION lane —
    get_cold_leads requires status IN ('Email Sent','Contacted'), so it only
    ever sees leads that were already emailed. That makes it structurally
    downstream of email. Cold email is deliberately deferred and fails closed
    (ADR-0014: 0 of 8 providers permit cold outreach), so Lane 4's input set is
    permanently EMPTY — and the ~4,280 on-ICP WA licence leads from ADR-0014
    seam 1, which carry a published business phone at 100% fill, could never be
    called by any scheduled lane.

    Every existing guardrail is reused rather than reimplemented:
      · DNC + National DNC Registry — inside trigger_retell_call (TCPA)
      · approval gate — gate_allows("call"), so calls QUEUE for Mark unless
        CALLS_AUTOPILOT=1. This lane does not widen who gets dialled without
        approval; it only widens which leads are eligible to be proposed.
      · MAX_CALLS_PER_DAY — the same daily_call_counter + _call_counter_lock
        Lane 4 uses. Deliberately NOT outreach_orchestrator.make_throttled_call,
        which keeps its own separate _daily_call_count: routing this lane
        through it would let the two counters each spend a full
        MAX_CALLS_PER_DAY, i.e. silently double the cap.
      · callability — outreach_ready() in lead_validator (single source of truth)

    ⚠️ COMPLIANCE — UNRESOLVED. Do NOT set CALLS_AUTOPILOT=1 for WA numbers
    until the question below is answered by a lawyer. An earlier version of this
    docstring claimed "published business lines from a state licence register,
    never personal cells" as if that settled TCPA. **It does not**, on three
    counts found in the 2026-07-30 review:

      1. TCPA §227(b)(1)(A)(iii) covers artificial/prerecorded voice to ANY
         wireless number and has NO B2B exemption (EBR is defined only for
         §(c)). $500/call, $1,500 willful. Licence records routinely list a
         mobile as the business line and do not say which.
      2. RCW 80.36.400 appears to bar "automatic dialing and announcing device"
         commercial solicitation in Washington outright — no B2B exemption, no
         consent cure — and violation is a per-se Consumer Protection Act claim.
      3. is_dnc_registered() FAILS OPEN and is unconfigured in production, so
         there is currently zero National DNC Registry protection. Scrubbing
         would not cure §227(b) anyway — different subsection.

    Also missing for WA: a recorded recording-announcement as the first
    utterance (RCW 9.73.030, two-party consent — Retell records every call) and
    caller identification within 30 seconds (RCW 19.158.040).

    The open question is narrow: is a TWO-WAY conversational agent an "ADAD" /
    "artificial voice message" at all, or do those terms reach only one-way
    prerecorded announcements? That is worth one paid hour of a WA
    consumer-protection lawyer before this lane is enabled.

    This lane is safe to MERGE — it is inert while CALLS_AUTOPILOT=0, and the
    approval gate means calls only queue for Mark.

    Kill switch: PHONE_FIRST_ENABLED=0.
    """
    global daily_call_counter

    if os.getenv("PHONE_FIRST_ENABLED", "1") != "1":
        logger.info("📞 [PHONE-FIRST] Disabled by env flag.")
        return

    logger.info(f"📞 [PHONE-FIRST] [Client {client_id}] Looking for uncontacted callable leads...")
    try:
        loop = asyncio.get_running_loop()

        pst_tz = pytz.timezone('America/Los_Angeles')
        now_pst = datetime.now(pst_tz)
        if now_pst.hour < 9 or now_pst.hour >= 17:
            logger.info(f"⏳ [PHONE-FIRST] Outside prime calling hours "
                        f"({now_pst.strftime('%I:%M %p')} PST). Waiting.")
            return

        with _call_counter_lock:
            if daily_call_counter >= MAX_CALLS_PER_DAY:
                logger.info(f"📞 [PHONE-FIRST] Daily call cap ({MAX_CALLS_PER_DAY}) reached. Skipping.")
                return

        leads = await DatabaseManager.aget_uncontacted_callable_leads(
            limit=PHONE_FIRST_BATCH, client_id=client_id)
        if not leads:
            logger.info(f"📞 [PHONE-FIRST] [Client {client_id}] No uncontacted callable leads.")
            return

        from app.skills.lead_validator import outreach_ready
        from app.core.approval_gate import gate_allows
        from app.core.call_consent import ai_call_allowed

        called = 0
        skipped_not_callable = 0
        skipped_no_consent = 0

        for lead in leads:
            lead_id = lead.get("id")
            business = lead.get("business", "Unknown")
            phone = lead.get("phone", "")
            contact = lead.get("owner", "")

            # outreach_ready owns callability — it requires a decision-maker
            # NAME alongside the number, so Retell can ask for the person
            # rather than cold-opening on whoever answers.
            readiness = outreach_ready(lead)
            if not readiness.get("callable"):
                skipped_not_callable += 1
                logger.debug(f"📞 [PHONE-FIRST] Skipping {business} — not callable: "
                             f"{readiness.get('blockers')}")
                continue

            # ── TCPA: prior express consent, fail-closed ─────────────────────
            # The DNC gate answers "did they ask us to stop?". For an ARTIFICIAL
            # voice that is the wrong question — FCC 24-17 (Feb 2024) holds that
            # AI-generated voices are "artificial" under the TCPA, so a
            # prerecorded/AI call needs PRIOR EXPRESS CONSENT regardless of the
            # B2B exemption. Damages are $500/call, trebled to $1,500 for a
            # wilful violation, PER CALL.
            #
            # And we cannot fall back on "it's a business landline": of the 23
            # numbers queued in production on 2026-08-06, 20 classified as
            # FIXED_OR_MOBILE — US portability makes landline vs cell
            # undeterminable from the number alone.
            #
            # So an AI call is placed only against a recorded consent event.
            # Mark's manual IG DM reply is the canonical one for this funnel.
            allowed, why = await ai_call_allowed(phone)
            if not allowed:
                skipped_no_consent += 1
                logger.info(f"📞 [PHONE-FIRST] NOT calling {business} — {why}.")
                continue

            if not await gate_allows(
                "call",
                {"lead_id": lead_id, "phone": phone},
                reason=f"Consented call to {business} ({contact}) — {phone} [{why}]",
            ):
                logger.info(f"📞 [PHONE-FIRST] Call to {business} awaiting approval.")
                continue

            with _call_counter_lock:
                if daily_call_counter >= MAX_CALLS_PER_DAY:
                    logger.info("📞 [PHONE-FIRST] Daily cap reached mid-batch. Stopping.")
                    break
                daily_call_counter += 1

            context = {
                "business_name": business,
                "contact_name": contact,
                "owner_name": contact,
                "owner_title": lead.get("owner_title", ""),
                "niche": lead.get("vertical", ""),
                # No prior contact, so the escalation lane's "we emailed you"
                # framing would be a lie. Say nothing about a prior touch and
                # let the Retell prompt open cold.
                "icebreaker": (lead.get("icebreaker") or "").replace("Pending review...", "").strip(),
                "call_type": "phone_first",
                "lead_id": lead_id,
                "client_id": client_id,
            }

            try:
                import inspect
                if inspect.iscoroutinefunction(trigger_retell_call):
                    result = await trigger_retell_call(phone, context)
                else:
                    result = await loop.run_in_executor(None, trigger_retell_call, phone, context)

                if result.get("skipped"):
                    # Retell unconfigured, or DNC/suppression blocked the number.
                    logger.info(f"⏭️ [PHONE-FIRST] Call skipped for {business}: "
                                f"{result.get('error', 'not configured')}")
                    with _call_counter_lock:
                        daily_call_counter -= 1      # release the reserved slot
                    continue

                if result.get("success"):
                    called += 1
                    call_id = result.get("call_id")
                    logger.info(f"✅ [PHONE-FIRST] Called {business}. Call ID: {call_id}")
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Cold Call Initiated', "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND client_id = ?",
                        (int(lead_id), int(client_id))
                    )
                    await send_telegram_report(
                        f"📞 **First-Touch Call** [Client {client_id}]\n\n"
                        f"**{business}** ({contact or 'no name'})\n"
                        f"Phone: `{phone}`\n"
                        f"Call ID: `{call_id}`"
                    )
                else:
                    logger.warning(f"⚠️ [PHONE-FIRST] Call failed for {business}: "
                                   f"{result.get('error', 'Unknown')}")
                    with _call_counter_lock:
                        daily_call_counter -= 1
                    await DatabaseManager.query(
                        "UPDATE leads SET status = 'Ready for Call', "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND client_id = ?",
                        (int(lead_id), int(client_id))
                    )
            except Exception as call_err:
                logger.error(f"❌ [PHONE-FIRST] Call error for {business}: {call_err}")
                with _call_counter_lock:
                    daily_call_counter -= 1

            if called:
                await asyncio.sleep(5)      # spacing between dials

        logger.info(f"📞 [PHONE-FIRST] [Client {client_id}] {called} call(s) placed; "
                    f"{skipped_not_callable} lead(s) not callable; "
                    f"{skipped_no_consent} lead(s) without prior express consent.")

    except Exception as e:
        logger.error(f"Phone-First Lane Error (Client {client_id}): {e}")


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
        # Sequential (not gather) so per-client enqueues to the shared booking
        # queue can't race. Reply monitoring is light and runs every 5 min.
        for c in client_list:
            try:
                await run_reply_monitor(client_id=c.get("id", 0))
            except Exception as e:
                logger.error(f"[REPLY MONITOR] Client {c.get('id', 0)} failed: {e}")
    _run_async(run_all())

def cold_escalation_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_cold_lead_escalation(client_id=c.get("id", 0)) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def phone_first_job():
    clients = DatabaseManager.get_clients()
    client_list = [{"id": 0}] + (clients if clients else [])
    async def run_all():
        tasks = [run_phone_first_lane(client_id=c.get("id", 0)) for c in client_list]
        await asyncio.gather(*tasks, return_exceptions=True)
    _run_async(run_all())

def cloud_backup_job():
    logger.info("☁️ [LANE 5] Triggering Google Drive Database Backup...")
    try:
        # Use vault_skill.backup_database — the working OAuth-capable Drive path
        # (the old drive_backup.upload_database was service-account-only and
        # can't upload to consumer Drive). _run_async bridges this sync
        # schedule-thread job to the async backup.
        from app.skills.vault_skill import backup_database
        _run_async(backup_database())
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
    _run_async(ImprovementLoop().run())
    # Also run the two learning loops that existed but were never scheduled:
    # SelfLearningLoop crystallizes repeated tool-sequences into reusable skills;
    # PatternReinforcer decays stale patterns and reinforces winners. Best-effort —
    # a failure in one must not stop the lane.
    try:
        from app.core.self_learning import SelfLearningLoop
        _run_async(SelfLearningLoop().run_cycle())
    except Exception as e:
        logger.error(f"[LANE 8] SelfLearningLoop failed: {e}")
    try:
        from app.core.pattern_reinforcer import PatternReinforcer
        _run_async(PatternReinforcer().run_cycle())
    except Exception as e:
        logger.error(f"[LANE 8] PatternReinforcer failed: {e}")
    # ADR-0004 Phase 2: skill-version champion/challenger evaluation. A clean
    # no-op until a challenger version is registered via the forge flow.
    try:
        from app.core.self_improvement import SkillChallengerEvaluator
        _run_async(SkillChallengerEvaluator.run_cycle())
    except Exception as e:
        logger.error(f"[LANE 8] SkillChallengerEvaluator failed: {e}")

def sequence_drip_job():
    logger.info("[LANE 9] Triggering Drip Sequence Sender...")
    from app.skills.email_sequence_skill import send_pending_drip_emails
    _run_async(send_pending_drip_emails())

def reply_and_drip_check_job():
    logger.info("[REPLY & DRIP CHECK] Checking replies and processing drips...")
    reply_monitor_job()
    # Drain the HOT-reply booking queue (send booking links for approved replies).
    _run_async(process_pending_booking_replies())
    from app.skills.email_sequence_skill import check_drip_replies_and_process
    _run_async(check_drip_replies_and_process())


# ═══════════════════════════════════════════════════════
# THE SCHEDULE — 9 Autonomous Lanes
# ═══════════════════════════════════════════════════════
def _safe_job(job_fn):
    """Run a lane job, containing any exception.

    The schedule library advances a job's next_run only AFTER the job function
    returns — a raising job stays perpetually due, re-fires on every 1-second
    tick, and its exception aborts that run_pending() pass so later-due lanes
    (including the backup lane) never run. Observed live 2026-07-19: Lane 7
    looping at 1 Hz on a schema error, starving all other lanes. Containing
    the exception here keeps the lane on its normal cadence instead.
    """
    try:
        job_fn()
    except Exception as e:
        logger.error(f"[SCHED] {job_fn.__name__} failed (contained; lane stays on cadence): {e}")


schedule.every(APPROVAL_CHECK_MINUTES).minutes.do(_safe_job, fast_lane_job)      # Lane 1: Approvals + calls
schedule.every(HUNT_INTERVAL_MINUTES).minutes.do(_safe_job, slow_lane_job)        # Lane 2: Lead hunting
schedule.every(REPLY_CHECK_MINUTES).minutes.do(_safe_job, reply_and_drip_check_job) # Lane 3: Reply + Drip monitoring
schedule.every(COLD_CALL_CHECK_MINUTES).minutes.do(_safe_job, cold_escalation_job)  # Lane 4: Cold lead → call
schedule.every(PHONE_FIRST_CHECK_MINUTES).minutes.do(_safe_job, phone_first_job)   # Lane 4b: Never-contacted → call (phone-first; Lane 4 only sees already-emailed leads)
schedule.every(3).hours.do(_safe_job, cloud_backup_job)                           # Lane 5: Google Drive Backup (3h: caps learning-data loss on Render restarts)
schedule.every().day.at("17:00").do(_safe_job, ceo_brain_job)                     # Lane 6: CEO Morning Brief (17:00 UTC = ~9-10 AM Pacific)
schedule.every(2).hours.do(_safe_job, health_check_job)                           # Lane 7: Pipeline Health Check
schedule.every(6).hours.do(_safe_job, self_improvement_job)                       # Lane 8: Strategy Self-Improvement
schedule.every(1).hours.do(_safe_job, sequence_drip_job)                          # Lane 9: Drip Sequence Sender


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
