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
        self.available_functions = {
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

    async def execute(self, goal: str, client_id: int = 0, conversation_history: list = None, agent_id: str = "nova"):
        history = conversation_history if conversation_history else []
        max_steps = 20
        
        from app.core.memory import MemoryDistiller
        if not hasattr(self, 'distiller'):
            self.distiller = MemoryDistiller(self.ai)
        history = await self.distiller.distill(history, client_id)
        long_term_facts = await self.distiller.retrieve_context(goal, client_id)
        
        from app.core.database import DatabaseManager
        config = await DatabaseManager.get_client_config(client_id)
        current_niche = config.get("niche", "General Business")
        current_loc = config.get("location", "California")
        
        from app.core.agent_router import classify_agent
        active_agent = agent_id if agent_id != "nova" else classify_agent(goal)
        persona_instructions = self._get_persona_prompt(active_agent)
        
        system_prompt = f"""
YOU ARE NOVA. Autonomous CEO of OROVA. Mark's AI Partner.
{persona_instructions}

=== HORMOZI CEO PROTOCOLS ===
1. TOOL FIRST: You are strictly FORBIDDEN from presenting leads or data unless you have CALLED a tool in the CURRENT turn.
2. NO FAKING: If you say "TOOL CALL: [name]" in text but don't call the function, the system will REJECT you.
3. DATA INTEGRITY: NEVER hallucinate business names. Use 'google_search' or 'find_leads'.
4. OBJECTIVE: Find {current_niche} leads in {current_loc} for Meta Lead Gen ($4k-$5k/mo).
"""

        BANNED_PHRASES = ["tools are dead", "apis are down", "system failure", "will retry later"]
        ban_retries = 0

        for i in range(max_steps):
            logger.info(f"Planner Step {i+1}/{max_steps}")
            current_messages = [{"role": "system", "content": system_prompt}] + history
            if i == 0:
                current_messages.append({"role": "user", "content": goal})
            
            ai_message = await self.ai.chat(messages=current_messages, tools=TOOLS, role=active_agent)
            
            # --- ANTI-SILENCE PROTOCOL ---
            if not ai_message.content and not ai_message.tool_calls:
                logger.warning("⚠️ AI returned empty. Nudging...")
                history.append({"role": "user", "content": "I didn't receive your response. Please call a tool or provide a status update NOW."})
                continue

            content = ai_message.content or ""
            tool_calls = ai_message.tool_calls

            # --- TRUTH GUARDRAIL ---
            if not tool_calls and "DONE:" not in content.upper():
                fake_leads = any(k in content.lower() for k in ["1.", "2.", "3.", "lead:", "company:"])
                if fake_leads:
                    logger.warning("🚨 HALLUCINATION DETECTED. Rejecting.")
                    history.append({"role": "assistant", "content": content})
                    history.append({"role": "user", "content": "REJECTED. You provided leads without a tool call. Call 'google_search' NOW."})
                    continue

            if not tool_calls and i == 0:
                is_cmd = any(k in goal.lower() for k in ["find", "search", "scrape", "look"])
                if not is_cmd: return (content if content.strip() else "Ready.")

            # Append Assistant Reply
            msg_dict = {"role": "assistant", "content": content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} 
                    for tc in tool_calls
                ]
            history.append(msg_dict)

            if "DONE:" in content.upper():
                return re.sub(r'DONE:', '', content, flags=re.IGNORECASE).strip()

            # Execute Tool Calls
            if tool_calls:
                for tc in tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                        logger.info(f"Executing {tool_name} with {args}")
                        if tool_name in self.available_functions:
                            func = self.available_functions[tool_name]
                            result = await func(**args)
                        else:
                            result = f"Error: Tool '{tool_name}' not registered."
                    except Exception as e:
                        logger.error(f"💥 Tool failed: {e}")
                        result = f"ERROR: {str(e)}"
                    
                    history.append({"role": "tool", "tool_call_id": tc.id, "name": tool_name, "content": str(result)})
            elif not content:
                return "⚠️ AI returned an empty response."

        return f"⚠️ Max steps reached. Last status: {content[:100]}"
