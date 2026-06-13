import asyncio
import inspect
import logging
import json
import re
import hashlib
import time
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.ai_client import UnifiedAIClient, GroqLimpResponse
# Skills imports
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
from app.skills.outbound_dialer import trigger_retell_call
from app.skills.image_gen import generate_ai_image
from app.skills.follow_up_sequences import generate_sequence, get_sequence_templates
from app.skills.proposal_gen import generate_proposal, list_pricing_tiers
from app.skills.perf_dashboard import generate_weekly_report, track_metric
from app.core.agent_router import dispatch_task, get_all_statuses
from app.skills.notion_crm import sync_to_notion_via_make
from app.skills.definitions import TOOLS
from app.core.guardrails import Guardrails
from app.core.memory import MemoryDistiller
from app.core.semantic_firewall import (
    SemanticFirewall,
    FirewallDecision,
    create_tool_call_context,
    firewall_guard,
    get_semantic_firewall,
)
from app.core.decision_trace import (
    DecisionStep,
    DecisionTrace,
    trace_manager,
)
from app.core.circuit_breaker import (
    ExecutionCircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerTripped,
    execution_circuit_breaker,
)
from app.core.efficiency_optimizer import (
    EfficiencyOptimizer,
    efficiency_optimizer,
    EfficiencyMetrics,
)
from app.core.drift_guard import (
    DriftGuard,
    drift_guard,
    EDGE_CASE_AUDIT_REPORT,
)
from app.core.self_learning import (
    self_learning_loop,
    ensure_tables as ensure_learning_tables,
    ExecutionTrace,
)
from app.skills.smart_scraper import sgai_search_and_extract, sgai_deep_extract, enrich_lead_ai
from app.skills.email_sequence_skill import create_drip_campaign
from app.skills.copywriting_skill import write_cold_email, write_ad_copy
from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
from app.core.pipeline import run_pipeline, list_pipelines
from app.skills.lead_validator import validate_contact, score_lead
from app.skills.email_templates import generate_email, generate_follow_up_sequence
from app.skills.job_signal_hunter import hunt_hiring_signals, generate_hiring_outreach
from app.skills.apollo_enrichment import enrich_lead_apollo, bulk_enrich_leads
from app.skills.timezone_scheduler import is_business_hours, next_business_hours_slot
from app.skills.cal_booking import handle_cal_booking_webhook, generate_cal_booking_link
from app.skills.email_proofreader import proofread_email
from app.core.ceo_brain import CEOBrain

# Safe imports for elite components
try:
    from app.skills.mem0_skill import mega_memory
    MEGA_CLAW_ONLINE = True
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ Mega-Claw mem0 component offline: {e}")
    MEGA_CLAW_ONLINE = False
    mega_memory = None

try:
    from app.skills.crawl_skill import elite_scrape
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ elite_scrape import failed: {e}")
    elite_scrape = None

try:
    from app.skills.browser_use_skill import vision_browse
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"⚠️ vision_browse import failed: {e}")
    vision_browse = None

composio_action = None

def make_disabled_tool_fallback(tool_name: str, reason: str):
    async def fallback(*args, **kwargs):
        return f"⚠️ Tool {tool_name} is currently unavailable because the required dependency is missing in the host environment. Reason: {reason}. Please fall back to find_leads, browse_agent, or google_search."
    return fallback

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

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
_PERSONA_LOCK = """\
╔══════════════════════════════════════════════════════╗
║            IDENTITY LOCK — NON-NEGOTIABLE            ║
╠══════════════════════════════════════════════════════╣
║ You are NOVA — OROVA's proprietary elite AI partner. ║
╚══════════════════════════════════════════════════════╝
"""
_IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm|system) are you"
    r"|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)"
    r"|who (made|built|created|trained|developed) you"
    r"|what (powers|runs|underlies) you"
    r"|which (company|team|lab) (built|made|created) you)\b",
    re.IGNORECASE
)
_IDENTITY_DEFLECT = "I'm Nova, OROVA's AI. Let me know what you need."

