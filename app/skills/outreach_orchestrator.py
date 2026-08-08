"""
Outreach Orchestrator — State Machine for Lead Pipeline
=========================================================
Ties together: Google Sheets → Email Sending → Follow-ups → Call Dialing
with proper rate limiting, retry logic, and state tracking.

Fixes:
1. Sheet write queue with retry (buffers writes, retries on failure)
2. Email send throttle (1 email per 30s, daily cap per client)
3. Call outcome tracking (answered/voicemail/failed)
4. Follow-up state machine (email1 → email2 → email3 → call)
5. Business hours enforcement (7:30-11:30 AM, 6:00-8:00 PM PT)
"""

import asyncio
import logging
import time
import os
from datetime import datetime, date, timezone
from typing import Dict, List, Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Rate Limits ────────────────────────────────────────────────────
EMAIL_DELAY_SECONDS = 30  # Minimum gap between emails
CALL_DELAY_SECONDS = 60   # Minimum gap between calls
MAX_EMAILS_PER_DAY = 50   # Safe daily email cap
MAX_CALLS_PER_DAY = 20    # Safe daily call cap
MAX_RETRIES = 3
BUSINESS_HOURS_RANGES = [
    (7, 30, 11, 30),   # 7:30 AM - 11:30 AM PT
    (18, 0, 20, 0),    # 6:00 PM - 8:00 PM PT
]

# ── Follow-up States (state machine) ───────────────────────────────
FOLLOW_UP_STAGES = [
    {"stage": "email_1", "label": "First Email", "delay_hours": 0},
    {"stage": "email_2", "label": "Follow-up 1", "delay_hours": 48},   # 2 days
    {"stage": "email_3", "label": "Follow-up 2", "delay_hours": 120},  # 5 days
    {"stage": "call_1",  "label": "Phone Call",  "delay_hours": 168},  # 7 days
]

# ── A/B Subject Line Templates ─────────────────────────────────────
AB_SUBJECT_TEMPLATES = [
    "{business_name} — quick question about your online presence",
    "{business_name} — I noticed something about your website",
    "{business_name} — {icebreaker}",
    "Quick question for {owner_name} at {business_name}",
    "{business_name} — SEO opportunity I spotted",
]


