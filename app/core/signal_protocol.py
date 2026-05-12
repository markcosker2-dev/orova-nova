# -*- coding: utf-8 -*-
"""
OROVA Signal Protocol — 3-Tier Telegram Communication
======================================================
Nova communicates with the Owner via a strict 3-tier signal system.
All Telegram messages follow exact MSI format.
No message is sent without a Signal Tier header.

Tier 1: [REVENUE ALERT] — High-intent lead or contract action
Tier 2: [MISSION PULSE]  — Daily automated report (08:00/20:00 ET)
Tier 3: [CRITICAL EXCEPTION] — Sub-agent failure after 3 correction cycles
"""

import os
import logging
import datetime
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

_CEO_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID") or None


def _get_chat_id():
    """Get CEO's Telegram chat ID."""
    global _CEO_CHAT_ID
    if not _CEO_CHAT_ID:
        _CEO_CHAT_ID = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    if not _CEO_CHAT_ID:
        # Check persisted file
        try:
            chat_id_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "ceo_chat_id.txt")
            if os.path.exists(chat_id_file):
                with open(chat_id_file, "r") as f:
                    _CEO_CHAT_ID = f.read().strip()
        except Exception:
            pass
    return _CEO_CHAT_ID


def set_chat_id(chat_id: str):
    """Auto-detect CEO chat ID from first Telegram message. Persists to disk."""
    global _CEO_CHAT_ID
    _CEO_CHAT_ID = str(chat_id)
    logger.info(f"[SIGNAL] CEO chat ID set: {_CEO_CHAT_ID}")

    # Persist to file so it survives restarts
    try:
        chat_id_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "ceo_chat_id.txt")
        os.makedirs(os.path.dirname(chat_id_file), exist_ok=True)
        with open(chat_id_file, "w") as f:
            f.write(str(chat_id))
    except Exception:
        pass


