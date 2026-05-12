# -*- coding: utf-8 -*-
"""
Performance Dashboard Skill for OROVA (Sentinel Agent)
Generates weekly metrics reports for the CEO Pulse.
"""

import logging
import json
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS_FILE = Path(__file__).parent.parent / "metrics.json"


def _load_metrics() -> dict:
    """Load metrics from persistent storage."""
    if METRICS_FILE.exists():
        try:
            return json.loads(METRICS_FILE.read_text())
        except Exception:
            pass
    return {
        "leads_found": 0,
        "emails_sent": 0,
        "replies_received": 0,
        "meetings_booked": 0,
        "calls_made": 0,
        "proposals_sent": 0,
        "content_created": 0,
        "week_start": datetime.now().strftime("%Y-%m-%d"),
        "daily_log": [],
    }


def _save_metrics(metrics: dict):
    """Save metrics to persistent storage."""
    METRICS_FILE.write_text(json.dumps(metrics, indent=2))


def track_metric(metric_name: str, increment: int = 1) -> dict:
    """
    Increment a metric counter.

    Args:
        metric_name: One of leads_found, emails_sent, replies_received, 
                     meetings_booked, calls_made, proposals_sent, content_created
        increment: How much to add (default 1)
    """
    metrics = _load_metrics()

    if metric_name not in metrics:
        return {"success": False, "error": f"Unknown metric: {metric_name}"}

    metrics[metric_name] = metrics.get(metric_name, 0) + increment

    # Log daily
    today = datetime.now().strftime("%Y-%m-%d")
    metrics.setdefault("daily_log", [])
    metrics["daily_log"].append({
        "date": today,
        "metric": metric_name,
        "value": increment,
        "timestamp": datetime.now().isoformat(),
    })

    _save_metrics(metrics)
    logger.info(f"[SENTINEL] Tracked: {metric_name} +{increment}")
    return {"success": True, "metric": metric_name, "new_total": metrics[metric_name]}


def generate_weekly_report() -> str:
    """Generate a formatted weekly performance report for Telegram."""
    m = _load_metrics()
    today = datetime.now()

    # ── Pipeline Metrics ──
    reply_rate = (m["replies_received"] / max(m["emails_sent"], 1)) * 100
    book_rate = (m["meetings_booked"] / max(m["replies_received"], 1)) * 100

    report = f"""
📊 **OROVA CEO PULSE — Weekly Report**
━━━━━━━━━━━━━━━━━━━━━━
📅 Week of: {m.get('week_start', today.strftime('%Y-%m-%d'))}
⏰ Generated: {today.strftime('%b %d, %Y %I:%M %p PT')}

🎯 **PIPELINE PERFORMANCE**
┌─────────────────────────────┐
│ 🔍 Leads Found:      {m['leads_found']:>5} │
│ 📧 Emails Sent:      {m['emails_sent']:>5} │
│ 💬 Replies Received:  {m['replies_received']:>5} │
│ 📞 Calls Made:        {m['calls_made']:>5} │
│ 📋 Proposals Sent:    {m['proposals_sent']:>5} │
│ 📅 Meetings Booked:   {m['meetings_booked']:>5} │
│ 🎨 Content Created:   {m['content_created']:>5} │
└─────────────────────────────┘

📈 **CONVERSION RATES**
• Email → Reply:    {reply_rate:.1f}%
• Reply → Meeting:  {book_rate:.1f}%

🤖 **AGENT STATUS**
• Nova (CEO): ✅ Active — orchestrating all operations
• Hawk (Lead Hunter): ✅ Active — hunting {m['leads_found']} leads
• Quill (Content): ✅ Active — {m['content_created']} pieces created
• Closer (Sales): ✅ Active — {m['proposals_sent']} proposals sent
• Sentinel (Ops): ✅ Active — monitoring all systems
━━━━━━━━━━━━━━━━━━━━━━
"""

    return report.strip()


def reset_weekly_metrics() -> dict:
    """Reset metrics for a new week."""
    metrics = {
        "leads_found": 0,
        "emails_sent": 0,
        "replies_received": 0,
        "meetings_booked": 0,
        "calls_made": 0,
        "proposals_sent": 0,
        "content_created": 0,
        "week_start": datetime.now().strftime("%Y-%m-%d"),
        "daily_log": [],
    }
    _save_metrics(metrics)
    logger.info("[SENTINEL] Weekly metrics reset.")
    return {"success": True, "message": "Weekly metrics reset."}