async def compose_premium_outreach(lead: Dict[str, Any], niche: str = "", client_id: int = 0) -> Dict[str, str]:
    """Compose a personalized, world-class cold email for a lead.

    - Framework is picked by the champion/challenger loop (select_strategy),
      so every send feeds real A/B data back into learned_strategies.
    - Personalization uses everything enrichment found: owner name, title,
      business, niche, website, LinkedIn, and any icebreaker research.
    - Returns {subject, body, framework}. Falls back to a clean template if
      the AI is unavailable — never blocks the pipeline.
    """
    owner = (lead.get("owner") or lead.get("owner_name") or "").strip()
    first_name = owner.split()[0] if owner else "there"
    business = lead.get("business", "your business")
    title = lead.get("owner_title", "")
    website = lead.get("website") or lead.get("url") or ""
    icebreaker = lead.get("icebreaker", "")
    if icebreaker.lower().startswith("pending"):
        icebreaker = ""

    framework = "pas"
    try:
        from app.core.self_improvement import OutcomeTracker
        pick = await OutcomeTracker.select_strategy("email_framework", client_id=client_id)
        if pick.get("strategy_value"):
            framework = pick["strategy_value"]
    except Exception as e:
        logger.debug(f"[OUTREACH] Strategy selection fallback to pas: {e}")

    framework_notes = {
        "pas": "Problem-Agitate-Solve: name the specific pain, twist it, then present the fix.",
        "bab": "Before-After-Bridge: paint their current state, the ideal state, and OROVA as the bridge.",
        "aida": "Attention-Interest-Desire-Action: hook hard in line one, build want, single CTA.",
        "story_brand": "StoryBrand: they are the hero, OROVA is the guide with a plan.",
        "4ps": "Promise-Picture-Proof-Push: bold promise, vivid picture, credibility, clear ask.",
    }

    prompt = f"""You are the best cold-email writer alive, writing for OROVA — a marketing agency that runs Meta ads (Facebook + Instagram) for luxury and premium West Coast businesses: we generate the leads with AI-crafted ad creatives, and our AI qualifies every lead and books the serious ones onto the owner's calendar.

Write ONE cold email to this exact person:
- Name: {owner or 'Unknown (address as "there", never "Sir/Madam")'}
- Title: {title or 'Owner (assumed)'}
- Business: {business}
- Industry: {niche or 'local business'}
- Website: {website or 'n/a'}
- Research note: {icebreaker or 'none — open with a sharp industry-specific observation instead'}

Framework: {framework.upper()} — {framework_notes.get(framework, 'direct and concise')}

HARD RULES:
- Under 90 words. Sounds like a sharp human peer, not marketing.
- Line 1 must be specific to THEM (their business/industry/research note) — never "I hope this finds you well" or "My name is".
- No buzzwords (synergy, revolutionize, leverage, cutting-edge, streamline).
- Exactly one CTA: a low-friction question about a 10-minute call.
- No placeholder brackets. No links. Sign off as "Nova @ OROVA".
- Write at a 6th-grade reading level. Short sentences.

Return ONLY JSON: {{"subject": "...", "body": "..."}}
Subject: under 6 words, lowercase-casual, curiosity-driven, no clickbait."""

    try:
        from app.core.ai_client import UnifiedAIClient
        import json as _json
        import re as _re
        ai = UnifiedAIClient()
        raw = await ai.write(prompt)
        match = _re.search(r'\{.*\}', raw or "", _re.DOTALL)
        if match:
            data = _json.loads(match.group(0))
            subject = (data.get("subject") or "").strip()
            body = (data.get("body") or "").strip()
            if subject and body and "{" not in body:
                return {"subject": subject[:78], "body": body, "framework": framework}
    except Exception as e:
        logger.warning(f"[OUTREACH] Premium composer failed, using fallback: {e}")

    # Fallback: still personalized, never generic filler
    subject = generate_ab_subject(business, owner, icebreaker)
    market = niche or "your market"
    if icebreaker:
        opener = icebreaker[0].upper() + icebreaker[1:]
        if opener[-1] not in ".!?":
            opener += " — impressive."
    else:
        opener = f"Noticed {business} while researching {market} — impressive operation."
    body = (
        f"Hi {first_name},\n\n"
        f"{opener}\n\n"
        f"We run Meta ads for premium businesses like {business} — our AI makes the creatives, "
        f"generates the leads, and qualifies every one so you only talk to people ready to buy.\n\n"
        f"Worth a 10-minute call to see if it fits?\n\n"
        f"Nova @ OROVA"
    )
    return {"subject": subject, "body": body, "framework": framework}


def generate_ab_subject(business_name: str, owner_name: str = "", icebreaker: str = "") -> str:
    """
    Generate a randomized A/B subject line.
    Uses hash of business_name + lead_id for deterministic rotation.
    """
    import random
    template = random.choice(AB_SUBJECT_TEMPLATES)
    return template.format(
        business_name=business_name,
        owner_name=owner_name or "the team",
        icebreaker=icebreaker or "quick question",
    )


async def get_best_send_timing() -> int:
    """
    Fetch the learned best_send_hour from learned_strategies table.
    Returns an hour (0-23) or 9 if no data.
    """
    try:
        from app.core.database import DatabaseManager
        row = await DatabaseManager.fetchone(
            "SELECT strategy_value FROM learned_strategies WHERE strategy_type = 'send_timing' AND active = 1 ORDER BY wilson_score DESC, win_rate DESC LIMIT 1"
        )
        if row and row.get("strategy_value"):
            hour = int(row["strategy_value"])
            if 0 <= hour <= 23:
                return hour
    except Exception as e:
        logger.warning(f"[TIMING] Could not fetch best_start timing: {e}")
    return 9  # Default 9 AM PT