def _send_telegram(message: str, parse_mode: str = "Markdown"):
    """Low-level Telegram send."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = _get_chat_id()
    if not token or not chat_id:
        logger.warning("[SIGNAL] Cannot send — TOKEN or CHAT_ID missing.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "text": message, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        logger.warning(f"[SIGNAL] Telegram returned {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"[SIGNAL] Telegram send failed: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 1 — REVENUE ALERT
# ═══════════════════════════════════════════════════════════════════════════════

def send_revenue_alert(
    client_name: str,
    vertical: str,
    elite_score: int,
    status: str,
    projected_value: str,
    next_action: str,
    timeline: str = "Executing in 2 hours unless overridden.",
):
    """
    Tier 1 — Revenue Alert.
    Trigger: Lead reaches Elite Score 85+ OR contract action pending.
    Owner Action: Approve or Override within 2 hours.
    """
    message = (
        f"[REVENUE ALERT] ─────────────────────────\n"
        f"Client:   {client_name}\n"
        f"Vertical: {vertical}\n"
        f"Score:    {elite_score} / 100\n"
        f"Status:   {status}\n"
        f"Value:    {projected_value}\n"
        f"─────────────────────────────────────────\n"
        f"Nova's Move: {next_action}\n"
        f"Timeline:    {timeline}\n"
        f"Override:    Reply HOLD to pause. Reply APPROVE to accelerate.\n"
        f"─────────────────────────────────────────"
    )
    logger.info(f"[SIGNAL T1] REVENUE ALERT for {client_name} — Score {elite_score}")
    return _send_telegram(message, parse_mode=None)


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 2 — MISSION PULSE
# ═══════════════════════════════════════════════════════════════════════════════

def send_mission_pulse(
    period: str,
    metrics: Dict,
    active_agents: int = 0,
    priority: str = "",
    nova_note: str = "",
):
    """
    Tier 2 — Mission Pulse.
    Trigger: Daily at 08:00 ET and 20:00 ET, automated.
    Owner Action: None (informational only).

    Args:
        period: "AM" or "PM"
        metrics: Dict with leads_in_pipeline, new_today, outreach_sent_email,
                 outreach_sent_calls, interested, proposals_out, proposals_value,
                 appointments_booked, elite_score_avg
        active_agents: Number of sub-agents currently running
        priority: Today's priority target
        nova_note: One sentence — precise, clinical, forward-looking
    """
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = "08:00" if period == "AM" else "20:00"

    leads_total = metrics.get("leads_in_pipeline", 0)
    new_today = metrics.get("new_today", 0)
    emails = metrics.get("outreach_sent_email", 0)
    calls = metrics.get("outreach_sent_calls", 0)
    interested = metrics.get("interested", 0)
    proposals = metrics.get("proposals_out", 0)
    proposals_value = metrics.get("proposals_value", "$0")
    appointments = metrics.get("appointments_booked", 0)
    avg_score = metrics.get("elite_score_avg", 0)

    message = (
        f"[MISSION PULSE — {period}] ─────────────────\n"
        f"Period:   {date_str} {time_str} ET\n"
        f"─────────────────────────────────────────\n"
        f"Active Cycles:    {active_agents} sub-agents running\n"
        f"Leads in Pipeline:{leads_total} ({new_today} new today)\n"
        f"Outreach Sent:    {emails} emails | {calls} calls\n"
        f"Interested:       {interested} leads\n"
        f"Proposals Out:    {proposals} | Value: {proposals_value}\n"
        f"Appointments:     {appointments} booked this week\n"
        f"─────────────────────────────────────────\n"
        f"Today's Priority: {priority or 'Pipeline review and outreach'}\n"
        f"Elite Score Avg:  {avg_score} / 100\n"
        f"Nova's Note:      {nova_note or 'Systems nominal. Pipeline under active management.'}\n"
        f"─────────────────────────────────────────"
    )
    logger.info(f"[SIGNAL T2] MISSION PULSE {period} — {leads_total} leads, {emails} emails")
    return _send_telegram(message, parse_mode=None)


def send_initialization_pulse(leads_count: int, verticals_count: int):
    """
    Send initialization confirmation when Nova comes online.
    """
    message = (
        f"[MISSION PULSE — INITIALIZATION]\n"
        f"Nova is online. All systems nominal.\n"
        f"Pipeline loaded: {leads_count} leads across {verticals_count} verticals.\n"
        f"Awaiting your first directive or standing by for autonomous operation.\n\n"
        f"First recommended action: /health to confirm all systems,\n"
        f"then /scrape [vertical] to begin sourcing."
    )
    logger.info(f"[SIGNAL T2] INITIALIZATION — {leads_count} leads loaded")
    return _send_telegram(message, parse_mode=None)


# ═══════════════════════════════════════════════════════════════════════════════
# TIER 3 — CRITICAL EXCEPTION
# ═══════════════════════════════════════════════════════════════════════════════

def send_critical_exception(
    source_agent: str,
    cycle: str,
    issue: str,
    impact: str,
    proposed_fix: str,
    risk: str = "Medium",
):
    """
    Tier 3 — Critical Exception.
    Trigger: Sub-agent fails 3 correction cycles OR system fault persists.
    Owner Action: Reply YES to proceed, NO to pause.
    """
    message = (
        f"[CRITICAL EXCEPTION] ────────────────────\n"
        f"Source:    {source_agent}\n"
        f"Cycle:     {cycle}\n"
        f"─────────────────────────────────────────\n"
        f"Issue:     {issue}\n"
        f"Impact:    {impact}\n"
        f"─────────────────────────────────────────\n"
        f"Nova's Fix: {proposed_fix}\n"
        f"Risk:       {risk}\n"
        f"─────────────────────────────────────────\n"
        f"Input Needed: YES — Reply YES to execute Nova's fix.\n"
        f"              Reply NO to pause this agent and re-route.\n"
        f"─────────────────────────────────────────"
    )
    logger.info(f"[SIGNAL T3] CRITICAL EXCEPTION — {source_agent}: {issue}")
    return _send_telegram(message, parse_mode=None)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Generate Mission Pulse from Database
# ═══════════════════════════════════════════════════════════════════════════════

def generate_pulse_metrics() -> Dict:
    """
    Pull current metrics from the database for Mission Pulse.
    Returns a dict ready for send_mission_pulse().
    """
    try:
        from app.core.database import DatabaseManager

        # Get all metrics
        db_metrics = DatabaseManager.get_metrics(0)
        leads = DatabaseManager.get_leads(0)

        # Count new leads today
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        new_today = sum(
            1 for l in leads
            if l.get("created_at", "").startswith(today)
        )

        # Count interested leads
        interested = sum(
            1 for l in leads
            if l.get("status", "").lower() in ("interested", "hot", "warm", "replied")
        )

        # Calculate average elite score
        scores = [l.get("score", 0) for l in leads if l.get("score", 0) > 0]
        avg_score = int(sum(scores) / len(scores)) if scores else 0

        return {
            "leads_in_pipeline": len(leads),
            "new_today": new_today,
            "outreach_sent_email": db_metrics.get("emails_sent", 0),
            "outreach_sent_calls": db_metrics.get("calls_made", 0),
            "interested": interested,
            "proposals_out": db_metrics.get("proposals_sent", 0),
            "proposals_value": "$0",
            "appointments_booked": db_metrics.get("meetings_booked", 0),
            "elite_score_avg": avg_score,
        }
    except Exception as e:
        logger.error(f"[SIGNAL] Failed to generate pulse metrics: {e}")
        return {
            "leads_in_pipeline": 0,
            "new_today": 0,
            "outreach_sent_email": 0,
            "outreach_sent_calls": 0,
            "interested": 0,
            "proposals_out": 0,
            "proposals_value": "$0",
            "appointments_booked": 0,
            "elite_score_avg": 0,
        }


def run_mission_pulse(period: str = "AM"):
    """
    Convenience function for scheduler: generates metrics and sends pulse.
    """
    metrics = generate_pulse_metrics()

    # Count active agents
    try:
        import json
        data_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        agent_path = os.path.join(data_dir, "agent_status.json")
        if os.path.exists(agent_path):
            with open(agent_path, "r") as f:
                agents = json.load(f)
            active = len([a for a in agents.values() if isinstance(a, dict) and a.get("status") == "active"])
        else:
            active = 0
    except Exception:
        active = 0

    send_mission_pulse(
        period=period,
        metrics=metrics,
        active_agents=active,
        nova_note="Systems nominal. Pipeline under active management.",
    )
