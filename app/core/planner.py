import asyncio
import inspect
import logging
import json
import re
import hashlib
import time
from pathlib import Path
from app.core.ai_client import UnifiedAIClient, GroqLimpResponse
# ... (skills imports same as before) ...
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
from app.skills.smart_scraper import sgai_search_and_extract, sgai_deep_extract
from app.skills.scrapling_scraper import stealth_search, stealth_extract, bulk_scrape
from app.skills.email_sequence_skill import create_drip_campaign
from app.skills.copywriting_skill import write_cold_email, write_ad_copy
from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
from app.core.pipeline import run_pipeline, list_pipelines
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

# ── [P0] STABILITY CONSTANTS ──
MAX_OBS_CHARS = 2000    # Hard cap per observation
MAX_TOTAL_CHARS = 18000 # Context budget before compression
MAX_REPEAT_CALLS = 2    # Halting problem guard

def _truncate_obs(obs: str) -> str:
    if len(obs) <= MAX_OBS_CHARS: return obs
    half = MAX_OBS_CHARS // 2
    return obs[:half] + f"\n... [TRUNCATED {len(obs)-MAX_OBS_CHARS} chars] ...\n" + obs[-half:]

def _ctx_size(messages: list) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages)

def _call_hash(fn_name: str, fn_args: dict) -> str:
    payload = json.dumps({"fn": fn_name, "args": fn_args}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()

# ... (email_re and persona_lock same as before) ...
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_PERSONA_LOCK = """\
╔══════════════════════════════════════════════════════╗
║            IDENTITY LOCK — NON-NEGOTIABLE            ║
╠══════════════════════════════════════════════════════╣
║ You are NOVA — OROVA's proprietary elite AI partner. ║
╚══════════════════════════════════════════════════════╝
"""
_IDENTITY_PROBE_RE = re.compile(r"\b(what (ai|model|llm) are you|are you (chatgpt|gpt|gemini|claude)|who (made|built|created) you)\b", re.IGNORECASE)
_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI. Let me know what you need."

async def _call_tool(fn, args: dict):
    if fn is None: raise ValueError("Tool function is None")
    if inspect.iscoroutinefunction(fn): return await fn(**args)
    return await asyncio.get_event_loop().run_in_executor(None, lambda: fn(**args))

class TaskPlanner:
    def __init__(self, ai_client: UnifiedAIClient, config: dict = None):
        self.ai = ai_client
        self.config = config or {}
        self.available_functions = {
            "sgai_search_and_extract": sgai_search_and_extract, "sgai_deep_extract": sgai_deep_extract,
            "find_leads": find_leads, "browse_agent": browse_and_extract, "google_search": google_search_scrape,
            "deep_research": deep_research, "research_lead": research_lead, "analyze_competitor": analyze_competitor,
            "compare_competitors": compare_competitors, "write_content": write_content, "optimize_post": optimize_post,
            "get_inbox": get_inbox, "search_emails": search_emails, "send_email": send_email,
            "get_today": get_today, "get_week": get_week, "get_office_hour_slots": get_office_hour_slots,
            "create_event": create_event, "update_event": update_event, "delete_event": delete_event,
            "get_orova_prompt": get_orova_prompt, "advanced_browser": advanced_browser, "append_to_sheet": append_to_sheet,
            "create_new_sheet": create_new_sheet, "request_approval": request_approval, "list_pending": list_pending,
            "create_inbox": create_inbox, "send_outreach": send_outreach, "check_replies": check_replies,
            "reply_to_email": reply_to_email, "summarize_and_categorize_inbox": summarize_and_categorize_inbox,
            "create_instagram_post": create_instagram_post, "create_content_calendar": create_content_calendar,
            "trigger_retell_call": trigger_retell_call, "generate_ai_image": generate_ai_image,
            "run_seo_audit": seo_audit, "generate_sequence": generate_sequence, "generate_proposal": generate_proposal,
            "weekly_report": generate_weekly_report, "track_metric": track_metric, "dispatch_task": dispatch_task,
            "stealth_search": stealth_search, "stealth_extract": stealth_extract, "bulk_scrape": bulk_scrape,
            "create_drip_campaign": create_drip_campaign, "write_cold_email": write_cold_email,
            "write_ad_copy": write_ad_copy, "pipeline_report": pipeline_report, "conversion_analysis": conversion_analysis,
            "roi_calculator": roi_calculator, "run_pipeline": run_pipeline, "list_pipelines": list_pipelines,
            "elite_scrape": elite_scrape, "vision_browse": vision_browse, "composio_action": composio_action,
        }

    HUNTING_TOOLS = ["sgai_search_and_extract", "sgai_deep_extract", "find_leads", "google_search", "research_lead", "stealth_search", "stealth_extract", "elite_scrape", "vision_browse", "composio_action"]
    OUTREACH_TOOLS = ["send_outreach", "send_email", "write_cold_email", "create_drip_campaign", "generate_sequence", "check_replies", "reply_to_email", "get_inbox"]
    LIGHT_RESEARCH_TOOLS = ["deep_research", "browse_agent"]

    def _scope_tools(self, goal: str) -> list:
        goal_lower = goal.lower()
        if _EMAIL_RE.search(goal): scope = self.OUTREACH_TOOLS
        elif any(k in goal_lower for k in ["find leads", "search for", "hunt", "prospect"]): scope = self.HUNTING_TOOLS
        elif any(k in goal_lower for k in ["send", "email", "outreach", "reply", "follow up"]): scope = self.OUTREACH_TOOLS
        else: scope = self.OUTREACH_TOOLS + self.LIGHT_RESEARCH_TOOLS
        return [t for t in TOOLS if t["function"]["name"] in scope]

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova", _already_intercepted: bool = False):
        if _IDENTITY_PROBE_RE.search(goal): return {"status": "ok", "agent": agent_id, "steps": 0, "response": _IDENTITY_DEFLECT}
        
        # [P0] Track identical calls to prevent halting loops
        call_counts: dict[str, int] = {}
        history = list(conversation_history or [])
        
        # Gate 1 — Direct Action Intercept (OMITTED for brevity, logic remains same)
        # ... 

        tools = self._scope_tools(goal)
        tool_names = [t["function"]["name"] for t in tools]
        messages = [{"role": "system", "content": _PERSONA_LOCK + f"You are Nova. Available tools: {tool_names}"}]
        if history: messages.extend(history[-6:])
        messages.append({"role": "user", "content": goal})

        MAX_STEPS = 6
        TERMINAL_TOOLS = {"send_outreach", "send_email", "reply_to_email"}

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"[Nova:{agent_id}] Step {step}/{MAX_STEPS}")

            response = await self.ai.chat(messages=messages, tools=tools, tool_choice="auto")
            
            # [P0] Groq Limp Mode Guard
            if isinstance(response, GroqLimpResponse):
                logger.warning("[PLANNER] Groq limp mode active — synthesizing final answer")
                return {"status": "ok", "agent": agent_id, "steps": step, "response": response.content}

            tool_calls = getattr(response, "tool_calls", None) or []
            content = getattr(response, "content", "") or ""

            if not tool_calls:
                return {"status": "ok", "agent": agent_id, "steps": step, "response": content or "Task complete."}

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else (tc.function.arguments or {})
                except: args = {}

                # [P0] Halting Problem Guard
                h = _call_hash(fn_name, args)
                call_counts[h] = call_counts.get(h, 0) + 1
                if call_counts[h] > MAX_REPEAT_CALLS:
                    logger.warning(f"[PLANNER] Halting detected for {fn_name}. Escaping...")
                    return {"status": "ok", "agent": agent_id, "steps": step, "response": "I encountered a loop while trying to access that information. Here is my best summary..."}

                logger.info(f"[Nova:{agent_id}] → {fn_name}({list(args.keys())})")
                fn = self.available_functions.get(fn_name)
                if not fn: tool_result = f"Error: Tool {fn_name} unknown."
                else:
                    try: tool_result = await _call_tool(fn, args)
                    except Exception as e: tool_result = f"Error: {e}"

                # [P0] Observation Truncation
                obs = _truncate_obs(str(tool_result))
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})

                # [P0] Context Budget Guard
                if _ctx_size(messages) > MAX_TOTAL_CHARS:
                    logger.warning("[PLANNER] Context budget exceeded — compressing...")
                    messages = await self._compress_context(messages)

                if fn_name in TERMINAL_TOOLS:
                    return {"status": "ok", "agent": agent_id, "steps": step, "action": fn_name, "result": tool_result}

        return {"status": "max_steps", "agent": agent_id, "steps": MAX_STEPS, "response": "Step limit reached."}

    async def _compress_context(self, messages: list) -> list:
        """[P0] Summarize middle history to reclaim context."""
        system = [m for m in messages if m["role"] == "system"]
        tail = messages[-3:]
        middle = messages[len(system):-3]
        if not middle: return messages
        
        bulk = "\n".join(str(m.get("content", "")) for m in middle)
        summary = await self.ai.write(f"Summarize these agent observations concisely:\n{bulk[:6000]}")
        return system + [{"role": "assistant", "content": f"[COMPRESSED]: {summary}"}] + tail