def is_target_send_hour(target_hour: int = 9) -> bool:
    """
    Check if the current hour (PT) matches the target send hour.
    Allows a 2-hour window around the target.
    """
    try:
        import pytz
        pt_tz = pytz.timezone("America/Los_Angeles")
        now = datetime.now(pt_tz)
        current_hour = now.hour
        return (current_hour >= target_hour - 1 and current_hour <= target_hour + 1)
    except Exception:
        return True  # If timezone fails, allow send


def is_business_hours() -> bool:
    """Check if current time is within business hours (PT)."""
    # Get current time in PT (UTC-7 for PDT / UTC-8 for PST)
    import pytz
    pt_tz = pytz.timezone("America/Los_Angeles")
    now = datetime.now(pt_tz)
    current_minutes = now.hour * 60 + now.minute
    
    for start_h, start_m, end_h, end_m in BUSINESS_HOURS_RANGES:
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m
        if start <= current_minutes <= end:
            return True
    return False


def get_next_available_slot() -> str:
    """Get the next available business time slot as a string."""
    import pytz
    pt_tz = pytz.timezone("America/Los_Angeles")
    now = datetime.now(pt_tz)
    
    for start_h, start_m, end_h, end_m in BUSINESS_HOURS_RANGES:
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        current_minutes = now.hour * 60 + now.minute
        
        if current_minutes < start_minutes:
            return f"Today {start_h}:{start_m:02d} AM PT"
        elif current_minutes < end_minutes:
            return "Now"
    
    # Past all slots - return next day's morning
    return f"Tomorrow 7:30 AM PT"


# ── Lead Follow-up State Machine ───────────────────────────────────

