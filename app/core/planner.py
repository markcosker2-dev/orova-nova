import asyncio
import inspect
import logging
import json
import re
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.ai_client import UnifiedAIClient, GroqLimpResponse

# ── Lazy skill imports ──────────────────────────────────────
# Skills are imported on first access to reduce startup time and
# memory footprint (CQ-01). Only core infra is imported eagerly.
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


class _LazyModule:
    """Lazy importer — defers heavy skill imports until first attribute access."""
    def __init__(self, import_path: str, names: list[str]):
        self._import_path = import_path
        self._names = names
        self._module = None

    def _load(self):
        if self._module is None:
            import importlib
            self._module = importlib.import_module(self._import_path)
        return self._module

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        mod = self._load()
        return getattr(mod, name)


# Lazy skill module proxies — imported only when a tool is actually called
_skills_lead_finder = _LazyModule("app.skills.lead_finder", ["find_leads", "research_lead"])
_skills_browser_ops = _LazyModule("app.skills.browser_ops", ["browse_and_extract", "google_search_scrape"])
_skills_gmail = _LazyModule("app.skills.gmail_skill", ["get_inbox", "search_emails", "send_email"])
_skills_calendar = _LazyModule("app.skills.calendar_skill", ["get_today", "get_week", "create_event", "update_event", "delete_event", "get_office_hour_slots"])
_skills_orova_sales = _LazyModule("app.skills.orova_sales_core", ["get_orova_prompt"])
_skills_seo = _LazyModule("app.skills.seo_audit", ["run_seo_audit"])
_skills_arsenal = _LazyModule("app.skills.arsenal_skills", ["advanced_browser"])
_skills_sheets = _LazyModule("app.skills.sheets_skill", ["append_to_sheet", "create_new_sheet"])
_skills_deep_research = _LazyModule("app.skills.deep_research", ["deep_research"])
_skills_competitive = _LazyModule("app.skills.competitive_intel", ["analyze_competitor", "compare_competitors"])
_skills_content = _LazyModule("app.skills.content_writer", ["write_content", "optimize_post"])
_skills_approval = _LazyModule("app.skills.approval_workflow", ["request_approval", "list_pending"])
_skills_agentmail = _LazyModule("app.skills.agentmail_skill", ["create_inbox", "send_outreach", "check_replies", "reply_to_email", "summarize_and_categorize_inbox"])
_skills_dialer = _LazyModule("app.skills.outbound_dialer", ["trigger_retell_call"])
_skills_image = _LazyModule("app.skills.image_gen", ["generate_ai_image"])
_skills_follow_up = _LazyModule("app.skills.follow_up_sequences", ["generate_sequence", "get_sequence_templates"])
_skills_proposal = _LazyModule("app.skills.proposal_gen", ["generate_proposal", "list_pricing_tiers"])
_skills_perf = _LazyModule("app.skills.perf_dashboard", ["generate_weekly_report", "track_metric"])
_skills_agent_router = _LazyModule("app.core.agent_router", ["dispatch_task", "get_all_statuses"])
_skills_notion = _LazyModule("app.skills.notion_crm", ["sync_to_notion_via_make"])
_skills_smart_scraper = _LazyModule("app.skills.smart_scraper", ["sgai_search_and_extract", "sgai_deep_extract", "enrich_lead_ai"])
_skills_email_seq = _LazyModule("app.skills.email_sequence_skill", ["create_drip_campaign"])
_skills_copywriting = _LazyModule("app.skills.copywriting_skill", ["write_cold_email", "write_ad_copy"])
_skills_analytics = _LazyModule("app.skills.analytics_skill", ["pipeline_report", "conversion_analysis", "roi_calculator"])
_skills_pipeline = _LazyModule("app.core.pipeline", ["run_pipeline", "list_pipelines"])
_skills_lead_validator = _LazyModule("app.skills.lead_validator", ["validate_contact", "score_lead"])
_skills_email_templates = _LazyModule("app.skills.email_templates", ["generate_email", "generate_follow_up_sequence"])
_skills_job_signal = _LazyModule("app.skills.job_signal_hunter", ["hunt_hiring_signals", "generate_hiring_outreach"])
_skills_apollo = _LazyModule("app.skills.apollo_enrichment", ["enrich_lead_apollo", "bulk_enrich_leads"])
_skills_timezone = _LazyModule("app.skills.timezone_scheduler", ["is_business_hours", "next_business_hours_slot"])
_skills_cal_booking = _LazyModule("app.skills.cal_booking", ["handle_cal_booking_webhook", "generate_cal_booking_link"])
_skills_email_proof = _LazyModule("app.skills.email_proofreader", ["proofread_email"])
_skills_lead_gen_v2 = _LazyModule("app.skills.lead_gen_v2", ["find_leads_v2"])
_skills_scrapling = _LazyModule("app.skills.scrapling_scraper", ["stealth_search", "stealth_extract", "bulk_scrape"])
_skills_forge = _LazyModule("app.skills.skill_forge", ["propose_skill", "activate_skill", "use_forged_skill", "list_forged_skills"])

