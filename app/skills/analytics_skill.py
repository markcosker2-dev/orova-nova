# -*- coding: utf-8 -*-
"""
OROVA Analytics Skill — Performance Intelligence
Inspired by OROVA Master Skills: analytics-tracking

Provides deep analytics on OROVA's pipeline, conversions, ROI,
and trend analysis from metrics.json + metrics_history.json.
"""

import json
import os
import logging
from datetime import datetime, timedelta
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# Data directory (same as main.py)
DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_json(filename, default=None):
    """Read JSON from data directory."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        oc_path = os.path.join(DATA_DIR, "orova_instance", filename)
        if os.path.exists(oc_path):
            path = oc_path
        else:
            return default if default is not None else {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default or {}


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE REPORT — Full funnel analysis
# ═══════════════════════════════════════════════════════════════════════════════

async def pipeline_report() -> str:
    """
    Generate a comprehensive pipeline analytics report.
    Analyzes the full funnel: leads → emails → replies → meetings → proposals.
    """
    metrics = DatabaseManager.get_metrics()
    history = _read_json("metrics_history.json", []) 

    leads = metrics.get("leads_found", 0)
    emails = metrics.get("emails_sent", 0)
    replies = metrics.get("replies_received", 0)
    meetings = metrics.get("meetings_booked", 0)
    calls = metrics.get("calls_made", 0)
    proposals = metrics.get("proposals_sent", 0)
    errors = metrics.get("errors", 0)

    report = "# 📊 OROVA Pipeline Analytics Report\n"
    report += f"**Generated:** {datetime.now().strftime('%B %d, %Y at %I:%M %p')}\n\n"

    # ── Funnel Metrics ──
    report += "## 🔄 Pipeline Funnel\n\n"
    report += "| Stage | Count | Conversion |\n"
    report += "|-------|-------|------------|\n"
    report += f"| 🎯 Leads Found | {leads} | — |\n"

    email_rate = f"{(emails/leads*100):.1f}%" if leads > 0 else "—"
    report += f"| ✉️ Emails Sent | {emails} | {email_rate} |\n"

    reply_rate = f"{(replies/emails*100):.1f}%" if emails > 0 else "—"
    report += f"| 💬 Replies | {replies} | {reply_rate} |\n"

    meeting_rate = f"{(meetings/replies*100):.1f}%" if replies > 0 else "—"
    report += f"| 📅 Meetings | {meetings} | {meeting_rate} |\n"

    report += f"| 📞 Calls Made | {calls} | — |\n"
    report += f"| 📝 Proposals | {proposals} | — |\n"

    report += "\n"

    # ── Health Score ──
    report += "## 🏥 System Health\n"
    error_status = "🟢 Healthy" if errors < 5 else "🟡 Warning" if errors < 20 else "🔴 Critical"
    report += f"- Error count: {errors} ({error_status})\n"

    # ── Trend Analysis (last 7 days) ──
    if len(history) >= 2:
        report += "\n## 📈 7-Day Trend\n\n"
        recent = history[-7:] if len(history) >= 7 else history

        lead_trend = _calculate_trend(recent, "leads")
        email_trend = _calculate_trend(recent, "emails")
        reply_trend = _calculate_trend(recent, "replies")

        report += f"- Leads: {lead_trend}\n"
        report += f"- Emails: {email_trend}\n"
        report += f"- Replies: {reply_trend}\n"

    # ── Recommendations ──
    report += "\n## 💡 Recommendations\n"
    recommendations = []

    if leads > 0 and emails == 0:
        recommendations.append("🚨 You have leads but haven't sent any emails. Activate the email drafter!")
    if emails > 10 and replies == 0:
        recommendations.append("⚠️ Low reply rate. Consider switching email frameworks (try PAS or BAB).")
    if replies > 0 and meetings == 0:
        recommendations.append("📅 You're getting replies but no meetings. Add calendar links to follow-ups.")
    if errors > 10:
        recommendations.append("🔧 High error count. Check API keys and service connections.")
    if leads == 0:
        recommendations.append("🎯 No leads found yet. Run a hunt: 'find luxury remodel businesses in California'")

    if not recommendations:
        recommendations.append("✅ Pipeline looks healthy. Keep the momentum going!")

    for rec in recommendations:
        report += f"- {rec}\n"

    return report


def _calculate_trend(history: list, metric: str) -> str:
    """Calculate trend direction and percentage for a metric."""
    if len(history) < 2:
        return "📊 Insufficient data"

    recent = history[-1].get(metric, 0)
    previous = history[-2].get(metric, 0)

    if previous == 0:
        if recent > 0:
            return f"📈 **{recent}** (new activity!)"
        return "⏸️ No activity"

    change = ((recent - previous) / previous) * 100
    if change > 0:
        return f"📈 **+{change:.0f}%** ({previous} → {recent})"
    elif change < 0:
        return f"📉 **{change:.0f}%** ({previous} → {recent})"
    else:
        return f"➡️ Flat ({recent})"


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSION ANALYSIS — Deep dive into conversion rates
# ═══════════════════════════════════════════════════════════════════════════════

async def conversion_analysis() -> str:
    """
    Analyze conversion rates at each pipeline stage with benchmarks.
    """
    metrics = _read_json("metrics.json", {})

    leads = metrics.get("leads_found", 0)
    emails = metrics.get("emails_sent", 0)
    replies = metrics.get("replies_received", 0)
    meetings = metrics.get("meetings_booked", 0)

    report = "# 🔍 Conversion Analysis\n\n"

    # Industry benchmarks for cold outreach
    benchmarks = {
        "email_rate": {"good": 80, "avg": 50, "label": "Lead → Email"},
        "reply_rate": {"good": 5, "avg": 2, "label": "Email → Reply"},
        "meeting_rate": {"good": 30, "avg": 15, "label": "Reply → Meeting"},
    }

    # Lead → Email
    if leads > 0:
        rate = (emails / leads) * 100
        bm = benchmarks["email_rate"]
        status = "🟢" if rate >= bm["good"] else "🟡" if rate >= bm["avg"] else "🔴"
        report += f"### {bm['label']}\n"
        report += f"- Your rate: **{rate:.1f}%** {status}\n"
        report += f"- Benchmark: Good ≥{bm['good']}%, Average ≥{bm['avg']}%\n\n"

    # Email → Reply
    if emails > 0:
        rate = (replies / emails) * 100
        bm = benchmarks["reply_rate"]
        status = "🟢" if rate >= bm["good"] else "🟡" if rate >= bm["avg"] else "🔴"
        report += f"### {bm['label']}\n"
        report += f"- Your rate: **{rate:.1f}%** {status}\n"
        report += f"- Benchmark: Good ≥{bm['good']}%, Average ≥{bm['avg']}%\n\n"

    # Reply → Meeting
    if replies > 0:
        rate = (meetings / replies) * 100
        bm = benchmarks["meeting_rate"]
        status = "🟢" if rate >= bm["good"] else "🟡" if rate >= bm["avg"] else "🔴"
        report += f"### {bm['label']}\n"
        report += f"- Your rate: **{rate:.1f}%** {status}\n"
        report += f"- Benchmark: Good ≥{bm['good']}%, Average ≥{bm['avg']}%\n\n"

    if leads == 0:
        report += "⚠️ No data yet. Start by running a lead hunt to populate the pipeline.\n"

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# ROI CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

async def roi_calculator(spend: float = 0, revenue: float = 0) -> str:
    """
    Calculate ROI metrics for the business.

    Args:
        spend: Total marketing spend (USD)
        revenue: Total revenue generated (USD)

    Returns:
        ROI analysis report
    """
    spend = float(spend)
    revenue = float(revenue)

    report = "# 💰 ROI Calculator\n\n"

    if spend > 0:
        roi = ((revenue - spend) / spend) * 100
        roas = revenue / spend

        report += f"- **Spend:** ${spend:,.2f}\n"
        report += f"- **Revenue:** ${revenue:,.2f}\n"
        report += f"- **Profit:** ${revenue - spend:,.2f}\n"
        report += f"- **ROI:** {roi:.1f}%\n"
        report += f"- **ROAS:** {roas:.1f}x\n\n"

        if roi > 300:
            report += "🟢 **Excellent ROI!** You're in Hormozi territory. Scale aggressively.\n"
        elif roi > 100:
            report += "🟡 **Good ROI.** Profitable but room to optimize. Focus on reducing CAC.\n"
        elif roi > 0:
            report += "🟠 **Break-even zone.** Tighten targeting or improve conversion rates.\n"
        else:
            report += "🔴 **Negative ROI.** Pause and audit before spending more.\n"
    else:
        metrics = _read_json("metrics.json", {})
        report += "## Current Pipeline Value (Estimated)\n"
        leads = metrics.get("leads_found", 0)
        meetings = metrics.get("meetings_booked", 0)

        # Estimated values based on industry averages
        est_lead_value = 50  # $50 per qualified lead
        est_meeting_value = 500  # $500 per meeting

        report += f"- Leads × ${est_lead_value}: **${leads * est_lead_value:,.0f}**\n"
        report += f"- Meetings × ${est_meeting_value}: **${meetings * est_meeting_value:,.0f}**\n"
        report += f"- **Total Pipeline Value:** ${leads * est_lead_value + meetings * est_meeting_value:,.0f}\n"

    return report
