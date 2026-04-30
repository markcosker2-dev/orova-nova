# -*- coding: utf-8 -*-
"""
Daily Reporter
Compiles lead stats and errors into a Telegram report.
"""
import asyncio
from pathlib import Path
from loguru import logger
from app.skills.sheet_ops import SheetManager
from app.skills.notifier import send_alert

class DailyReporter:
    @staticmethod
    async def send_report():
        """
        Generate and send the daily report.
        """
        logger.info("Generating Daily Report...")

        # 1. Count New Leads (last 24h)
        lead_count = SheetManager.count_recent_leads(hours=24)

        # 2. Scan bot_activity.log for errors and scheduler events
        error_count = 0
        scheduler_events = []
        log_file = Path("bot_activity.log")
        if not log_file.exists():
             # Try parent
             log_file = Path("../bot_activity.log")

        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                    # Read all lines (could be optimized for large files)
                    lines = f.readlines()

                    # Optional: limit to last 2000 lines to avoid processing ancient history
                    recent_lines = lines[-2000:] if len(lines) > 2000 else lines

                    for line in recent_lines:
                        if "ERROR" in line or "CRITICAL" in line:
                            error_count += 1

                        if "[SCHEDULER]" in line and "DAILY HUNT" in line:
                            scheduler_events.append(line.strip())

            except Exception as e:
                logger.error(f"Failed to read log file: {e}")

        # Determine Scheduler Status from events
        sched_status = "❓ No recent activity detected"
        if scheduler_events:
            # Get the last event
            last_event = scheduler_events[-1]
            if "COMPLETED" in last_event:
                 sched_status = "✅ Daily Hunt Completed"
            elif "FAILED" in last_event:
                 sched_status = "❌ Daily Hunt Failed"
            elif "STARTED" in last_event:
                 sched_status = "⏳ Daily Hunt In Progress"
            else:
                 sched_status = "ℹ️ Active"

        # 3. Format Message
        report = (
            f"📊 *OROVA Daily Operations Report*\n\n"
            f"🚀 *Leads Generated (24h):* {lead_count}\n"
            f"⚠️ *System Errors:* {error_count}\n"
            f"📅 *Scheduler Heartbeat:* {sched_status}\n\n"
            f"STATUS: {'✅ Nominal' if error_count == 0 else '⚠️ Attention Needed'}"
        )

        # 4. Send via Telegram
        success = await send_alert(report)
        if success:
            logger.success("Daily Report Sent via Telegram")
        else:
            logger.error("Failed to send Daily Report")

if __name__ == "__main__":
    asyncio.run(DailyReporter.send_report())
