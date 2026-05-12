"""
Performance Dashboard — tracks metrics and generates weekly CEO reports.
This file was missing from the codebase, causing an ImportError in planner.py.
"""
import logging
from datetime import datetime
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

VALID_METRICS = {
    "leads_found", "emails_sent", "replies_received", "meetings_booked",
    "calls_made", "proposals_sent", "content_created", "ad_spend",
    "monthly_recurring_revenue", "deals_closed", "errors",
}


async def track_metric(metric_name: str, increment: float = 1, client_id: int = 0) -> str:
    """Increment a named performance metric by `increment`."""
    if metric_name not in VALID_METRICS:
        return f"?? Unknown metric '{metric_name}'. Valid: {', '.join(sorted(VALID_METRICS))}"
    try:
        metrics = await DatabaseManager.get_metrics(client_id)
        current = float(metrics.get(metric_name, 0) or 0)
        new_val = current + increment
        await DatabaseManager.update_metrics({metric_name: new_val}, client_id=client_id)
        logger.info(f"[METRICS] {metric_name} += {increment} ? {new_val} (client={client_id})")
        return f"? {metric_name}: {current} ? {new_val}"
    except Exception as e:
        logger.error(f"[METRICS] Failed to track {metric_name}: {e}")
        return f"? Error tracking metric: {e}"


async def generate_weekly_report(client_id: int = 0) -> str:
    """Generate the OROVA CEO Pulse weekly performance report."""
    try:
        m = await DatabaseManager.get_metrics(client_id)
    except Exception as e:
        return f"? Could not load metrics: {e}"

    leads    = int(m.get("leads_found", 0) or 0)
    emails   = int(m.get("emails_sent", 0) or 0)
    replies  = int(m.get("replies_received", 0) or 0)
    meetings = int(m.get("meetings_booked", 0) or 0)
    calls    = int(m.get("calls_made", 0) or 0)
    proposals= int(m.get("proposals_sent", 0) or 0)
    mrr      = float(m.get("monthly_recurring_revenue", 0) or 0)

    def pct(n, d):
        return f"{(n / d * 100):.1f}%" if d > 0 else "—"

    status_line = "? Pipeline healthy." if leads > 0 else "?? No leads yet — run a hunt."

    report = f"""# ?? OROVA CEO Pulse Report
**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}

## Pipeline Funnel
| Stage | Count | Rate |
|-------|-------|------|
| ?? Leads Found | {leads} | — |
| ?? Emails Sent | {emails} | {pct(emails, leads)} |
| ?? Replies | {replies} | {pct(replies, emails)} |
| ?? Meetings | {meetings} | {pct(meetings, replies)} |
| ?? Calls Made | {calls} | — |
| ?? Proposals | {proposals} | — |

## Revenue
- **MRR:** ${mrr:,.2f}

## Status
{status_line}
"""
    return report
