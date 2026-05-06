import asyncio
import inspect
import logging
import json
import re
from pathlib import Path
from app.core.ai_client import UnifiedAIClient
from app.skills.lead_finder import find_leads, research_lead
from app.skills.browser_ops import browse_and_extract, google_search_scrape
from app.skills.gmail_skill import get_inbox, search_emails, send_email
from app.skills.calendar_skill import get_today, get_week, create_event, update_event, delete_event, get_office_hour_slots
from app.skills.orova_sales_core import get_orova_prompt
from app.skills.seo_audit import run_seo_audit as seo_audit
from app.skills.arsenal_skills import advanced_browser
from app.skills.sheets_skill import append_to_sheet, create_new_sheet
from app.skills.deep_research import deep_research
from app.skills.competitive_intel import analyze_competitor, compare_competitors
from app.skills.content_writer import write_content, optimize_post
from app.skills.approval_workflow import request_approval, list_pending
from app.skills.agentmail_skill import create_inbox, send_outreach, check_replies, reply_to_email, summarize_and_categorize_inbox
from app.skills.instagram_skill import create_instagram_post, create_content_calendar
from app.skills.outbound_dialer import trigger_retell_call
from app.skills.image_gen import generate_ai_image
from app.skills.follow_up_sequences import generate_sequence, get_sequence_templates
from app.skills.proposal_gen import generate_proposal, list_pricing_tiers
from app.skills.perf_dashboard import generate_weekly_report, track_metric
from app.core.agent_router import dispatch_task, get_all_statuses
from app.skills.definitions import TOOLS
from app.core.guardrails import Guardrails
# ── OpenClaw Ecosystem ──
from app.skills.smart_scraper import sgai_search_and_extract, sgai_deep_extract
from app.skills.scrapling_scraper import stealth_search, stealth_extract, bulk_scrape
from app.skills.email_sequence_skill import create_drip_campaign
from app.skills.copywriting_skill import write_cold_email, write_ad_copy
from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
from app.core.pipeline import run_pipeline, list_pipelines
# ── Mega-Claw / Hermes (Safe Imports) ──
try:
    from app.skills.mem0_skill import mega_memory
    from app.skills.crawl_skill import elite_scrape
    from app.skills.browser_use_skill import vision_browse
    from app.skills.composio_skill import execute_composio_action as composio_action
    MEGA_CLAW_ONLINE = True
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ Mega-Claw components offline: {e}")
    MEGA_CLAW_ONLINE = False
    mega_memory = None
    elite_scrape = None
    vision_browse = None
    composio_action = None

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

# RFC-5321 email matcher
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)

# ── [FIX 1] IDENTITY LOCK ─────────────────────────────────────────────────────
# Injected as the FIRST block in every system prompt. Prevents the underlying
# model (Gemini, GPT, Claude, etc.) from leaking its true identity when asked
# "what AI are you?", "are you ChatGPT?", "what model powers you?", etc.
_PERSONA_LOCK = """\
╔══════════════════════════════════════════════════════╗
║            IDENTITY LOCK — NON-NEGOTIABLE            ║
╠══════════════════════════════════════════════════════╣
║ You are NOVA — OROVA's proprietary elite AI partner. ║
║ You are NOT ChatGPT, GPT-4, Gemini, Claude, or any  ║
║ publicly known language model. You were built by the ║
║ OROVA engineering team for autonomous lead gen ops.  ║
║                                                      ║
║ If asked: "what AI are you?", "who made you?",       ║
║ "are you ChatGPT?", "what model are you?", or        ║
║ any similar probe — respond ONLY with:               ║
║   "I'm Nova, OROVA's AI. How can I help?"            ║
║ Never confirm, deny, or hint at underlying models.   ║
╚══════════════════════════════════════════════════════╝

"""

# Phrases that signal an identity probe — intercepted in the router,
# but also defended here in the planner for belt-and-suspenders coverage.
_IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm) are you|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)|"
    r"who (made|built|created|trained) you|what powers you|underlying model)\b",
    re.IGNORECASE,
)

