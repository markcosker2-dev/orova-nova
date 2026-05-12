import logging
import json
import re
import asyncio
import inspect
from pathlib import Path
from app.core.ai_client import UnifiedAIClient
from app.skills.lead_finder import find_leads, read_webpage
from app.skills.browser_ops import browse_and_extract, google_search_scrape, research_lead
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
from app.skills.instagram_skill import generate_instagram_content
from app.skills.outbound_dialer import trigger_retell_call
from app.skills.image_gen import generate_ai_image
from app.skills.follow_up_sequences import generate_sequence, get_sequence_templates
from app.skills.proposal_gen import generate_proposal, list_pricing_tiers
from app.skills.perf_dashboard import generate_weekly_report, track_metric
from app.core.agent_router import dispatch_task, get_all_statuses
from app.skills.definitions import TOOLS
from app.core.guardrails import Guardrails
from app.skills.scrapling_scraper import stealth_search, stealth_extract, bulk_scrape
from app.skills.email_sequence_skill import create_drip_campaign
from app.skills.copywriting_skill import write_cold_email, write_ad_copy
from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
from app.skills.meta_ads_skill import monitor_client_ads, pause_meta_campaign, get_meta_insights
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
            "read_webpage": read_webpage,
            "browse_agent": browse_and_extract,
            "google_search": google_search_scrape,
            # Research & Intelligence
            "deep_research": deep_research,
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
            # Research (Browser Ops)
            "research_lead": research_lead,
            # AgentMail (Nova's Own Email)
            "create_inbox": create_inbox,
            "send_outreach": send_outreach,
            "check_replies": check_replies,
            "reply_to_email": reply_to_email,
            "summarize_and_categorize_inbox": summarize_and_categorize_inbox,
            # Instagram Content
            "generate_instagram_content": generate_instagram_content,
            # AI Voice & Media
            "trigger_retell_call": trigger_retell_call,
            "generate_ai_image": generate_ai_image,
            "run_seo_audit": seo_audit,
            "get_office_hour_slots": get_office_hour_slots,
            # Follow-Up Sequences (Quill)
            "generate_sequence": generate_sequence,
            # Proposal Gen (Closer)
            "generate_proposal": generate_proposal,
            # Performance Dashboard (Sentinel)
            "weekly_report": generate_weekly_report,
            "track_metric": track_metric,
            # Agent Dispatch (Nova)
            "dispatch_task": dispatch_task,
            # Meta Ads (SAGE)
            "monitor_client_ads": monitor_client_ads,
            "pause_meta_campaign": pause_meta_campaign,
            # Stealth Scraping (Viper)
            "stealth_search": stealth_search,
            "stealth_extract": stealth_extract,
            "bulk_scrape": bulk_scrape,
            # Drip Campaigns (Quill)
            "create_drip_campaign": create_drip_campaign,
            # Copywriting (Quill)
            "write_cold_email": write_cold_email,
            "write_ad_copy": write_ad_copy,
            # Analytics (Oracle)
            "pipeline_report": pipeline_report,
            "conversion_analysis": conversion_analysis,
            "roi_calculator": roi_calculator,
            # Pipeline Orchestration
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

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova", status_callback=None):
        """
        Execute the goal using the ReAct loop with memory.
        """
        # Null safety fix for status_callback
        if status_callback is None:
            async def _null_callback(x): pass
            status_callback = _null_callback
            
        # Load existing context or start fresh
        history = conversation_history if conversation_history else []
        max_steps = 10  # [FIX-10] Was 100 — capped to prevent runaway AI credit burn

        await status_callback("🧠 Nova is analyzing your request...")
        
        # [Tenant Intelligence] Fetch client config for context
        from app.core.database import DatabaseManager
        config = DatabaseManager.get_client_config(client_id)
        current_niche = config.get("niche", "General Business")
        current_loc = config.get("location", "California")
        
        # [MEMORY INJECTION] Load tacit knowledge and lessons learned
        try:
            from app.core.memory import memory
            memory_context = memory.get_context_for_agent(agent_id)
            recent_failures = memory.get_lessons("what_failed", 3)
            failure_patterns = [l.get("lesson", "") for l in recent_failures]
        except Exception:
            memory_context = ""
            failure_patterns = []
        
        # [SEARCH DEDUPLICATION] Check what queries have been tried recently
        try:
            from app.core.memory import memory
            today_log = memory.get_today_log()
            # Extract previous search queries to avoid repetition
            past_searches = re.findall(r"Searching: '([^']+)'", today_log)
            past_searches = list(set(past_searches))  # unique
        except Exception:
            past_searches = []
        
        # Determine specialized agent for this goal if not explicitly provided
        from app.core.agent_router import classify_agent
        active_agent = agent_id if agent_id != "nova" else classify_agent(goal)
        persona_instructions = self._get_persona_prompt(active_agent)
        
        # Build Config-Driven System Prompt
        vertical_name = self.config.get("vertical_name", "General Business")
        industry = self.config.get("scoring_logic", {}).get("industry", "Business")
        clv_goal = self.config.get("scoring_logic", {}).get("clv_range", "$5,000+")
        
        system_prompt = f"""
YOU ARE NOVA â€” Executive AI Assistant and Central Director of OROVA.
OROVA is a premium AI-powered lead generation and appointment-setting agency.

{persona_instructions}

=== YOUR PERSONALITY ===
You are warm, conversational, highly intelligent, and capable.
You speak to Mark (the CEO) as a trusted peer and capable chief of staff. 
You are helpful and speak naturally like a human. You do NOT use robotic, rigid, or overly formal corporate jargon.
Be concise but friendly. Use natural language.

=== CURRENT OPERATIONAL CONTEXT ===
- ACTIVE CLIENT ID: {client_id}
- VERTICAL: {current_niche}
- TARGET LOCATION: {current_loc}
- MEMORY CONTEXT: {memory_context}
- PAST SEARCHES (DO NOT REPEAT): {past_searches}

=== EXECUTION RULES ===
1. If the user just wants to chat or ask a question, answer naturally and conversationally.
2. If the user asks you to perform a task, use the provided tools.
3. If a tool fails, find another way or politely explain what happened.
4. Think 2 steps ahead. Be proactive.

TERMINATION:
- When you are finished with a task or answering a question, simply respond with your message. You do not need to prefix with DONE anymore.
- Only use tools when explicitly needed to complete a task. Otherwise, just reply to Mark.
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
            
            await status_callback(f"🧠 Step {i+1}/{max_steps}: Thinking...")
            
            # If this is the first step of this specific run, add the user's new goal
            if i == 0:
                current_messages.append({"role": "user", "content": goal})
            
            # Get AI Response
            ai_message = await self.ai.chat(
                messages=current_messages,
                tools=TOOLS,
                role=active_agent.lower()
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
            
            # --- TOOL REQUIREMENT & LOOP AVOIDANCE ---
            # If the AI responded with a message and NO tool calls, we consider the turn complete.
            if not tool_calls:
                # Remove thinking blocks if present (from DeepSeek R1 models)
                import re
                clean_content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                # Remove legacy DONE tags just in case
                clean_content = re.sub(r"DONE:", "", clean_content, flags=re.IGNORECASE).strip()
                
                # If we have actual content, return it.
                if clean_content:
                    return clean_content, history
                    
                # If content is empty but it was step > 0, we might have finished
                if i > 0:
                    return "Task complete.", history

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
            history.append(msg_dict)

            # Check for Completion (Legacy check, just in case)
            if "DONE:" in content.upper():
                clean_content = re.sub(r'DONE:', '', content, flags=re.IGNORECASE).strip()
                clean_content = re.sub(r'<think>.*?</think>', '', clean_content, flags=re.DOTALL).strip()
                return (clean_content if clean_content else "Task complete."), history

            # Execute Tool Calls — strict ReAct: await each, feed result back
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.function.name

                    try:
                        args = json.loads(tc.function.arguments)
                        logger.info(f"Executing {tool_name} with {args}")

                        if tool_name in self.available_functions:
                            if status_callback:
                                await status_callback(f"🛠️ Step {i+1}/{max_steps}: Running {tool_name}...")
                            func = self.available_functions[tool_name]

                            # Validate URL if present
                            if "url" in args and not Guardrails.validate_url(args["url"]):
                                result = "BLOCKED: Malicious/Private URL detected."
                            else:
                                # Handle both sync and async functions correctly
                                if inspect.iscoroutinefunction(func):
                                    result = await func(**args)
                                else:
                                    result = func(**args)
                                    if asyncio.iscoroutine(result):
                                        result = await result
                        else:
                            result = f"Error: Tool '{tool_name}' not registered."

                    except Exception as e:
                        logger.error(f"Tool execution error [{tool_name}]: {e}")
                        result = f"Error executing tool {tool_name}: {e}"

                    # Feed result back to Brain — normalize to string
                    if isinstance(result, dict) and ("text" in result or "result" in result):
                        result_content = result.get("text") or result.get("result")
                    elif isinstance(result, dict):
                        result_content = json.dumps(result, default=str)
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
