# -*- coding: utf-8 -*-
"""
OROVA Nova CEO Brain
Autonomous Pipeline Health Checks, Morning Briefs, and Task Scheduling
"""

import os
import logging
import json
import datetime
from datetime import timedelta
import asyncio

from app.core.database import DatabaseManager
from app.core.ai_client import UnifiedAIClient
from app.skills.calendar_skill import get_today
from app.skills.agentmail_skill import _send_telegram_alert, check_replies

logger = logging.getLogger(__name__)


# In-memory store for pending auto-execute proposals (survives within a process)
_pending_proposals: dict = {}  # task_id -> {"tasks": [...], "created_at": datetime, "timer": asyncio.Task}
_AUTO_EXECUTE_TIMEOUT = 1800  # 30 minutes in seconds


class CEOBrain:
    def __init__(self):
        self.ai = UnifiedAIClient()

    async def get_status(self, client_id: int = 0) -> str:
        """Quick Telegram status summary. Run when user sends /status."""
        metrics = DatabaseManager.get_metrics(client_id)

        # Pull best strategy from learned_strategies
        best_framework = "BAB"
        best_hour = "10:00"
        best_niche = "None yet"
        try:
            fw_row = await DatabaseManager.fetchone(
                "SELECT strategy_value, win_rate FROM learned_strategies WHERE strategy_type='email_framework' AND client_id=? AND active=1 ORDER BY win_rate DESC LIMIT 1",
                (client_id,)
            )
            if fw_row:
                best_framework = f"{fw_row['strategy_value']} ({fw_row['win_rate']*100:.1f}%)"
        except Exception:
            pass
        try:
            tim_row = await DatabaseManager.fetchone(
                "SELECT strategy_value FROM learned_strategies WHERE strategy_type='send_timing' AND client_id=? AND active=1 ORDER BY win_rate DESC LIMIT 1",
                (client_id,)
            )
            if tim_row:
                best_hour = tim_row['strategy_value']
        except Exception:
            pass
        try:
            niche_row = await DatabaseManager.fetchone(
                "SELECT strategy_value, win_rate FROM learned_strategies WHERE strategy_type='niche' AND client_id=? AND active=1 ORDER BY win_rate DESC LIMIT 1",
                (client_id,)
            )
            if niche_row:
                best_niche = f"{niche_row['strategy_value']} ({niche_row['win_rate']*100:.1f}%)"
        except Exception:
            pass

        return (
            f"📊 **Nova Status**\n"
            f"Framework: {best_framework} ← Learned\n"
            f"Send time: {best_hour} ← Default (no data yet) if no row\n"
            f"Best niche: {best_niche}\n"
            f"Leads today: {metrics.get('leads_found', 0)}\n"
            f"Emails sent today: {metrics.get('emails_sent', 0)}\n"
            f"Replies: {metrics.get('replies_received', 0)}\n"
            f"Meetings: {metrics.get('meetings_booked', 0)}\n"
        )

    async def morning_brief(self, client_id: int = 0) -> str:
        """
        Runs daily to generate a comprehensive morning briefing.
        Pulls pipeline health metrics, rolling averages, HOT replies,
        and proposes the day's schedule. Sends report to Telegram.
        """
        logger.info("[CEO_BRAIN] Generating morning briefing...")
        
        # 1. Gather Metrics
        metrics = DatabaseManager.get_metrics(client_id)
        
        # Detect fresh start (no data at all) and short-circuit with friendly first-boot message
        is_fresh = (
            metrics.get('leads_found', 0) == 0
            and metrics.get('emails_sent', 0) == 0
            and metrics.get('replies_received', 0) == 0
        )
        if is_fresh:
            logger.info("[CEO_BRAIN] No pipeline data yet — first boot message.")
            first_boot_msg = (
                "☀️ **Nova First Boot**\n\n"
                "No pipeline data yet — I'm seeding with industry baselines.\n\n"
                "📋 **What's ready:**\n"
                "• Email Proofreader: ACTIVE (every email is checked)\n"
                "• CEO Brain: ACTIVE (morning brief at 5 PM PST)\n"
                "• Self-Improvement: ACTIVE (learns from outcomes)\n\n"
                "🎯 **Start recommendation:**\n"
                "Framework: **BAB** (Before-After-Bridge) — 22% avg reply rate (industry benchmark).\n"
                "Send time: **10:00 AM** — I'll track your best hours as you send emails.\n\n"
                "I'll start tracking once you send your first outreach. 🚀"
            )
            _send_telegram_alert(first_boot_msg)
            return first_boot_msg
        
        # 2. Query 7-day averages
        yesterday_sends = 0
        avg_7day_sends = 0.0
        yesterday_replies = 0
        avg_7day_replies = 0.0
        
        try:
            # Sends
            yesterday_sends_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) as cnt FROM outreach_outcomes WHERE action='email_sent' AND datetime(created_at) >= datetime('now', '-1 day')"
            )
            yesterday_sends = yesterday_sends_row["cnt"] if yesterday_sends_row else 0
            
            sends_7day_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) as cnt FROM outreach_outcomes WHERE action='email_sent' AND datetime(created_at) >= datetime('now', '-7 days')"
            )
            avg_7day_sends = (sends_7day_row["cnt"] / 7.0) if sends_7day_row else 0.0

            # Replies
            yesterday_replies_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) as cnt FROM outreach_outcomes WHERE action='email_reply' AND datetime(created_at) >= datetime('now', '-1 day')"
            )
            yesterday_replies = yesterday_replies_row["cnt"] if yesterday_replies_row else 0
            
            replies_7day_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) as cnt FROM outreach_outcomes WHERE action='email_reply' AND datetime(created_at) >= datetime('now', '-7 days')"
            )
            avg_7day_replies = (replies_7day_row["cnt"] / 7.0) if replies_7day_row else 0.0
        except Exception as e:
            logger.error(f"[CEO_BRAIN] Error compiling stats: {e}")

        # 3. Check for HOT Replies
        hot_replies_text = "None"
        try:
            inbox_res = check_replies(limit=5)
            if inbox_res.get("status") == "success" and inbox_res.get("messages"):
                # We can check recent emails or DB status
                hot_list = []
                for msg in inbox_res["messages"]:
                    snippet = msg.get("snippet", "")
                    # Simple heuristic or check category
                    if any(k in snippet.lower() for k in ["interested", "call", "meeting", "price", "how much", "yes"]):
                        hot_list.append(f"• {msg.get('from')}: \"{snippet[:100]}...\"")
                if hot_list:
                    hot_replies_text = "\n".join(hot_list)
        except Exception as e:
            logger.error(f"[CEO_BRAIN] Error checking HOT replies: {e}")

        # 4. Propose Tasks and Schedule
        proposed_tasks = await self.propose_tasks(metrics, client_id)
        schedule_text = await self.auto_schedule_day()

        # 5. Generate AI Executive Summary
        prompt = f"""
        You are the OROVA CEO Brain. Write a concise, premium daily executive summary based on the following stats:
        
        PIPELINE METRICS:
        - Total Leads Found: {metrics.get('leads_found')}
        - Emails Sent: {metrics.get('emails_sent')}
        - Replies Received: {metrics.get('replies_received')}
        - Meetings Booked: {metrics.get('meetings_booked')}
        - Calls Made: {metrics.get('calls_made')}
        
        PERFORMANCE COMPARISON (Yesterday vs. 7-Day Average):
        - Yesterday sends: {yesterday_sends} (7-Day Avg: {avg_7day_sends:.1f})
        - Yesterday replies: {yesterday_replies} (7-Day Avg: {avg_7day_replies:.1f})
        
        HOT REPLIES NEEDING ATTENTION:
        {hot_replies_text}
        
        PROPOSED SCHEDULE:
        {schedule_text}
        
        Format it in a clear, professional style suitable for a high-end CEO briefing on Telegram. Make it punchy and highlight any critical actions.
        """
        
        try:
            summary = await self.ai.write(prompt)
        except Exception as e:
            summary = f"Good morning! Here is your quick pipeline update. Total leads: {metrics.get('leads_found')}, sent: {metrics.get('emails_sent')}."

        # 6. Format Final Telegram Report
        report = (
            f"☀️ **Nova CEO Daily Briefing**\n\n"
            f"{summary.strip()}\n\n"
            f"⚡ **Proposed Daily Tasks:**\n"
        )
        for task in proposed_tasks:
            report += f"- {task['description']} (Priority: {task['priority']})\n"
            
        report += f"\n📅 **Today's Schedule:**\n{schedule_text}"
        
        _send_telegram_alert(report)

        # ── Auto-execute: schedule tasks to run in 30 min if no override ──
        await self._schedule_auto_execute(proposed_tasks, client_id)

        return report

    async def pipeline_health_check(self, client_id: int = 0) -> dict:
        """
        Runs periodically (every 2 hours) to check the health of the pipeline.
        Returns a health score (0-100) and action items if issues are detected.
        """
        logger.info("[CEO_BRAIN] Running pipeline health check...")
        
        # 1. Gather Metrics
        metrics = DatabaseManager.get_metrics(client_id)
        
        # 2. Check lead flow rate
        health_score = 100
        alerts = []
        
        # Check if we have leads
        if metrics.get("leads_found", 0) < 10:
            health_score -= 30
            alerts.append("Lead inventory is low (less than 10 leads in DB).")
            
        # Check if email rate is zero
        yesterday_sends_row = await DatabaseManager.fetchone(
            "SELECT COUNT(*) as cnt FROM outreach_outcomes WHERE action='email_sent' AND datetime(created_at) >= datetime('now', '-1 day')"
        )
        yesterday_sends = yesterday_sends_row["cnt"] if yesterday_sends_row else 0
        if yesterday_sends == 0:
            health_score -= 20
            alerts.append("No outreach emails sent in the last 24 hours.")
            
        # Check for reply rate drops
        if metrics.get("emails_sent", 0) > 20 and metrics.get("replies_received", 0) == 0:
            health_score -= 15
            alerts.append("Outreach campaigns sent but zero replies logged.")
            
        # 3. Check for stale leads
        stale_leads_row = await DatabaseManager.fetchone(
            "SELECT COUNT(*) as cnt FROM leads WHERE status IN ('Email Sent', 'Contacted') AND datetime(updated_at) < datetime('now', '-2 days')"
        )
        stale_count = stale_leads_row["cnt"] if stale_leads_row else 0
        if stale_count > 5:
            alerts.append(f"{stale_count} leads are stale (no updates in 48h+). Escalation recommended.")
            health_score -= 10
            
        health_score = max(0, health_score)
        
        # If health score drops below 70, alert CEO
        if health_score < 70:
            alert_msg = (
                f"⚠️ **Orova Pipeline Health Warning**\n\n"
                f"Health Score: **{health_score}/100**\n"
                f"Alerts:\n" + "\n".join(f"• {a}" for a in alerts) + "\n\n"
                f"Nova is auto-scheduling corrective tasks."
            )
            _send_telegram_alert(alert_msg)
            
        # If health score drops below 70, auto-execute corrective tasks
        if health_score < 70:
            corrective_tasks = await self.propose_tasks(metrics, client_id)
            if corrective_tasks:
                await self._schedule_auto_execute(corrective_tasks, client_id, source="health_alert")

        return {
            "health_score": health_score,
            "alerts": alerts,
            "checked_at": datetime.datetime.now().isoformat()
        }

    async def propose_tasks(self, metrics: dict, client_id: int = 0) -> list:
        """Proposes specific tasks based on current metrics."""
        tasks = []
        
        # Check leads count
        if metrics.get("leads_found", 0) < 20:
            tasks.append({
                "description": "Run lead hunter for new vertical (e.g. custom home builders)",
                "priority": "HIGH",
                "action": "hunt"
            })
            
        # Check replies
        hot_row = await DatabaseManager.fetchone(
            "SELECT COUNT(*) as cnt FROM leads WHERE status = 'Replied'"
        )
        hot_count = hot_row["cnt"] if hot_row else 0
        if hot_count > 0:
            tasks.append({
                "description": f"Draft custom responses for {hot_count} hot replied leads",
                "priority": "URGENT",
                "action": "reply"
            })
            
        # Check drip sends
        pending_drips = await DatabaseManager.fetchone(
            "SELECT COUNT(*) as cnt FROM drip_campaigns WHERE status = 'active' AND (next_send_at IS NULL OR datetime(next_send_at) <= datetime('now'))"
        )
        pending_count = pending_drips["cnt"] if pending_drips else 0
        if pending_count > 0:
            tasks.append({
                "description": f"Execute {pending_count} pending drip sequence follow-ups",
                "priority": "HIGH",
                "action": "drip"
            })
            
        # Fallback default task
        if not tasks:
            tasks.append({
                "description": "Run daily lead enrichment and warm follow-ups",
                "priority": "MEDIUM",
                "action": "routine"
            })
            
        return tasks

    async def auto_schedule_day(self) -> str:
        """
        Queries today's calendar and returns a formatted daily schedule proposal.
        Prioritizes tasks: HOT replies > drip sequence sends > hunting.
        """
        # Retrieve calendar events with graceful fallback if OAuth is not configured
        try:
            cal = get_today()
            cal_events = cal.get("events", []) if cal.get("success") else []
        except Exception as e:
            logger.warning(f"[CEO_BRAIN] Calendar access failed: {e}. Using default schedule.")
            cal_events = []
        
        # Build schedule text
        schedule_lines = []
        
        # Let's outline the slots
        # California Time business hours
        slots = [
            ("09:00 - 10:00", "Review Inbox & Draft Suggested Replies (HOT)"),
            ("10:00 - 11:30", "Execute Pending Drip Outreach & Proofread"),
            ("13:00 - 14:30", "Pipeline Health Check & Lead Hunting"),
            ("16:00 - 17:00", "Daily Summary, Google Sheets CRM Sync, & Backup")
        ]
        
        for time_slot, default_task in slots:
            # Check if there is a calendar conflict
            conflict = None
            for event in cal_events:
                # Basic overlap check (in real app we'd parse time, but simple check works)
                if event.get("summary") and ("call" in event["summary"].lower() or "meeting" in event["summary"].lower()):
                    conflict = event["summary"]
                    break
            if conflict:
                schedule_lines.append(f"• {time_slot}: ⚠️ Conflict with Calendar: **{conflict}**")
            else:
                schedule_lines.append(f"• {time_slot}: {default_task}")
                
        return "\n".join(schedule_lines)

    async def _schedule_auto_execute(self, tasks: list, client_id: int = 0, source: str = "morning_brief"):
        """Schedule tasks to auto-execute in 30 minutes unless cancelled."""
        import uuid as _uuid
        task_id = str(_uuid.uuid4())[:8]

        # Check for existing override
        try:
            override = await DatabaseManager.get_state("override_auto_execute")
            if override:
                logger.info("[CEO_BRAIN] Auto-execute overridden by user. Skipping.")
                return
        except Exception:
            pass

        # Store proposal
        _pending_proposals[task_id] = {
            "tasks": tasks,
            "client_id": client_id,
            "created_at": datetime.datetime.now(),
            "source": source,
        }

        # Schedule auto-execution after 30 minutes
        async def _auto_execute_callback():
            await asyncio.sleep(_AUTO_EXECUTE_TIMEOUT)
            proposal = _pending_proposals.pop(task_id, None)
            if not proposal:
                return  # was cancelled or already executed
            logger.info(f"[CEO_BRAIN] Auto-executing {len(proposal['tasks'])} tasks (no override received)")
            await self._execute_tasks(proposal["tasks"], proposal["client_id"])
            _send_telegram_alert(
                f"🤖 **Auto-Executed** {len(proposal['tasks'])} tasks (source: {proposal['source']})\n"
                f"Tasks:\n" + "\n".join(f"• {t['description']} [{t['priority']}]" for t in proposal["tasks"])
            )

        timer = asyncio.create_task(_auto_execute_callback())
        _pending_proposals[task_id]["timer"] = timer

        _send_telegram_alert(
            f"⏰ **Schedule Proposal** (auto-execute in 30 min if no override)\n\n"
            + "\n".join(f"• {t['description']} [{t['priority']}]" for t in tasks)
            + "\n\n Reply with `/cancel {task_id}` to stop auto-execution."
        )
        logger.info(f"[CEO_BRAIN] Proposal {task_id} scheduled. Auto-execute in 30 min unless cancelled.")

    async def cancel_auto_execute(self, task_id: str) -> bool:
        """Cancel a pending auto-execute proposal. Returns True if cancelled."""
        proposal = _pending_proposals.pop(task_id, None)
        if proposal:
            timer = proposal.get("timer")
            if timer and not timer.done():
                timer.cancel()
            _send_telegram_alert(f"✅ Auto-execute cancelled for proposal `{task_id}`.")
            return True
        return False

    async def _execute_tasks(self, tasks: list, client_id: int = 0):
        """Execute a list of proposed tasks. This is the action layer."""
        for task in tasks:
            action = task.get("action", "")
            try:
                if action == "hunt":
                    logger.info(f"[CEO_BRAIN] Executing hunt task: {task['description']}")
                    # Trigger a lead hunt via the planner
                    from app.core.planner import run_planner
                    await run_planner(task["description"], client_id=client_id)
                elif action == "drip":
                    logger.info(f"[CEO_BRAIN] Executing drip task: {task['description']}")
                    from app.skills.email_sequence_skill import drip_send_pending
                    await drip_send_pending(client_id=client_id)
                elif action == "routine":
                    logger.info(f"[CEO_BRAIN] Executing routine task: {task['description']}")
                    # Default: run enrichment on existing leads
                    from app.skills.smart_scraper import enrich_lead_ai
                    # Enrich up to 5 leads
                    from app.core.database import DatabaseManager
                    leads = await DatabaseManager.fetchall(
                        "SELECT * FROM leads WHERE client_id=? AND orova_score IS NULL LIMIT 5",
                        (client_id,)
                    )
                    for lead in leads:
                        await enrich_lead_ai(lead)
                else:
                    logger.info(f"[CEO_BRAIN] Unknown action '{action}', skipping task: {task['description']}")
            except Exception as e:
                logger.error(f"[CEO_BRAIN] Failed to execute task '{action}': {e}")