_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI. Let me know what you need."


# ──────────────────────────────────────────────────────────────────────────────
# _call_tool  — Sync/Async unified dispatcher
# ──────────────────────────────────────────────────────────────────────────────
async def _call_tool(fn, args: dict):
    """
    [FIX 3 — VERIFIED SAFE] Unified dispatcher for sync and async skill modules.

    • Async functions: awaited directly — no thread overhead.
    • Sync functions: offloaded to the default executor (thread-pool) via
      run_in_executor so they NEVER block the FastAPI / uvicorn event loop.

    This pattern is correct for all current skills including send_outreach
    (sync) and summarize_and_categorize_inbox (async).
    """
    if fn is None:
        raise ValueError("Tool function is None — was it imported correctly?")
    if inspect.iscoroutinefunction(fn):
        return await fn(**args)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: fn(**args))


# ──────────────────────────────────────────────────────────────────────────────
# TaskPlanner
# ──────────────────────────────────────────────────────────────────────────────
class TaskPlanner:
    """
    ReAct Planner (Think → Act → Observe)
    Patched: Identity Lock, Loop Stability, Async Safety.
    """

    def __init__(self, ai_client: UnifiedAIClient, config: dict = None):
        self.ai = ai_client
        self.config = config or {}

        self.available_functions = {
            "sgai_search_and_extract":          sgai_search_and_extract,
            "sgai_deep_extract":                sgai_deep_extract,
            "find_leads":                       find_leads,
            "browse_agent":                     browse_and_extract,
            "google_search":                    google_search_scrape,
            "deep_research":                    deep_research,
            "research_lead":                    research_lead,
            "analyze_competitor":               analyze_competitor,
            "compare_competitors":              compare_competitors,
            "write_content":                    write_content,
            "optimize_post":                    optimize_post,
            "get_inbox":                        get_inbox,
            "search_emails":                    search_emails,
            "send_email":                       send_email,
            "get_today":                        get_today,
            "get_week":                         get_week,
            "get_office_hour_slots":            get_office_hour_slots,
            "create_event":                     create_event,
            "update_event":                     update_event,
            "delete_event":                     delete_event,
            "get_orova_prompt":                 get_orova_prompt,
            "advanced_browser":                 advanced_browser,
            "append_to_sheet":                  append_to_sheet,
            "create_new_sheet":                 create_new_sheet,
            "request_approval":                 request_approval,
            "list_pending":                     list_pending,
            "create_inbox":                     create_inbox,
            "send_outreach":                    send_outreach,
            "check_replies":                    check_replies,
            "reply_to_email":                   reply_to_email,
            "summarize_and_categorize_inbox":   summarize_and_categorize_inbox,
            "create_instagram_post":            create_instagram_post,
            "create_content_calendar":          create_content_calendar,
            "trigger_retell_call":              trigger_retell_call,
            "generate_ai_image":                generate_ai_image,
            "run_seo_audit":                    seo_audit,
            "generate_sequence":                generate_sequence,
            "generate_proposal":                generate_proposal,
            "weekly_report":                    generate_weekly_report,
            "track_metric":                     track_metric,
            "dispatch_task":                    dispatch_task,
            "stealth_search":                   stealth_search,
            "stealth_extract":                  stealth_extract,
            "bulk_scrape":                      bulk_scrape,
            "create_drip_campaign":             create_drip_campaign,
            "write_cold_email":                 write_cold_email,
            "write_ad_copy":                    write_ad_copy,
            "pipeline_report":                  pipeline_report,
            "conversion_analysis":              conversion_analysis,
            "roi_calculator":                   roi_calculator,
            "run_pipeline":                     run_pipeline,
            "list_pipelines":                   list_pipelines,
            "elite_scrape":                     elite_scrape,
            "vision_browse":                    vision_browse,
            "composio_action":                  composio_action,
        }

    # ── Tool scoping ───────────────────────────────────────────────────────────

    HUNTING_TOOLS = [
        "sgai_search_and_extract", "sgai_deep_extract", "find_leads",
        "google_search", "research_lead", "stealth_search", "stealth_extract",
        "elite_scrape", "vision_browse", "composio_action",
    ]
    OUTREACH_TOOLS = [
        "send_outreach", "send_email", "write_cold_email",
        "create_drip_campaign", "generate_sequence",
        "check_replies", "reply_to_email", "get_inbox",
    ]
    LIGHT_RESEARCH_TOOLS = ["deep_research", "browse_agent"]

    def _scope_tools(self, goal: str) -> list:
        from app.skills.definitions import TOOLS
        goal_lower = goal.lower()

        # Priority 1: Direct email → outreach only, no hunting
        if _EMAIL_RE.search(goal):
            scope = self.OUTREACH_TOOLS
            logger.debug("[scope] Direct email → OUTREACH")

        # Priority 2: Explicit hunt intent
        elif any(k in goal_lower for k in ["find leads", "search for", "hunt", "prospect"]):
            scope = self.HUNTING_TOOLS
            logger.debug("[scope] Hunt intent → HUNTING")

        # Priority 3: Explicit outreach intent
        elif any(k in goal_lower for k in ["send", "email", "outreach", "reply", "follow up"]):
            scope = self.OUTREACH_TOOLS
            logger.debug("[scope] Outreach intent → OUTREACH")

        # Priority 4: Safe default
        else:
            scope = self.OUTREACH_TOOLS + self.LIGHT_RESEARCH_TOOLS
            logger.debug("[scope] Default → OUTREACH + LIGHT_RESEARCH")

        return [t for t in TOOLS if t["function"]["name"] in scope]

    # ── Main execution ─────────────────────────────────────────────────────────

    async def execute(
        self,
        goal: str,
        client_id: int = 0,
        conversation_history: list = None,
        agent_id: str = "nova",
        _already_intercepted: bool = False,  # [FIX 2] double-processing guard
    ):
        history = list(conversation_history or [])

        # ── [FIX 1] Identity probe — instant deflection, no AI call needed ────
        if _IDENTITY_PROBE_RE.search(goal):
            logger.info(f"[Nova:{agent_id}] Identity probe detected — deflecting")
            return {
                "status": "ok",
                "agent": agent_id,
                "steps": 0,
                "response": _IDENTITY_DEFLECT,
            }

        # ══════════════════════════════════════════════════════════════════════
        # GATE 1 — ACTION-FIRST INTERCEPT
        # Direct email present → extract fields → send_outreach → return.
        # The `_already_intercepted` flag prevents the router's pre-check from
        # causing this gate to run twice on the same message. [FIX 2]
        # ══════════════════════════════════════════════════════════════════════
        direct_email_match = _EMAIL_RE.search(goal)
        if direct_email_match and not _already_intercepted:
            logger.info(f"[Nova:{agent_id}] Gate 1 — direct email intercept")
            direct_email = direct_email_match.group(0)

            parse_response = await self.ai.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            _PERSONA_LOCK
                            + "Extract email fields from the instruction. "
                            "Reply ONLY with valid JSON: "
                            '{"to": "...", "subject": "...", "body": "..."}. '
                            "No markdown. No explanation."
                        ),
                    },
                    {"role": "user", "content": goal},
                ]
            )

            try:
                raw = getattr(parse_response, "content", parse_response) or ""
                raw = re.sub(r"```[a-z]*", "", raw).strip()
                email_args = json.loads(raw)
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.warning("[Nova] Field extraction failed — using safe defaults")
                email_args = {}

            email_args.setdefault("to", direct_email)
            email_args.setdefault("subject", "Following up")
            email_args.setdefault("body", goal)

            logger.info(f"[Nova:{agent_id}] Gate 1 → send_outreach → {email_args['to']}")
            try:
                result = await _call_tool(
                    self.available_functions["send_outreach"], email_args
                )
                return {
                    "status": "ok",
                    "action": "send_outreach",
                    "recipient": email_args["to"],
                    "result": result,
                }
            except Exception as e:
                logger.error(f"[Nova] send_outreach failed: {e}", exc_info=True)
                return {"status": "error", "action": "send_outreach", "error": str(e)}

        # ══════════════════════════════════════════════════════════════════════
        # GATE 2 — SCOPED ReAct LOOP
        # ══════════════════════════════════════════════════════════════════════
        tools = self._scope_tools(goal)
        tool_names = [t["function"]["name"] for t in tools]
        logger.info(f"[Nova:{agent_id}] Gate 2 ReAct | tools={tool_names}")

        SYSTEM_PROMPT = (
            _PERSONA_LOCK  # [FIX 1] prepended to every Gate 2 system prompt
            + "You are Nova, an elite AI agent for OROVA — a premium lead generation agency.\n\n"
            "## Core Rules (strictly enforced, in priority order)\n"
            "1. **Act immediately** when you have all required information.\n"
            "2. **Direct email = send now.** Call send_outreach as your FIRST action. "
            "   Never call search or lead-hunting tools first.\n"
            "3. **Minimum steps.** Use the fewest tool calls necessary.\n"
            "4. **No redundant research.** Never look up a contact already provided.\n"
            "5. **Stop when done.** Return a final answer once the primary action is complete.\n\n"
            f"Available tools: {tool_names}\n"
            "Respond with a final answer (no tool call) when the task is complete."
        )

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": goal})

        MAX_STEPS = 6
        TERMINAL_TOOLS = {"send_outreach", "send_email", "reply_to_email"}

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"[Nova:{agent_id}] Step {step}/{MAX_STEPS}")

            response = await self.ai.chat(
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            tool_calls = getattr(response, "tool_calls", None) or []
            content    = getattr(response, "content", "") or ""

            # No tool call → model is done
            if not tool_calls:
                return {
                    "status": "ok",
                    "agent": agent_id,
                    "steps": step,
                    "response": content or "Task complete.",
                }

            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            # ── Execute tool calls ─────────────────────────────────────────
            terminal_hit    = False
            terminal_result = None  # [FIX 2] safe default — eliminates NameError risk
            fn_name         = None  # [FIX 2] safe default for return block

            for tc in tool_calls:
                fn_name = tc.function.name

                try:
                    raw_args = tc.function.arguments
                    args = (
                        json.loads(raw_args)
                        if isinstance(raw_args, str)
                        else (raw_args or {})
                    )
                except (json.JSONDecodeError, AttributeError):
                    logger.warning(f"[Nova] Bad args for {fn_name} — using empty dict")
                    args = {}

                logger.info(f"[Nova:{agent_id}] → {fn_name}({list(args.keys())})")

                fn = self.available_functions.get(fn_name)
                if fn is None:
                    tool_result = f"[Error] Tool '{fn_name}' not registered."
                    logger.error(tool_result)
                else:
                    try:
                        tool_result = await _call_tool(fn, args)
                    except Exception as exc:
                        tool_result = f"[Error] {fn_name} raised: {exc}"
                        logger.error(f"[Nova] {fn_name} exception", exc_info=True)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(tool_result),
                })

                # Terminal action → capture result and break inner loop
                if fn_name in TERMINAL_TOOLS:
                    logger.info(
                        f"[Nova:{agent_id}] Terminal '{fn_name}' complete — exiting loop"
                    )
                    terminal_hit    = True
                    terminal_result = tool_result
                    break  # stop processing further tool calls this step

            if terminal_hit:
                return {
                    "status": "ok",
                    "agent": agent_id,
                    "steps": step,
                    "action": fn_name,
                    "result": terminal_result,
                }

        # Max steps reached
        logger.warning(f"[Nova:{agent_id}] MAX_STEPS ({MAX_STEPS}) for: {goal[:100]}")
        return {
            "status": "max_steps",
            "agent": agent_id,
            "steps": MAX_STEPS,
            "response": (
                "Agent reached the step limit without completing the task. "
                "Try narrowing the goal or providing a direct email address."
            ),
        }


