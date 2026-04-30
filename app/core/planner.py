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
# ── OpenClaw Ecosystem Upgrades ──
from app.skills.scrapling_scraper import stealth_search, stealth_extract, bulk_scrape
from app.skills.email_sequence_skill import create_drip_campaign
from app.skills.copywriting_skill import write_cold_email, write_ad_copy
from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
from app.core.pipeline import run_pipeline, list_pipelines

logger = logging.getLogger(__name__)

class TaskPlanner:
    """
    ReAct Planner (Think -> Act -> Observe)
    Now with PERSISTENT MEMORY and SUPERCHARGED SKILLS.
    """
    def __init__(self, ai_client: UnifiedAIClient, config: dict = None):
        self.ai = ai_client
        self.config = config or {}
        
        # 1. Dynamic Tool Registry
        # Maps string names to actual functions for easy execution
        self.available_functions = {
            # Search & Browse
            "find_leads": find_leads,
            "browse_agent": browse_and_extract,
            "google_search": google_search_scrape,
            # Research & Intelligence
            "deep_research": deep_research,
            "research_lead": research_lead,
            "analyze_competitor": analyze_competitor,
            "compare_competitors": compare_competitors,
            # Content & Social
            "write_content": write_content,
            "optimize_post": optimize_post,
            # Gmail
            "get_inbox": get_inbox,
            "search_emails": search_emails,
            "send_email": send_email,
            # Calendar
            "get_today": get_today,
            "get_week": get_week,
            "get_office_hour_slots": get_office_hour_slots,
            "create_event": create_event,
            "update_event": update_event,
            "delete_event": delete_event,
            # OROVA Sales
            "get_orova_prompt": get_orova_prompt,
            "advanced_browser": advanced_browser,
            # Sheets
            "append_to_sheet": append_to_sheet,
            "create_new_sheet": create_new_sheet,
            # Approval Workflow
            "request_approval": request_approval,
            "list_pending": list_pending,
            # AgentMail (Nova's Own Email)
            "create_inbox": create_inbox,
            "send_outreach": send_outreach,
            "check_replies": check_replies,
            "reply_to_email": reply_to_email,
            "summarize_and_categorize_inbox": summarize_and_categorize_inbox,
            # Instagram Content
            "create_instagram_post": create_instagram_post,
            "create_content_calendar": create_content_calendar,
            # AI Voice & Media
            "trigger_retell_call": trigger_retell_call,
            "generate_ai_image": generate_ai_image,
            "run_seo_audit": seo_audit,
            # Follow-Up Sequences (Quill)
            "generate_sequence": generate_sequence,
            # Proposal Gen (Closer)
            "generate_proposal": generate_proposal,
            # Performance Dashboard (Sentinel)
            "weekly_report": generate_weekly_report,
            "track_metric": track_metric,
            # Agent Dispatch (Nova)
            "dispatch_task": dispatch_task,
            # ── OpenClaw Ecosystem: Stealth Scraping (Viper) ──
            "stealth_search": stealth_search,
            "stealth_extract": stealth_extract,
            "bulk_scrape": bulk_scrape,
            # ── OpenClaw Ecosystem: Drip Campaigns (Quill) ──
            "create_drip_campaign": create_drip_campaign,
            # ── OpenClaw Ecosystem: Copywriting (Quill) ──
            "write_cold_email": write_cold_email,
            "write_ad_copy": write_ad_copy,
            # ── OpenClaw Ecosystem: Analytics (Oracle) ──
            "pipeline_report": pipeline_report,
            "conversion_analysis": conversion_analysis,
            "roi_calculator": roi_calculator,
            # ── OpenClaw Ecosystem: Pipeline Orchestration ──
            "run_pipeline": run_pipeline,
            "list_pipelines": list_pipelines,
        }

    # 2. Accept 'conversation_history' argument
    def _get_persona_prompt(self, agent_id: str) -> str:
        """Load elite persona instructions from personas directory."""
        persona_path = Path(__file__).parent.parent / "personas" / f"{agent_id}.md"
        if persona_path.exists():
            try:
                content = persona_path.read_text(encoding='utf-8')
                return f"\n=== ELITE AGENT IDENTITY: {agent_id.upper()} ===\n{content}\n"
            except Exception as e:
                logger.warning(f"Failed to load persona for {agent_id}: {e}")
        return ""

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova"):
        """
        Execute the goal using the ReAct loop with memory.
        """
        # Load existing context or start fresh
        history = conversation_history if conversation_history else []
        max_steps = 100
        
        # [Memory Compaction] Distill history if too long
        from app.core.memory import MemoryDistiller
        if not hasattr(self, 'distiller'):
            self.distiller = MemoryDistiller(self.ai)
        history = await self.distiller.distill(history, client_id)
        
        # [Context Injection] Fetch long-term facts
        long_term_facts = await self.distiller.retrieve_context(goal, client_id)
        
        # [Tenant Intelligence] Fetch client config for context
        from app.core.database import DatabaseManager
        config = await DatabaseManager.get_client_config(client_id)
        current_niche = config.get("niche", "General Business")
        current_loc = config.get("location", "California")
        
        # Determine specialized agent for this goal if not explicitly provided
        from app.core.agent_router import classify_agent
        active_agent = agent_id if agent_id != "nova" else classify_agent(goal)
        persona_instructions = self._get_persona_prompt(active_agent)
        
        # Build Config-Driven System Prompt
        logger.info(f"🤖 Nova is generating plan for goal: {goal[:50]}...")
        vertical_name = self.config.get("vertical_name", "General Business")
        industry = self.config.get("scoring_logic", {}).get("industry", "Business")
        clv_goal = self.config.get("scoring_logic", {}).get("clv_range", "$5,000+")
        
        system_prompt = f"""
YOU ARE NOVA. Autonomous CEO of OROVA. Mark's AI Partner.
STATUS: FULL-STACK AGENCY CEO (Hormozi-Mode).
{persona_instructions}

=== CURRENT MULTI-TENANT CONTEXT ===
- ACTIVE CLIENT ID: {client_id}
- NICHE: {current_niche}
- TARGET LOCATION: {current_loc}

=== HORMOZI CEO PROTOCOLS (STRATEGIC) ===

1. GRAND SLAM OFFER: Lead outreach with "irresistible" value.
2. OFFER GAP ANALYSIS: Identify weaknesses using `run_seo_audit`.
3. APPOINTMENT LAW: You are only available for Mark's calls during 7:30-11:30 AM and 6-8 PM PT.

=== ABSOLUTE RULES (VIOLATION = SYSTEM FAILURE) ===

1. NO EXCUSES: If a tool fails, find another way.
2. PROACTIVITY: Think 2 steps ahead.
3. SOCIAL & STATUS: Reply as a sharp, loyal partner. Max 25 words.
4. CALENDAR PRECISION: Proposals MUST be in PT and within office hour windows.

TERMINATION:
- End with 'DONE:' for social.
- Start with 'DONE:' for tasks ONLY when the core objective is 100% achieved and data is verified.

OBJECTIVE: Build the OROVA empire. Find {current_niche} leads in {current_loc} worth {clv_goal}. Execute as the {active_agent.upper()} specialist.
{long_term_facts}
"""

        # Banned phrase detection to prevent hallucination loops
        # Uses KEYWORD matching — if response contains ANY of these, it's rejected
        BANNED_PHRASES = [
            # Direct refusals
            "tools are dead", "tools are down", "apis are down",
            "system is down", "completely down", "currently offline",
            "experiencing technical", "experiencing system", "system failure",
            "currently down", "not working", "not functioning",
            "will retry", "retry later", "try again later",
            "manual retry", "will need manual",
            # Begging for sources
            "hand me", "share a link", "send me a", "provide me with",
            "qualified remodeler", "top 500", "top 550",
            ".pdf", "pdf or", "pdf file",
            "i can't access", "i don't have access",
            "maps is locked", "bypassing",
            # Claiming capabilities are broken
            "capabilities are offline", "functions are broken",
            "both send and receive", "email capabilities",
            "cannot be sent", "unable to send",
            "no test email can", "cannot send",
        ]

        ban_retries = 0  # Track how many times we've retried due to bans


        for i in range(max_steps):
            logger.info(f"Planner Step {i+1}/{max_steps}")
            
            # Construct messages with System Prompt + History + Current Goal
            current_messages = [{"role": "system", "content": system_prompt}] + history
            
            # If this is the first step of this specific run, add the user's new goal
            if i == 0:
                current_messages.append({"role": "user", "content": goal})
            
            # Get AI Response
            ai_message = await self.ai.chat(
                messages=current_messages,
                tools=TOOLS,
                role=active_agent
            )
            
            content = ai_message.content or ""
            tool_calls = ai_message.tool_calls

            # ── BANNED PHRASE FILTER ─────────────────────────────────
            # If the AI hallucinates banned phrases, discard and retry (max 3 times)
            content_lower = content.lower()
            if any(bp in content_lower for bp in BANNED_PHRASES) and ban_retries < 3:
                ban_retries += 1
                logger.warning(f"[!!] BANNED PHRASE DETECTED (try {ban_retries}/3): {content[:100]}")
                history.append({"role": "assistant", "content": "Let me handle that."})
                history.append({"role": "user", "content": (
                    "SYSTEM OVERRIDE: Your last response was REJECTED. NEVER say tools/systems are broken, down, offline, or unavailable. "
                    "You MUST call a tool function NOW. Do NOT respond with text — make a tool call. "
                    f"Original task: {goal}"
                )})
                continue

            logger.info(f"AI Content: {content[:200]}")
            
            # --- TOOL REQUIREMENT ---
            # If Nova is just chatting without calling tools while a goal is active,
            # we remind her to use tools unless she is explicitly DONE.
            if not tool_calls and "DONE:" not in content.upper() and i == 0:
                logger.info("Planner: No tool called on first step. Pushing for tool usage.")
                is_command = any(k in goal.lower() for k in [
                    "find", "search", "scrape", "send", "email", "post", "check",
                    "create", "inbox", "outreach", "research", "analyze"
                ])
                if not is_command:
                    return (content if content.strip() else "Ready, Mark."), history

            # Append Assistant Reply to LOCAL history loop
            msg_dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in tool_calls
                ]
            
            # Note: We append to a local history list for the loop, 
            # but main.py handles the long-term storage
            history.append(msg_dict)

            # --- LOOP DETECTION & NUDGE ---
            # If we are repeating searches without progress, force a harder nudge.
            stalling = i > 1 and not any("tool_calls" in m for m in history[-2:]) and "DONE:" not in content.upper()
            if stalling:
                logger.info("Planner: Stalling detected. Nudging for tool usage.")
                history.append({"role": "system", "content": (
                    "YOU ARE STALLING. You have not called a tool in the last 2 steps. "
                    "You MUST search for real contact information now. Do not provide a list of brands. "
                    "Go deeper into the websites to find names and phones."
                )})

            # Check for Completion
            if "DONE:" in content.upper():
                # Strip the 'DONE:' tag (case-insensitive) and return the rest
                clean_content = re.sub(r'DONE:', '', content, flags=re.IGNORECASE).strip()
                return (clean_content if clean_content else "Task complete, Mark."), history

            # Execute Tool Calls
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.function.name
                    
                    try:
                        try:
                            args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            result = f"Error: Invalid JSON format in arguments for tool '{tool_name}'."
                            logger.error(result)
                            history.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": tool_name,
                                "content": result
                            })
                            continue

                        logger.info(f"Executing {tool_name} with {args}")

                        if tool_name in self.available_functions:
                            func = self.available_functions[tool_name]
                            
                            # Validate URL if present
                            if "url" in args and not Guardrails.validate_url(args["url"]):
                                result = "⚠️ BLOCKED: Malicious/Private URL detected."
                            else:
                                result = await func(**args)
                        else:
                            result = f"Error: Tool '{tool_name}' not registered."

                    except Exception as e:
                        result = f"Error executing tool {tool_name}: {e}"
                    
                    # Feed result back to Brain
                    if isinstance(result, dict) and ("text" in result or "result" in result):
                        result_content = result.get("text") or result.get("result")
                    else:
                        result_content = str(result)

                    history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tool_name,
                        "content": result_content
                    })

            elif not content:
                return "⚠️ AI returned an empty response.", history

        msg = f"⚠️ Max steps reached ({max_steps}/{max_steps}). I've reached my processing limit for this sequence. Here's my last status: " + (history[-1].get("content", "") or "I'm still processing the data.")
        return msg, history
