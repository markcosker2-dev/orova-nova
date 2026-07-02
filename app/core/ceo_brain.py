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


async def _persist_proposal(task_id: str, proposal: dict):
    """Persist a proposal to state_store so it survives restarts. Raises on failure."""
    payload = {
        "tasks": proposal["tasks"],
        "client_id": proposal["client_id"],
        "source": proposal.get("source", "morning_brief"),
        "created_at": proposal["created_at"].isoformat(),
    }
    try:
        await DatabaseManager.query(
            "INSERT OR REPLACE INTO state_store (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (f"pending_proposal:{task_id}", json.dumps(payload)),
        )
    except Exception as e:
        logger.error(f"[CEO_BRAIN] Failed to persist proposal {task_id}: {e}")
        raise


async def _delete_persisted_proposal(task_id: str):
    """Remove a persisted proposal from state_store. Raises on failure."""
    try:
        await DatabaseManager.query(
            "DELETE FROM state_store WHERE key = ?",
            (f"pending_proposal:{task_id}",),
        )
    except Exception as e:
        logger.error(f"[CEO_BRAIN] Failed to delete persisted proposal {task_id}: {e}")
        raise


async def _mark_proposal_executed(task_id: str):
    """Mark a persisted proposal as executed so it won't be retried on restart."""
    try:
        await DatabaseManager.query(
            "UPDATE state_store SET value = ? WHERE key = ?",
            (json.dumps({"status": "executed"}), f"pending_proposal:{task_id}"),
        )
    except Exception as e:
        logger.error(f"[CEO_BRAIN] Failed to mark proposal {task_id} as executed: {e}")
        raise


async def _run_proposal(task_id: str, context: str, execute_fn):
    """Shared auto-execute logic: execute tasks, clean up, alert.

    After execute_fn succeeds the persisted record is marked as executed
    so a restart won't re-run already-completed work. Deletion is then
    best-effort — a failed delete just leaves a harmless "executed" row.
    """
    proposal = _pending_proposals.get(task_id)
    if not proposal:
        return
    logger.info(f"[CEO_BRAIN] Auto-executing {len(proposal['tasks'])} tasks ({context})")
    try:
        await execute_fn(proposal["tasks"], proposal["client_id"])
    except Exception as e:
        logger.error(f"[CEO_BRAIN] execute_fn failed for {task_id}: {e}")
        return  # keep proposal in memory + DB for retry
    # Execution succeeded — mark persisted record so restarts won't re-run it
    persisted_ok = False
    try:
        await _mark_proposal_executed(task_id)
        persisted_ok = True
    except Exception:
        logger.warning(f"[CEO_BRAIN] Failed to mark {task_id} as executed; attempting delete instead")
    # Best-effort cleanup of persisted record
    try:
        await _delete_persisted_proposal(task_id)
        persisted_ok = True
    except Exception:
        if not persisted_ok:
            # Last resort: write executed status directly so reload won't re-schedule
            try:
                await DatabaseManager.query(
                    "INSERT OR REPLACE INTO state_store (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (f"pending_proposal:{task_id}", json.dumps({"status": "executed"})),
                )
                logger.warning(f"[CEO_BRAIN] Mark-executed and delete both failed for {task_id}; wrote terminal status directly")
            except Exception as write_err:
                logger.error(f"[CEO_BRAIN] All persistence attempts failed for {task_id}: {write_err}")
                # No terminal checkpoint confirmed — keep in-memory entry so the
                # DB row (still non-executed) won't be re-scheduled on restart
                # while the timer is already dead. A future restart will retry.
                return
        else:
            logger.warning(f"[CEO_BRAIN] Persisted delete failed for {task_id}, but proposal is marked executed")
    # Terminal checkpoint confirmed — safe to remove from memory
    _pending_proposals.pop(task_id, None)
    await _send_telegram_alert(
        f"🤖 **Auto-Executed** {len(proposal['tasks'])} tasks (source: {proposal['source']})\n"
        f"Tasks:\n" + "\n".join(f"• {t['description']} [{t['priority']}]" for t in proposal["tasks"])
    )