class FollowUpMachine:
    """
    Tracks where each lead is in the outreach pipeline.
    Uses SQLite-based persistence via DatabaseManager.
    """

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    async def get_lead_state(self, lead_id: int) -> Dict[str, Any]:
        """Get the current follow-up state for a lead."""
        cache_key = f"lead_followup_{lead_id}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]

        from app.core.database import DatabaseManager
        state = await DatabaseManager.get_state(cache_key, default={
            "lead_id": lead_id,
            "current_stage": 0,  # Index into FOLLOW_UP_STAGES
            "last_action_at": None,
            "emails_sent": 0,
            "calls_made": 0,
            "replied": False,
            "opted_out": False,
            "status": "pending",  # pending, active, replied, opted_out, completed
        })
        self._cache[cache_key] = state
        return state

    async def _save_lead_state(self, lead_id: int, state: Dict[str, Any]):
        """Persist lead state to database."""
        from app.core.database import DatabaseManager
        cache_key = f"lead_followup_{lead_id}"
        self._cache[cache_key] = state
        await DatabaseManager.set_state(cache_key, state)

    async def mark_replied(self, lead_id: int):
        """Mark a lead as having replied (stop follow-ups)."""
        state = await self.get_lead_state(lead_id)
        state["replied"] = True
        state["status"] = "replied"
        await self._save_lead_state(lead_id, state)

    async def mark_opted_out(self, lead_id: int):
        """Mark a lead as opted out."""
        state = await self.get_lead_state(lead_id)
        state["opted_out"] = True
        state["status"] = "opted_out"
        await self._save_lead_state(lead_id, state)

    async def next_action(self, lead_id: int) -> Optional[Dict[str, Any]]:
        """
        Determine the next action for a lead based on their current stage.
        Returns None if no action needed, or a dict with:
        - action: "send_email" | "make_call"
        - stage: the follow-up stage info
        - content: suggested content for the action
        """
        state = await self.get_lead_state(lead_id)

        # Check terminal states
        if state["replied"] or state["opted_out"] or state["status"] == "completed":
            return None

        # Check if we've completed all stages
        if state["current_stage"] >= len(FOLLOW_UP_STAGES):
            state["status"] = "completed"
            await self._save_lead_state(lead_id, state)
            return None

        stage = FOLLOW_UP_STAGES[state["current_stage"]]

        # Check delay requirement
        if state["last_action_at"] and stage["delay_hours"] > 0:
            last_time = datetime.fromisoformat(state["last_action_at"])
            hours_since = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600
            if hours_since < stage["delay_hours"]:
                hours_remaining = stage["delay_hours"] - hours_since
                return {
                    "action": "wait",
                    "hours_remaining": round(hours_remaining, 1),
                    "next_slot": get_next_available_slot(),
                }

        # Determine action type
        action = "make_call" if stage["stage"].startswith("call") else "send_email"

        return {
            "action": action,
            "stage": stage,
            "stage_index": state["current_stage"],
            "total_stages": len(FOLLOW_UP_STAGES),
        }

    async def advance_stage(self, lead_id: int, success: bool = True):
        """Advance a lead to the next stage after an action."""
        state = await self.get_lead_state(lead_id)
        if success:
            state["current_stage"] += 1
            state["last_action_at"] = datetime.now(timezone.utc).isoformat()
            if state["current_stage"] >= len(FOLLOW_UP_STAGES):
                state["status"] = "completed"
        await self._save_lead_state(lead_id, state)

    async def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get a summary of the current pipeline state."""
        # Load all leads with follow-up state
        from app.core.database import DatabaseManager
        all_leads = await DatabaseManager.fetchall(
            "SELECT id, business, owner, email, phone, status, score FROM leads ORDER BY id DESC LIMIT 100"
        )
        if not all_leads:
            return {"total": 0}

        pending = 0
        active = 0
        replied = 0
        completed = 0
        need_call = 0

        for lead_row in all_leads:
            lead = dict(lead_row)
            state = await self.get_lead_state(lead["id"])
            if state["replied"]:
                replied += 1
            elif state["status"] == "completed":
                completed += 1
            elif state["current_stage"] > 0:
                active += 1
                # Check if next action is a call
                next_act = await self.next_action(lead["id"])
                if next_act and next_act.get("action") == "make_call":
                    need_call += 1
            else:
                pending += 1

        return {
            "total": len(all_leads),
            "pending_first_email": pending,
            "active_followups": active,
            "replied": replied,
            "completed": completed,
            "pending_calls": need_call,
        }


# ── Sheet Write Queue ──────────────────────────────────────────────

class SheetWriteQueue:
    """
    Buffered sheet writer with retry.
    Prevents losing data when Google Sheets API is slow or down.
    """

    def __init__(self, max_retries: int = MAX_RETRIES, retry_delay: float = 5.0):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._retries = max_retries
        self._retry_delay = retry_delay
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background writer."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker())
        logger.info("[SHEET-Q] Writer started")

    async def stop(self):
        """Stop the background writer."""
        self._running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except: pass

    async def enqueue(self, sheet_name: str, rows: List[List[Any]]):
        """Add a write operation to the queue."""
        await self._queue.put({
            "sheet_name": sheet_name,
            "rows": rows,
            "attempts": 0,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        })

    async def _worker(self):
        """Background worker that processes the queue."""
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                await self._process_item(item)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[SHEET-Q] Worker error: {e}")

    async def _process_item(self, item: Dict):
        """Process a single queue item with retry."""
        from app.skills.sheets_skill import append_to_sheet
        for attempt in range(self._retries + 1):
            try:
                result = await append_to_sheet(item["sheet_name"], item["rows"])
                if result and result.get("status") == "ok":
                    logger.info(f"[SHEET-Q] Wrote {len(item['rows'])} rows to '{item['sheet_name']}'")
                    return
                logger.warning(f"[SHEET-Q] Write attempt {attempt + 1} failed: {result}")
            except Exception as e:
                logger.warning(f"[SHEET-Q] Write attempt {attempt + 1} error: {e}")

            if attempt < self._retries:
                await asyncio.sleep(self._retry_delay * (attempt + 1))

        logger.error(f"[SHEET-Q] Failed to write {len(item['rows'])} rows after {self._retries + 1} attempts")


# ── Throttled Email Sender ─────────────────────────────────────────

_last_email_time = 0.0
_last_call_time = 0.0
_daily_email_count: Dict[str, int] = defaultdict(int)  # client_id -> count
_daily_call_count: Dict[str, int] = defaultdict(int)
_last_reset_date = date.today()


def _check_daily_reset():
    """Reset daily counters if it's a new day."""
    global _last_reset_date
    today = date.today()
    if today != _last_reset_date:
        _daily_email_count.clear()
        _daily_call_count.clear()
        _last_reset_date = today