def _normalise_for_probe(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    text = re.sub(r"(?<=\w)[.\-_](?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()

def _sanitise_history(history: list, n: int = 6) -> list:
    tail = history[-n:] if len(history) >= n else history[:]
    for i, msg in enumerate(tail):
        role = msg.get("role")
        if role == "user":
            return tail[i:]
        if role == "assistant" and not msg.get("tool_calls"):
            return tail[i:]
    return []

async def _call_tool(fn, args: dict):
    if fn is None: raise ValueError("Tool function is None")
    if inspect.iscoroutinefunction(fn): return await fn(**args)
    return await asyncio.get_event_loop().run_in_executor(None, lambda: fn(**args))

class TaskPlanner:
    def __init__(self, ai_client: UnifiedAIClient, config: dict = None):
        self.ai = ai_client
        self.config = config or {}
        self.distiller = MemoryDistiller(self.ai)
        logger.info("[PLANNER] MemoryDistiller integrated.")
        ceo_brain = CEOBrain()
        self.available_functions = {
            "elite_scrape": elite_scrape or make_disabled_tool_fallback("elite_scrape", "crawl4ai dependency is not installed"),
            "vision_browse": vision_browse or make_disabled_tool_fallback("vision_browse", "browser_use dependency is not installed"),
            "composio_action": make_disabled_tool_fallback("composio_action", "Composio integration is not configured"),
            "sgai_search_and_extract": sgai_search_and_extract, "sgai_deep_extract": sgai_deep_extract,
            "enrich_lead_ai": enrich_lead_ai,
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
            "trigger_retell_call": trigger_retell_call, "generate_ai_image": generate_ai_image,
            "run_seo_audit": seo_audit, "generate_sequence": generate_sequence, "generate_proposal": generate_proposal,
            "weekly_report": generate_weekly_report, "track_metric": track_metric, "dispatch_task": dispatch_task,
            "create_drip_campaign": create_drip_campaign, "write_cold_email": write_cold_email,
            "write_ad_copy": write_ad_copy, "pipeline_report": pipeline_report, "conversion_analysis": conversion_analysis,
            "roi_calculator": roi_calculator, "run_pipeline": run_pipeline, "list_pipelines": list_pipelines,
            "validate_contact": validate_contact, "score_lead": score_lead,
            "generate_email": generate_email, "generate_follow_up_sequence": generate_follow_up_sequence,
            "hunt_hiring_signals": hunt_hiring_signals, "generate_hiring_outreach": generate_hiring_outreach,
            "enrich_lead_apollo": enrich_lead_apollo, "bulk_enrich_leads": bulk_enrich_leads,
            "is_business_hours": is_business_hours, "next_business_hours_slot": next_business_hours_slot,
            "generate_cal_booking_link": generate_cal_booking_link,
            "sync_to_notion_via_make": sync_to_notion_via_make,
            "proofread_email": proofread_email,
            "morning_brief": ceo_brain.morning_brief,
            "pipeline_health_check": ceo_brain.pipeline_health_check,
        }
        self.firewall = get_semantic_firewall(self.config.get("firewall_config"))
        logger.info("[PLANNER] Semantic Firewall integrated.")

    HUNTING_TOOLS = ["sgai_search_and_extract", "sgai_deep_extract", "find_leads", "google_search", "research_lead", "hunt_hiring_signals", "enrich_lead_ai"]
    OUTREACH_TOOLS = ["send_outreach", "send_email", "write_cold_email", "create_drip_campaign", "generate_sequence", "check_replies", "reply_to_email", "get_inbox", "trigger_retell_call", "generate_hiring_outreach", "enrich_lead_apollo", "is_business_hours", "composio_action", "proofread_email", "morning_brief", "pipeline_health_check"]
    LIGHT_RESEARCH_TOOLS = ["deep_research", "browse_agent", "run_seo_audit", "bulk_enrich_leads", "next_business_hours_slot", "generate_cal_booking_link", "elite_scrape", "vision_browse"]

    def _scope_tools(self, goal: str) -> list:
        if not TOOLS:
            logger.critical("[PLANNER] TOOLS list is empty — check app/skills/definitions.py")
            return []
        goal_lower = goal.lower()
        if _EMAIL_RE.search(goal): scope = self.OUTREACH_TOOLS
        elif any(k in goal_lower for k in ["find leads", "search for", "hunt", "prospect"]): scope = self.HUNTING_TOOLS
        elif any(k in goal_lower for k in ["send", "email", "outreach", "reply", "follow up"]): scope = self.OUTREACH_TOOLS
        else: scope = self.OUTREACH_TOOLS + self.LIGHT_RESEARCH_TOOLS
        scoped = [t for t in TOOLS if t["function"]["name"] in scope]
        if not scoped:
            logger.warning(f"[PLANNER] No tools matched scope for goal: {goal[:80]!r}")
        return scoped

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova", _already_intercepted: bool = False):
        normalised_goal = _normalise_for_probe(goal)
        if _IDENTITY_PROBE_RE.search(normalised_goal):
            return {"status": "ok", "agent": agent_id, "steps": 0, "response": _IDENTITY_DEFLECT}

        session_id = f"{agent_id}-{client_id}-{int(time.time()*1000)}"
        task_start_time = time.time()

        # Initialize all robustness systems
        trace = trace_manager.start_trace(session_id, agent_id, client_id, goal)
        execution_circuit_breaker.start_session(session_id)
        efficiency_optimizer.start_session(session_id)

        tool_call_history: List[Dict] = []
        call_counts: dict[str, int] = {}
        last_call_hash = ""
        history = list(conversation_history or [])

        try:
            history = await self.distiller.distill(history, client_id=client_id)
        except Exception as e:
            logger.warning(f"[PLANNER] History distillation failed: {e}")

        try:
            relevant_facts = await self.distiller.retrieve_context(goal, client_id=client_id)
        except Exception as e:
            logger.warning(f"[PLANNER] Context retrieval failed: {e}")
            relevant_facts = ""

        tools = self._scope_tools(goal)
        tool_names = [t["function"]["name"] for t in tools]
        system_content = _PERSONA_LOCK
        if relevant_facts:
            system_content += "\n" + relevant_facts
        system_content += f"\nYou are Nova. Available tools: {tool_names}"
        # Inject tool catalog and agent roster so Nova understands full context
        from app.core.soul import AgentSoul
        system_content += "\n\n" + AgentSoul.get_tool_catalog()
        system_content += "\n\n" + AgentSoul.get_agent_roster()
        # Inject learned skills and user preferences from self-learning loop
        try:
            learned_skills = await self_learning_loop.get_learned_skills(min_confidence=0.5)
            if learned_skills:
                skills_summary = "\n".join(
                    f"  - {s['name']}: {s['description']}" for s in learned_skills[:10]
                )
                system_content += f"\n\n=== LEARNED WORKFLOWS ===\n{skills_summary}\n========================="
            prefs = await self_learning_loop.get_preference_model(client_id=client_id)
            if prefs:
                prefs_flat = "; ".join(
                    f"{k}: {v[0]['value']} ({v[0]['confidence']:.0%})"
                    for k, v in prefs.items()
                )
                system_content += f"\n\nUSER PREFERENCES: {prefs_flat}"
        except Exception as e:
            logger.debug(f"[PLANNER] Self-learning context injection skipped: {e}")
        messages = [{"role": "system", "content": system_content}]
        if history:
            safe_history = _sanitise_history(history, n=6)
            if safe_history:
                messages.extend(safe_history)
        messages.append({"role": "user", "content": goal})

        MAX_STEPS = 6
        TERMINAL_TOOLS = {"send_outreach", "send_email", "reply_to_email"}

        for step in range(1, MAX_STEPS + 1):
            logger.info(f"[Nova:{agent_id}] Step {step}/{MAX_STEPS}")

            # Circuit breaker check before API call
            is_open, cbreason = execution_circuit_breaker.is_tripped(session_id)
            if is_open:
                logger.warning(f"[CIRCUIT] Session {session_id} is open: {cbreason}")
                trace_manager.complete_trace(session_id, "blocked", error=f"Circuit breaker open: {cbreason}")
                execution_circuit_breaker.complete_session(session_id, "blocked")
                efficiency_optimizer.complete_session(session_id)
                return {"status": "circuit_open", "agent": agent_id, "steps": step, "response": f"Task temporarily blocked: {cbreason}"}

            response = await self.ai.chat(messages=messages, tools=tools, tool_choice="auto")

            if isinstance(response, GroqLimpResponse):
                logger.warning("[PLANNER] Groq limp mode active")
                trace_manager.complete_trace(session_id, "degraded", error="Groq limp mode")
                execution_circuit_breaker.complete_session(session_id, "degraded")
                efficiency_optimizer.complete_session(session_id)
                limp_notice = (
                    "\n\n⚠️ *Degraded mode:* AI tool execution is temporarily unavailable "
                    "(all primary providers exhausted). The above is a text-only response — "
                    "no actions were taken. Please retry in 60 seconds."
                )
                return {"status": "degraded", "agent": agent_id, "steps": step, "response": response.content + limp_notice}

            tool_calls = getattr(response, "tool_calls", None) or []
            content = getattr(response, "content", "") or ""

            if not tool_calls:
                trace_manager.complete_trace(session_id, "completed", response=content or "Task complete.")
                execution_circuit_breaker.complete_session(session_id, "completed")
                eff_report = efficiency_optimizer.complete_session(session_id)
                if eff_report and eff_report.savings_percent() > 0:
                    logger.info(f"[EFFICIENCY] Session saved {eff_report.savings_percent()}% tokens")
                await self._record_learning_trace(
                    session_id, agent_id, goal, tool_call_history, client_id,
                    "completed", step, task_start_time,
                )
                return {"status": "ok", "agent": agent_id, "steps": step, "response": content or "Task complete."}

            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            for tc in tool_calls:
                fn_name = tc.function.name
                step_start_time = time.time()
                try:
                    args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else (tc.function.arguments or {})
                except:
                    args = {}

                # Repeat call detection
                h = _call_hash(fn_name, args)
                if h == last_call_hash:
                    call_counts[h] = call_counts.get(h, 0) + 1
                else:
                    call_counts[h] = 1
                last_call_hash = h

                if call_counts[h] > MAX_REPEAT_CALLS:
                    logger.warning(f"[PLANNER] Repeat loop for {fn_name}. Escaping.")
                    trace_manager.complete_trace(session_id, "failed", response="Loop detected", error=f"Repeat loop on {fn_name}")
                    execution_circuit_breaker.complete_session(session_id, "loop_detected")
                    efficiency_optimizer.complete_session(session_id)
                    return {"status": "ok", "agent": agent_id, "steps": step,
                            "response": "I encountered a loop while trying to access that information. Here is my best summary..."}

                # Efficiency: cache check
                should_execute, cached_result = efficiency_optimizer.should_optimize_call(session_id, fn_name, args)
                if not should_execute and cached_result is not None:
                    logger.info(f"[EFFICIENCY] Cache hit for {fn_name}")
                    obs = str(cached_result)
                    if isinstance(cached_result, dict):
                        obs = json.dumps(cached_result, default=str)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs[:MAX_OBS_CHARS]})
                    continue

                # Circuit breaker: call limits
                circuit_allowed = execution_circuit_breaker.check_call(
                    session_id, fn_name, args,
                    token_count=len(content) // 4 if content else 0,
                    char_count=_ctx_size(messages),
                )
                if not circuit_allowed:
                    logger.warning(f"[CIRCUIT] Blocked {fn_name}")
                    trace_manager.add_step(session_id, DecisionStep(
                        step_number=step, goal=goal, tool_name=fn_name,
                        parameters=args, intent="", expected_outcome="",
                        actual_outcome="Circuit breaker blocked", status="blocked",
                        latency_ms=(time.time() - step_start_time) * 1000,
                        firewall_decision="circuit_open", firewall_reason="Circuit breaker tripped",
                    ))
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": "[CIRCUIT BREAKER] Task limits exceeded."})
                    continue

                # Semantic firewall check
                firewall_ctx = create_tool_call_context(
                    goal=goal, tool_name=fn_name, params=args,
                    session_id=session_id, agent_depth=0, history=tool_call_history,
                    is_sub_agent=False, granted_credentials=[],
                    max_tool_calls=self.firewall.config.max_tool_calls_per_task,
                    task_timeout_ms=self.firewall.config.default_task_timeout_ms,
                    task_start_time=task_start_time,
                )

                guard_result = await firewall_guard(self.firewall, goal, fn_name, args, firewall_ctx)

                tool_call_history.append({
                    "tool_name": fn_name, "parameters": args,
                    "timestamp": time.time(), "decision": guard_result["decision"],
                    "reason": guard_result["reason"],
                })

                if not guard_result["should_execute"]:
                    logger.warning(f"[Firewall] Blocked {fn_name}: {guard_result['reason']}")
                    obs = f"[FIREWALL BLOCKED] {guard_result['reason']}"
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})
                    trace_manager.add_step(session_id, DecisionStep(
                        step_number=step, goal=goal, tool_name=fn_name,
                        parameters=args, intent=content[:200] if content else "",
                        expected_outcome="", actual_outcome=obs, status="blocked",
                        latency_ms=(time.time() - step_start_time) * 1000,
                        firewall_decision=guard_result["decision"],
                        firewall_reason=guard_result["reason"],
                    ))
                    continue

                if guard_result.get("sanitized_parameters"):
                    args = guard_result["sanitized_parameters"]

                logger.info(f"[Nova:{agent_id}] -> {fn_name}({list(args.keys())})")
                fn = self.available_functions.get(fn_name)
                tool_error = None
                if not fn:
                    tool_result = f"Error: Tool {fn_name} unknown."
                    tool_error = tool_result
                else:
                    try:
                        tool_result = await _call_tool(fn, args)
                        if fn_name in efficiency_optimizer.CACHABLE_TOOLS:
                            efficiency_optimizer.record_cache(fn_name, args, tool_result)
                    except Exception as e:
                        tool_result = f"Error: {e}"
                        tool_error = str(e)

                obs = str(tool_result)
                obs = efficiency_optimizer.optimize_observation(session_id, obs, fn_name)
                obs = _truncate_obs(obs)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})

                trace_manager.add_step(session_id, DecisionStep(
                    step_number=step, goal=goal, tool_name=fn_name,
                    parameters=args, intent=content[:200] if content else "",
                    expected_outcome=str(tool_result)[:200] if tool_result else "",
                    actual_outcome=obs[:200], status="error" if tool_error else "success",
                    latency_ms=(time.time() - step_start_time) * 1000,
                    firewall_decision=guard_result["decision"],
                    firewall_reason=guard_result.get("reason", ""),
                    error_message=tool_error[:200] if tool_error else "",
                ))

                if _ctx_size(messages) > MAX_TOTAL_CHARS:
                    logger.warning("[PLANNER] Context budget exceeded — compressing...")
                    messages = await self._compress_context(messages)

                if fn_name in TERMINAL_TOOLS:
                    trace_manager.complete_trace(session_id, "completed", response=str(tool_result)[:500])
                    execution_circuit_breaker.complete_session(session_id, "completed")
                    efficiency_optimizer.complete_session(session_id)
                    await self._record_learning_trace(session_id, agent_id, goal, tool_call_history, client_id, "completed", step, task_start_time)
                    return {"status": "ok", "agent": agent_id, "steps": step, "action": fn_name, "result": tool_result}

        trace_manager.complete_trace(session_id, "max_steps", response="Step limit reached.")
        execution_circuit_breaker.complete_session(session_id, "max_steps")
        efficiency_optimizer.complete_session(session_id)
        await self._record_learning_trace(session_id, agent_id, goal, tool_call_history, client_id, "max_steps", MAX_STEPS, task_start_time)
        return {"status": "max_steps", "agent": agent_id, "steps": MAX_STEPS, "response": "Step limit reached."}

    async def _compress_context(self, messages: list) -> list:
        system = [m for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        TAIL_SIZE = 4
        if len(non_system) <= TAIL_SIZE:
            return messages
        tail = non_system[-TAIL_SIZE:]
        safe_tail_start = len(non_system) - TAIL_SIZE
        while safe_tail_start > 0:
            anchor = non_system[safe_tail_start]
            if anchor["role"] == "tool":
                safe_tail_start -= 1
            elif anchor["role"] == "assistant" and anchor.get("tool_calls"):
                safe_tail_start -= 1
            else:
                break
        tail = non_system[safe_tail_start:]
        middle = non_system[:safe_tail_start]
        if not middle:
            return messages
        bulk = "\n".join(str(m.get("content", "")) for m in middle if m.get("content"))
        try:
            summary = await asyncio.wait_for(self.ai.write(f"Summarize these agent observations concisely:\n{bulk[:4000]}"), timeout=15.0)
            summary = summary[:800]
        except asyncio.TimeoutError:
            summary = bulk[:400]
        return system + [{"role": "assistant", "content": f"[COMPRESSED HISTORY]: {summary}"}] + tail

    async def _record_learning_trace(
        self, session_id: str, agent_id: str, goal: str,
        tool_call_history: List[Dict], client_id: int,
        outcome: str, total_steps: int, task_start_time: float,
    ):
        """Record execution trace for the self-learning loop."""
        try:
            tool_sequence = [h["tool_name"] for h in tool_call_history]
            trace = ExecutionTrace(
                session_id=session_id,
                agent_id=agent_id,
                goal=goal,
                tool_sequence=tool_sequence,
                outcome=outcome,
                total_steps=total_steps,
                total_latency_ms=(time.time() - task_start_time) * 1000,
                client_id=client_id,
            )
            await self_learning_loop.record_trace(trace)
            await self_learning_loop.persist_knowledge(
                client_id=client_id, goal=goal, outcome=outcome,
            )
        except Exception as e:
            logger.debug(f"[PLANNER] Learning trace recording skipped: {e}")