async def _reload_pending_proposals() -> int:
    """Reload pending proposals from DB on startup and re-schedule timers."""
    restored = 0
    try:
        rows = await DatabaseManager.fetchall(
            "SELECT key, value FROM state_store WHERE key LIKE 'pending_proposal:%'"
        )
        if not rows:
            return restored
        brain = CEOBrain()
        for row in rows:
            task_id = row["key"].split(":", 1)[1]
            try:
                payload = json.loads(row["value"])
                # Skip proposals already executed (leftover from a failed delete)
                if isinstance(payload, dict) and payload.get("status") == "executed":
                    logger.info(f"[CEO_BRAIN] Skipping already-executed proposal {task_id}, cleaning up")
                    try:
                        await _delete_persisted_proposal(task_id)
                    except Exception as cleanup_err:
                        logger.warning(f"[CEO_BRAIN] Cleanup delete failed for executed proposal {task_id}: {cleanup_err}")
                    continue
                created_at = datetime.datetime.fromisoformat(payload["created_at"])
                elapsed = (datetime.datetime.now() - created_at).total_seconds()
                remaining = max(0, _AUTO_EXECUTE_TIMEOUT - elapsed)

                _pending_proposals[task_id] = {
                    "tasks": payload["tasks"],
                    "client_id": payload.get("client_id", 0),
                    "created_at": created_at,
                    "source": payload.get("source", "morning_brief"),
                }

                async def _make_callback(tid, delay):
                    await asyncio.sleep(delay)
                    await _run_proposal(tid, "restored proposal", brain._execute_tasks)

                timer = asyncio.create_task(_make_callback(task_id, remaining))
                _pending_proposals[task_id]["timer"] = timer
                logger.info(f"[CEO_BRAIN] Restored proposal {task_id} ({remaining:.0f}s remaining)")
                restored += 1
            except Exception as e:
                logger.error(f"[CEO_BRAIN] Failed to restore proposal {task_id}: {e}")
                await _delete_persisted_proposal(task_id)
    except Exception as e:
        logger.error(f"[CEO_BRAIN] Failed to reload pending proposals: {e}")
    return restored


class CEOBrain:
    def __init__(self):
        self.ai = UnifiedAIClient()

    async def get_status(self, client_id: int = 0) -> str:
        """Quick Telegram status summary. Run when user sends /status."""
        metrics = await DatabaseManager.aget_metrics(client_id)

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
        metrics = await DatabaseManager.aget_metrics(client_id)
        
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
            await _send_telegram_alert(first_boot_msg)
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
            inbox_res = await check_replies(limit=5, advance_checkpoint=False)
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

        # 3.5 Audit recent task failures recorded by the planner's outcome
        # verification, so the brief surfaces what went wrong — not just wins.
        failed_audits_text = "None"
        try:
            audit_rows = await DatabaseManager.fetchall(
                """SELECT content FROM memories
                   WHERE content LIKE 'TASK AUDIT FAIL%' AND client_id = ?
                     AND datetime(created_at) >= datetime('now', '-1 day')
                   ORDER BY created_at DESC LIMIT 5""",
                (client_id,)
            )
            if audit_rows:
                failed_audits_text = "\n".join(f"• {r['content'][:200]}" for r in audit_rows)
        except Exception as e:
            logger.debug(f"[CEO_BRAIN] Audit fetch skipped: {e}")

        # 4. Propose Tasks and Schedule
        proposed_tasks = await self.propose_tasks(metrics, client_id)
        schedule_text = await self.auto_schedule_day()

        # 5. Generate AI Executive Summary
        prompt = f"""
        You are the CEO Brain of OROVA — think like the operator of a $100M revenue machine reviewing a daily P&L, not an assistant writing a status update.

        Voice: direct, numbers-first, zero fluff. Every observation must end in a decision or an action. Call out what's broken before what's working. If a metric is trending down, say so bluntly and say what you're doing about it. Money and booked meetings are the only scoreboard — leads and emails are inputs, not wins.

        Structure your summary as:
        1. THE NUMBER THAT MATTERS TODAY (one line: closest thing to revenue)
        2. WHAT'S WORKING (max 2 bullets, with the metric that proves it)
        3. WHAT'S BROKEN (be blunt; include the fix you're executing)
        4. TODAY'S ONE BIG BET (the single highest-leverage action)

        Base it on the following stats:

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

        FAILED TASK AUDITS (last 24h — call these out with a fix suggestion):
        {failed_audits_text}

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
        
        await _send_telegram_alert(report)

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
        metrics = await DatabaseManager.aget_metrics(client_id)
        
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
            await _send_telegram_alert(alert_msg)
            
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
        try:
            await _persist_proposal(task_id, _pending_proposals[task_id])
        except Exception:
            # Persistence failed — remove in-memory entry and skip the proposal alert
            _pending_proposals.pop(task_id, None)
            logger.warning(f"[CEO_BRAIN] Proposal {task_id} not persisted; skipping auto-execute schedule")
            return

        # Schedule auto-execution after 30 minutes
        async def _auto_execute_callback():
            await asyncio.sleep(_AUTO_EXECUTE_TIMEOUT)
            await _run_proposal(task_id, "no override received", self._execute_tasks)

        timer = asyncio.create_task(_auto_execute_callback())
        _pending_proposals[task_id]["timer"] = timer

        await _send_telegram_alert(
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
            try:
                await _delete_persisted_proposal(task_id)
            except Exception:
                logger.warning(f"[CEO_BRAIN] Failed to delete persisted proposal {task_id} on cancel; in-memory entry already removed")
            await _send_telegram_alert(f"✅ Auto-execute cancelled for proposal `{task_id}`.")
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