# Safe imports for elite components (already guarded, keep as-is)
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
# Load Nova's full persona from soul.py at module init time
try:
    from app.core.soul import SYSTEM_PROMPT_BASE as _NOVA_PERSONA
except ImportError:
    _NOVA_PERSONA = (
        "You are Nova — the Autonomous CEO of OROVA. "
        "You are Mark's elite AI partner. You don't just 'assist' — you lead."
    )
_PERSONA_LOCK = _NOVA_PERSONA
from app.core.identity import IDENTITY_PROBE_RE as _IDENTITY_PROBE_RE, IDENTITY_DEFLECT as _IDENTITY_DEFLECT, normalise_for_probe as _normalise_for_probe

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
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(**args))

class TaskPlanner:
    def __init__(self, ai_client: UnifiedAIClient, config: dict = None):
        self.ai = ai_client
        self.config = config or {}
        self.distiller = MemoryDistiller(self.ai)
        logger.info("[PLANNER] MemoryDistiller integrated.")
        # CEOBrain is lightweight — import eagerly for morning_brief / pipeline_health_check
        from app.core.ceo_brain import CEOBrain
        ceo_brain = CEOBrain()
        self.available_functions = {
            # ── Guarded imports (already resolved at module level) ──
            "elite_scrape": elite_scrape or make_disabled_tool_fallback("elite_scrape", "crawl4ai dependency is not installed"),
            "vision_browse": vision_browse or make_disabled_tool_fallback("vision_browse", "browser_use dependency is not installed"),
            "composio_action": make_disabled_tool_fallback("composio_action", "Composio integration is not configured"),
            # ── Lazy-loaded skills (imported on first call via _LazyModule proxy) ──
            "sgai_search_and_extract": _skills_smart_scraper.sgai_search_and_extract,
            "sgai_deep_extract": _skills_smart_scraper.sgai_deep_extract,
            "enrich_lead_ai": _skills_smart_scraper.enrich_lead_ai,
            "find_leads": _skills_lead_finder.find_leads,
            "browse_agent": _skills_browser_ops.browse_and_extract,
            "google_search": _skills_browser_ops.google_search_scrape,
            "deep_research": _skills_deep_research.deep_research,
            "research_lead": _skills_lead_finder.research_lead,
            "analyze_competitor": _skills_competitive.analyze_competitor,
            "compare_competitors": _skills_competitive.compare_competitors,
            "write_content": _skills_content.write_content,
            "optimize_post": _skills_content.optimize_post,
            "get_inbox": _skills_gmail.get_inbox,
            "search_emails": _skills_gmail.search_emails,
            "send_email": _skills_gmail.send_email,
            "get_today": _skills_calendar.get_today,
            "get_week": _skills_calendar.get_week,
            "get_office_hour_slots": _skills_calendar.get_office_hour_slots,
            "create_event": _skills_calendar.create_event,
            "update_event": _skills_calendar.update_event,
            "delete_event": _skills_calendar.delete_event,
            "get_orova_prompt": _skills_orova_sales.get_orova_prompt,
            "advanced_browser": _skills_arsenal.advanced_browser,
            "append_to_sheet": _skills_sheets.append_to_sheet,
            "create_new_sheet": _skills_sheets.create_new_sheet,
            "request_approval": _skills_approval.request_approval,
            "list_pending": _skills_approval.list_pending,
            "create_inbox": _skills_agentmail.create_inbox,
            "send_outreach": _skills_agentmail.send_outreach,
            "check_replies": _skills_agentmail.check_replies,
            "reply_to_email": _skills_agentmail.reply_to_email,
            "summarize_and_categorize_inbox": _skills_agentmail.summarize_and_categorize_inbox,
            "trigger_retell_call": _skills_dialer.trigger_retell_call,
            "generate_ai_image": _skills_image.generate_ai_image,
            "run_seo_audit": _skills_seo.run_seo_audit,
            "generate_sequence": _skills_follow_up.generate_sequence,
            "generate_proposal": _skills_proposal.generate_proposal,
            "weekly_report": _skills_perf.generate_weekly_report,
            "track_metric": _skills_perf.track_metric,
            "dispatch_task": _skills_agent_router.dispatch_task,
            "create_drip_campaign": _skills_email_seq.create_drip_campaign,
            "write_cold_email": _skills_copywriting.write_cold_email,
            "write_ad_copy": _skills_copywriting.write_ad_copy,
            "pipeline_report": _skills_analytics.pipeline_report,
            "conversion_analysis": _skills_analytics.conversion_analysis,
            "roi_calculator": _skills_analytics.roi_calculator,
            "run_pipeline": _skills_pipeline.run_pipeline,
            "list_pipelines": _skills_pipeline.list_pipelines,
            "validate_contact": _skills_lead_validator.validate_contact,
            "score_lead": _skills_lead_validator.score_lead,
            "generate_email": _skills_email_templates.generate_email,
            "generate_follow_up_sequence": _skills_email_templates.generate_follow_up_sequence,
            "hunt_hiring_signals": _skills_job_signal.hunt_hiring_signals,
            "generate_hiring_outreach": _skills_job_signal.generate_hiring_outreach,
            "enrich_lead_apollo": _skills_apollo.enrich_lead_apollo,
            "bulk_enrich_leads": _skills_apollo.bulk_enrich_leads,
            "is_business_hours": _skills_timezone.is_business_hours,
            "next_business_hours_slot": _skills_timezone.next_business_hours_slot,
            "generate_cal_booking_link": _skills_cal_booking.generate_cal_booking_link,
            "sync_to_notion_via_make": _skills_notion.sync_to_notion_via_make,
            "proofread_email": _skills_email_proof.proofread_email,
            "morning_brief": ceo_brain.morning_brief,
            "pipeline_health_check": ceo_brain.pipeline_health_check,
            "find_leads_v2": _skills_lead_gen_v2.find_leads_v2,
            "stealth_search": _skills_scrapling.stealth_search,
            "stealth_extract": _skills_scrapling.stealth_extract,
            "bulk_scrape": _skills_scrapling.bulk_scrape,
            # ── Skill Forge: dynamic tool acquisition (approval-gated) ──
            "propose_skill": _skills_forge.propose_skill,
            "activate_skill": _skills_forge.activate_skill,
            "use_forged_skill": _skills_forge.use_forged_skill,
            "list_forged_skills": _skills_forge.list_forged_skills,
        }
        self.firewall = get_semantic_firewall(self.config.get("firewall_config"))
        logger.info("[PLANNER] Semantic Firewall integrated.")

    HUNTING_TOOLS = ["sgai_search_and_extract", "sgai_deep_extract", "find_leads", "find_leads_v2", "google_search", "research_lead", "hunt_hiring_signals", "enrich_lead_ai"]
    OUTREACH_TOOLS = ["send_outreach", "send_email", "write_cold_email", "create_drip_campaign", "generate_sequence", "check_replies", "reply_to_email", "get_inbox", "trigger_retell_call", "generate_hiring_outreach", "enrich_lead_apollo", "is_business_hours", "composio_action", "proofread_email", "morning_brief", "pipeline_health_check"]
    LIGHT_RESEARCH_TOOLS = ["deep_research", "browse_agent", "run_seo_audit", "bulk_enrich_leads", "next_business_hours_slot", "generate_cal_booking_link", "elite_scrape", "vision_browse", "stealth_search", "stealth_extract", "bulk_scrape", "propose_skill", "activate_skill", "use_forged_skill", "list_forged_skills"]

    def _scope_tools(self, goal: str) -> list:
        if not TOOLS:
            logger.critical("[PLANNER] TOOLS list is empty — check app/skills/definitions.py")
            return []
        goal_lower = goal.lower()
        if _EMAIL_RE.search(goal): scope = self.OUTREACH_TOOLS
        elif any(k in goal_lower for k in ["find leads", "search for", "hunt", "prospect"]): scope = self.HUNTING_TOOLS
        elif any(k in goal_lower for k in ["send", "email", "outreach", "reply", "follow up"]): scope = self.OUTREACH_TOOLS
        else: scope = self.OUTREACH_TOOLS + self.LIGHT_RESEARCH_TOOLS + self.HUNTING_TOOLS
        scoped = [t for t in TOOLS if t["function"]["name"] in scope]
        if not scoped:
            logger.warning(f"[PLANNER] No tools matched scope for goal: {goal[:80]!r}")
        return scoped

    async def _decompose_goal(self, goal: str) -> str:
        """Hierarchical planning: break a complex goal into subgoals with
        verifiable success criteria. One cheap LLM call, only for goals that
        look multi-step; returns '' on any failure so execution never blocks.
        """
        looks_complex = len(goal) > 120 or " and " in goal.lower() or goal.count(".") >= 2
        if not looks_complex:
            return ""
        try:
            plan = await self.ai.quick(
                "Decompose this goal into 2-5 numbered subgoals. For each, add "
                "'DONE WHEN: <observable success criterion>'. Be terse.\n\nGOAL: " + goal[:600]
            )
            return (plan or "").strip()[:1200]
        except Exception as e:
            logger.debug(f"[PLANNER] Decomposition skipped: {e}")
            return ""

    async def _verify_outcome(self, goal: str, plan: str, tool_call_history: list, final_result: str, client_id: int):
        """Subgoal verification: judge whether the execution actually met the
        goal. Failures are stored as memory fragments so the CEO brain audit
        and semantic recall learn from them.
        """
        try:
            actions = "; ".join(
                f"{h['tool_name']}({h.get('decision','')})" for h in tool_call_history[-8:]
            ) or "no tool calls"
            verdict = await self.ai.quick(
                "You are auditing an autonomous agent run. Reply with exactly "
                "'PASS: <reason>' or 'FAIL: <reason>' in one line.\n\n"
                f"GOAL: {goal[:400]}\n"
                + (f"PLAN: {plan[:400]}\n" if plan else "")
                + f"ACTIONS: {actions}\n"
                f"FINAL RESULT: {str(final_result)[:400]}"
            )
            verdict = (verdict or "").strip()
            if verdict.upper().startswith("FAIL"):
                logger.warning(f"[PLANNER] Outcome verification FAILED: {verdict[:200]}")
                await self.distiller._store_fragment(
                    f"TASK AUDIT FAIL — goal: {goal[:200]} | verdict: {verdict[:300]}",
                    client_id,
                )
            else:
                logger.info(f"[PLANNER] Outcome verification: {verdict[:120]}")
        except Exception as e:
            logger.debug(f"[PLANNER] Outcome verification skipped: {e}")

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
        # Hierarchical planning: decompose complex goals into verifiable subgoals
        subgoal_plan = await self._decompose_goal(goal)
        if subgoal_plan:
            system_content += f"\n\n=== EXECUTION PLAN (follow in order, each subgoal has a DONE-WHEN check) ===\n{subgoal_plan}\n==="

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
                except (json.JSONDecodeError, TypeError, ValueError):
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
                    await self._verify_outcome(goal, subgoal_plan, tool_call_history, str(tool_result), client_id)
                    return {"status": "ok", "agent": agent_id, "steps": step, "action": fn_name, "result": tool_result}

        trace_manager.complete_trace(session_id, "max_steps", response="Step limit reached.")
        execution_circuit_breaker.complete_session(session_id, "max_steps")
        efficiency_optimizer.complete_session(session_id)
        await self._record_learning_trace(session_id, agent_id, goal, tool_call_history, client_id, "max_steps", MAX_STEPS, task_start_time)
        await self._verify_outcome(goal, subgoal_plan, tool_call_history, "Step limit reached without terminal action", client_id)
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