async def send_throttled_email(
    to: str,
    subject: str,
    body: str,
    client_id: int = 0,
) -> Dict[str, Any]:
    """
    Send an email with rate limiting and daily cap enforcement.
    Returns: {"status": "ok"|"rate_limited"|"error", ...}
    """
    global _last_email_time

    _check_daily_reset()

    # Check daily cap
    if _daily_email_count[client_id] >= MAX_EMAILS_PER_DAY:
        return {"status": "rate_limited", "reason": "Daily email cap reached", "max": MAX_EMAILS_PER_DAY}

    # Check business hours
    if not is_business_hours():
        return {"status": "rate_limited", "reason": "Outside business hours", "next_slot": get_next_available_slot()}

    # Rate limit: ensure minimum gap between emails
    elapsed = time.time() - _last_email_time
    if elapsed < EMAIL_DELAY_SECONDS:
        wait = EMAIL_DELAY_SECONDS - elapsed
        return {"status": "rate_limited", "reason": f"Rate limited, wait {wait:.0f}s", "wait_seconds": wait}

    # Send
    try:
        from app.skills.agentmail_skill import send_outreach
        # `await` was missing. send_outreach is `async def`, so this only built a
        # coroutine and threw it away — the opt-out check, the CAN-SPAM postal
        # check, the ICP gate, the MX check and the approval gate ALL never ran,
        # while the function returned {"status": "ok"} and reported success.
        # Unreachable today (run_lead_pipeline has no callers), which is why the
        # incident-driven audit missed it — but it reads as a finished pipeline,
        # so wiring it up later would have bypassed every gate while claiming to
        # have passed them. Found by the compliance review, not by the tests.
        result = await send_outreach(to=to, subject=subject, body=body)
        _last_email_time = time.time()
        _daily_email_count[client_id] += 1

        # Track in database
        from app.core.database import DatabaseManager
        await DatabaseManager.set_state(f"email_count_{client_id}_{date.today().isoformat()}",
                                        _daily_email_count[client_id])

        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"[THROTTLE] Email send failed: {e}")
        return {"status": "error", "error": str(e)}


