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
from app.skills.smart_scraper import sgai_search_and_extract, sgai_deep_extract
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
        self.available_functions = {
            "sgai_search_and_extract": sgai_search_and_extract,
            "sgai_deep_extract": sgai_deep_extract,
            "find_leads": find_leads,
            "browse_agent": browse_and_extract,
            "google_search": google_search_scrape,
            "deep_research": deep_research,
            "research_lead": research_lead,
            "analyze_competitor": analyze_competitor,
            "compare_competitors": compare_competitors,
            "write_content": write_content,
            "optimize_post": optimize_post,
            "get_inbox": get_inbox,
            "search_emails": search_emails,
            "send_email": send_email,
            "get_today": get_today,
            "get_week": get_week,
            "get_office_hour_slots": get_office_hour_slots,
            "create_event": create_event,
            "update_event": update_event,
            "delete_event": delete_event,
            "get_orova_prompt": get_orova_prompt,
            "advanced_browser": advanced_browser,
            "append_to_sheet": append_to_sheet,
            "create_new_sheet": create_new_sheet,
            "request_approval": request_approval,
            "list_pending": list_pending,
            "create_inbox": create_inbox,
            "send_outreach": send_outreach,
            "check_replies": check_replies,
            "reply_to_email": reply_to_email,
            "summarize_and_categorize_inbox": summarize_and_categorize_inbox,
            "create_instagram_post": create_instagram_post,
            "create_content_calendar": create_content_calendar,
            "trigger_retell_call": trigger_retell_call,
            "generate_ai_image": generate_ai_image,
            "run_seo_audit": seo_audit,
            "generate_sequence": generate_sequence,
            "generate_proposal": generate_proposal,
            "weekly_report": generate_weekly_report,
            "track_metric": track_metric,
            "dispatch_task": dispatch_task,
            "stealth_search": stealth_search,
            "stealth_extract": stealth_extract,
            "bulk_scrape": bulk_scrape,
            "create_drip_campaign": create_drip_campaign,
            "write_cold_email": write_cold_email,
            "write_ad_copy": write_ad_copy,
            "pipeline_report": pipeline_report,
            "conversion_analysis": conversion_analysis,
            "roi_calculator": roi_calculator,
            "run_pipeline": run_pipeline,
            "list_pipelines": list_pipelines,
        }

    def _get_persona_prompt(self, agent_id: str) -> str:
        persona_path = Path(__file__).parent.parent / "personas" / f"{agent_id}.md"
        if persona_path.exists():
            try:
                content = persona_path.read_text(encoding='utf-8')
                return f"\n=== ELITE AGENT IDENTITY: {agent_id.upper()} ===\n{content}\n"
            except Exception as e:
                logger.warning(f"Failed to load persona for {agent_id}: {e}")
        return ""

    def _scope_tools(self, goal: str) -> list:
        """Only pass RELEVANT tools to the AI based on the task category.
        This prevents context window overload on lightweight models."""
        goal_lower = goal.lower()

        # Tool name sets by category
        HUNTING_TOOLS = ["sgai_search_and_extract", "sgai_deep_extract", "find_leads", "google_search", "research_lead", "stealth_search", "stealth_extract"]
        OUTREACH_TOOLS = ["send_outreach", "write_cold_email", "create_drip_campaign", "generate_sequence", "check_replies"]
        CONTENT_TOOLS = ["write_content", "optimize_post", "create_instagram_post", "generate_ai_image", "write_ad_copy"]
        ANALYTICS_TOOLS = ["pipeline_report", "conversion_analysis", "roi_calculator", "weekly_report", "track_metric"]
        CALENDAR_TOOLS = ["get_today", "get_week", "create_event"]

        # Classify intent
        if any(k in goal_lower for k in ["find", "search", "lead", "hunt", "client", "prospect", "scrape", "look"]):
            scope = HUNTING_TOOLS
        elif any(k in goal_lower for k in ["email", "outreach", "send", "cold", "drip", "sequence", "reply"]):
            scope = OUTREACH_TOOLS
        elif any(k in goal_lower for k in ["content", "post", "instagram", "image", "creative", "ad copy", "write"]):
            scope = CONTENT_TOOLS
        elif any(k in goal_lower for k in ["report", "analytics", "roi", "metric", "performance", "dashboard"]):
            scope = ANALYTICS_TOOLS
        elif any(k in goal_lower for k in ["calendar", "schedule", "meeting", "event"]):
            scope = CALENDAR_TOOLS
        else:
            # General mode: give a small general set
            scope = HUNTING_TOOLS + ["dispatch_task", "weekly_report"]

        # Filter TOOLS to only include scoped ones
        scoped = [t for t in TOOLS if t["function"]["name"] in scope]
        logger.info(f"🎯 Tool Scope: {len(scoped)} tools for intent: {scope[:3]}...")
        return scoped if scoped else TOOLS[:8]  # Safety fallback

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova"):
        history = conversation_history if conversation_history else []
        max_steps = 10
        
        from app.core.memory import MemoryDistiller
        if not hasattr(self, 'distiller'):
            self.distiller = MemoryDistiller(self.ai)
        history = await self.distiller.distill(history, client_id)
        long_term_facts = await self.distiller.retrieve_context(goal, client_id)
        
        from app.core.database import DatabaseManager
        config = await DatabaseManager.get_client_config(client_id)
        current_niche = config.get("niche", "General Business")
        current_loc = config.get("location", "California")
        
        # Nova stays as Nova for direct user messages.
        # Sub-agents are only used when explicitly dispatched.
        active_agent = agent_id
        persona_instructions = self._get_persona_prompt(active_agent)
        
        # Scope tools to reduce context pressure
        scoped_tools = self._scope_tools(goal)

        system_prompt = f"""YOU ARE NOVA. Mark's AI Partner at OROVA.
{persona_instructions}
TARGET: {current_niche} in {current_loc}.

RULES:
1. You MUST call a tool function to get data. Do NOT make up business names.
2. Use 'find_leads' or 'google_search' to search. Use 'research_lead' to deep-dive a URL.
3. After getting tool results, present them clearly with DONE: prefix when finished.
4. Be concise. No essays. Results only.
{long_term_facts}"""

        # ── DIRECT ACTION SHORTCUT ──────────────────────────────────
        # For hunting tasks, skip the unreliable AI tool-calling and
        # call find_leads directly. Then ask AI to format results.
        goal_lower = goal.lower()
        is_hunt = any(k in goal_lower for k in ["find", "search", "look", "client", "lead", "hunt", "prospect"])
        
        if is_hunt:
            logger.info("🎯 DIRECT ACTION: Hunting task detected.")
            search_query = goal
            
            try:
                import os
                # Use ScrapeGraphAI if available
                if os.getenv("SGAI_API_KEY"):
                    logger.info("🎯 Using ScrapeGraphAI for Direct Action...")
                    from app.skills.smart_scraper import sgai_search_and_extract
                    res = await sgai_search_and_extract(query=search_query, count=3)
                    
                    if res.get("status") == "success":
                        data = res.get("data", {})
                        # Ask AI to present the JSON cleanly
                        format_messages = [
                            {"role": "system", "content": "You are Nova, Mark's AI partner. Present this structured lead data cleanly to Mark. Emphasize the 'Verified_Mobile' and 'owner_name' if found."},
                            {"role": "user", "content": f"Here is the ScrapeGraphAI structured extraction for '{goal}':\n\n{str(data)[:3000]}\n\nPresent these to Mark as a professional brief."}
                        ]
                        ai_response = await self.ai.chat(messages=format_messages, role=active_agent)
                        return ai_response.content or "Successfully extracted leads with ScrapeGraphAI."
                    else:
                        logger.warning(f"SGAI failed: {res.get('error')}. Falling back to DDG.")
                
                # Fallback to free DDG lead finder
                logger.info("🎯 Falling back to standard find_leads...")
                from app.skills.lead_finder import find_leads
                raw_results = await find_leads(query=search_query, count=5)
                
                if isinstance(raw_results, dict):
                    lead_text = raw_results.get("text", str(raw_results))
                else:
                    lead_text = str(raw_results)
                
                if lead_text and "non-actionable" not in lead_text.lower():
                    # Ask AI to present results nicely
                    format_messages = [
                        {"role": "system", "content": "You are Nova, Mark's AI partner at OROVA. Present these search results clearly and concisely. Add a brief recommendation for each lead."},
                        {"role": "user", "content": f"Here are the raw search results for '{goal}':\n\n{lead_text[:2500]}\n\nPresent these to Mark with your recommendations."}
                    ]
                    ai_response = await self.ai.chat(messages=format_messages, role=active_agent)
                    return ai_response.content or lead_text
                else:
                    return lead_text or "No actionable leads found. Try a more specific query."
            except Exception as e:
                logger.error(f"💥 Direct hunt failed: {e}")
                return f"⚠️ Search tool error: {str(e)}. Try again in a moment."

        # ── STANDARD AI LOOP (for non-hunting tasks) ───────────────
        for i in range(max_steps):
            logger.info(f"Planner Step {i+1}/{max_steps}")
            current_messages = [{"role": "system", "content": system_prompt}] + history
            if i == 0:
                current_messages.append({"role": "user", "content": goal})
            
            ai_message = await self.ai.chat(messages=current_messages, tools=scoped_tools, role=active_agent)
            
            # --- ANTI-SILENCE PROTOCOL ---
            if not ai_message.content and not ai_message.tool_calls:
                if i < 3:
                    logger.warning(f"⚠️ Empty response on step {i+1}. Nudging...")
                    history.append({"role": "user", "content": "You returned empty. Call 'find_leads' with a search query NOW."})
                    continue
                else:
                    return "⚠️ Nova is having trouble processing. Try a simpler request like: 'find leads remodeling Los Angeles'"

            content = ai_message.content or ""
            tool_calls = ai_message.tool_calls

            # --- TRUTH GUARDRAIL ---
            if not tool_calls and "DONE:" not in content.upper() and i == 0:
                has_list = any(k in content for k in ["1.", "2.", "3."])
                is_hunt = any(k in goal.lower() for k in ["find", "search", "look", "client", "lead", "hunt"])
                if has_list and is_hunt:
                    logger.warning("🚨 HALLUCINATION: Leads without tool call. Rejecting.")
                    history.append({"role": "assistant", "content": content})
                    history.append({"role": "user", "content": "REJECTED. Call 'find_leads' tool NOW. Do not type lead names."})
                    continue
                if not is_hunt:
                    return content if content.strip() else "Ready, Mark."

            # Append to history
            msg_dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} 
                    for tc in tool_calls
                ]
            history.append(msg_dict)

            if "DONE:" in content.upper():
                return re.sub(r'DONE:', '', content, flags=re.IGNORECASE).strip() or "Task complete, Mark."

            # Execute Tool Calls
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                        logger.info(f"🔧 Executing: {tool_name}({args})")
                        if tool_name in self.available_functions:
                            result = await self.available_functions[tool_name](**args)
                        else:
                            result = f"Error: Tool '{tool_name}' not registered."
                    except Exception as e:
                        logger.error(f"💥 Tool failed: {e}")
                        result = f"ERROR: {str(e)}"
                    
                    result_str = str(result)[:3000]  # Cap tool output to prevent token overflow
                    history.append({"role": "tool", "tool_call_id": tc.id, "name": tool_name, "content": result_str})
            elif not content:
                return "⚠️ AI returned an empty response. Try: 'find leads remodeling LA'"

        return f"⚠️ Max steps reached. Last: {content[:200]}"