async def make_throttled_call(
    phone: str,
    context: Dict[str, str],
    client_id: int = 0,
) -> Dict[str, Any]:
    """
    Make a phone call with rate limiting and daily cap enforcement.
    Returns: {"status": "ok"|"rate_limited"|"error", ...}
    """
    global _last_call_time

    _check_daily_reset()

    if _daily_call_count[client_id] >= MAX_CALLS_PER_DAY:
        return {"status": "rate_limited", "reason": "Daily call cap reached", "max": MAX_CALLS_PER_DAY}

    if not is_business_hours():
        return {"status": "rate_limited", "reason": "Outside business hours", "next_slot": get_next_available_slot()}

    elapsed = time.time() - _last_call_time
    if elapsed < CALL_DELAY_SECONDS:
        wait = CALL_DELAY_SECONDS - elapsed
        return {"status": "rate_limited", "reason": f"Rate limited, wait {wait:.0f}s"}

    try:
        from app.skills.outbound_dialer import trigger_retell_call
        result = await trigger_retell_call(
            phone=phone,
            context=context,
        )
        _last_call_time = time.time()
        _daily_call_count[client_id] += 1

        # Extract outcome
        call_id = result.get("call_id", "")
        success = result.get("success", False)

        from app.core.database import DatabaseManager
        await DatabaseManager.query(
            """INSERT INTO metrics (client_id, metric_key, metric_value) VALUES (?, ?, ?)""",
            (client_id, f"call_{date.today().isoformat()}", 1 if success else 0)
        )

        return {
            "status": "ok" if success else "failed",
            "call_id": call_id,
            "outcome": "answered" if success else "failed",
            "raw": result,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── High-Level Pipeline Orchestrator ───────────────────────────────

async def run_lead_pipeline(
    lead_id: int,
    lead_data: Dict[str, Any],
    sheet_queue: SheetWriteQueue,
) -> Dict[str, Any]:
    """
    Run the outreach pipeline for a single lead.
    Determines the next action, executes it, and advances state.

    Args:
        lead_id: Database lead ID
        lead_data: Lead dict with business, owner, email, phone, etc.
        sheet_queue: Sheet write queue for logging

    Returns:
        Dict with action taken and result
    """
    machine = FollowUpMachine()
    next_act = await machine.next_action(lead_id)

    if not next_act:
        return {"lead_id": lead_id, "action": "none", "reason": "Pipeline complete"}

    if next_act.get("action") == "wait":
        return {
            "lead_id": lead_id,
            "action": "wait",
            "hours_remaining": next_act["hours_remaining"],
            "next_slot": next_act["next_slot"],
        }

    stage = next_act["stage"]
    business_name = lead_data.get("business", lead_data.get("owner", "there"))
    owner_name = lead_data.get("owner", "there")
    icebreaker = lead_data.get("icebreaker", "")

    # A/B subject line rotation — each lead gets a randomized subject
    subject = generate_ab_subject(business_name, owner_name, icebreaker)
    body = f"Hi {owner_name},\n\n{icebreaker or 'This is a follow-up regarding...'}"

    if next_act["action"] == "send_email":
        # Check learned send timing — defer if outside optimal window
        target_hour = await get_best_send_timing()
        if not is_target_send_hour(target_hour):
            logger.info(f"[PIPELINE] Deferring email to {lead_data.get('business')} — optimal hour is {target_hour}:00 PT")
            return {
                "lead_id": lead_id, "action": "deferred",
                "reason": f"Optimal send time is {target_hour}:00 PT",
                "next_slot": f"Today {target_hour}:00 PT",
            }
        result = await send_throttled_email(
            to=lead_data.get("email", ""),
            subject=subject,
            body=body,
            client_id=lead_data.get("client_id", 0),
        )
    else:  # make_call
        result = await make_throttled_call(
            phone=lead_data.get("phone", ""),
            context={
                "business_name": business_name,
                "icebreaker": lead_data.get("icebreaker", ""),
            },
            client_id=lead_data.get("client_id", 0),
        )

    if result.get("status") == "ok":
        await machine.advance_stage(lead_id, success=True)
        # Log to sheet
        await sheet_queue.enqueue("Outreach Log", [[
            lead_id,
            business_name,
            next_act["action"],
            stage["label"],
            datetime.now(timezone.utc).isoformat(),
            "success",
            result.get("call_id", result.get("result", {}).get("message_id", "")),
        ]])
    elif result.get("status") == "rate_limited":
        return {"lead_id": lead_id, "action": "rate_limited", "reason": result.get("reason"), "next_slot": result.get("next_slot")}

    return {"lead_id": lead_id, "action": next_act["action"], "stage": stage["label"], "result": result}


# ── Global Instances ───────────────────────────────────────────────

follow_up_machine = FollowUpMachine()
sheet_write_queue = SheetWriteQueue()