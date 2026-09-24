"""AgentMail's provider rule closes prospect email regardless of old send gates."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.planner import TaskPlanner
from app.skills import agentmail_skill, outreach_orchestrator


def test_agentmail_prospect_send_stays_blocked_after_budget_or_approval_changes(monkeypatch):
    monkeypatch.setenv("ZERO_BUDGET_MODE", "0")
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    with patch.object(agentmail_skill, "_get_client") as client, \
         patch.object(agentmail_skill, "_send_via_agentmail", AsyncMock()) as sender, \
         patch("app.core.approval_gate.gate_allows", AsyncMock()) as approval:
        result = asyncio.run(agentmail_skill.send_outreach(
            "owner@example.com", "Quick question", "Hello", _approval_checked=True))
    assert result["status"] == "blocked" and result["skipped"] is True
    assert "provider policy" in result["error"]
    client.assert_not_called()
    sender.assert_not_awaited()
    approval.assert_not_awaited()


def test_nova_planner_cannot_offer_or_execute_generic_email_send():
    planner = TaskPlanner(MagicMock())
    assert "send_email" not in planner.available_functions
    assert "send_outreach" not in planner.available_functions
    assert "create_drip_campaign" not in TaskPlanner.OUTREACH_TOOLS
    for goal in ("email a prospect", "reply to an inbound message", "help me now"):
        offered = {tool["function"]["name"] for tool in planner._scope_tools(goal)}
        assert "send_email" not in offered
        assert "send_outreach" not in offered
        assert "create_drip_campaign" not in offered
    assert "reply_to_email" in planner.available_functions


def test_throttled_mailer_does_not_report_a_blocked_send_as_success():
    client_id = 987654
    outreach_orchestrator._daily_email_count[client_id] = 0
    with patch.object(outreach_orchestrator, "is_business_hours", return_value=True), \
         patch.object(outreach_orchestrator, "_last_email_time", 0.0), \
         patch("app.skills.agentmail_skill.send_outreach", AsyncMock(
             return_value={"status": "blocked", "error": "provider policy"})):
        result = asyncio.run(outreach_orchestrator.send_throttled_email(
            "owner@example.com", "Subject", "Body", client_id=client_id))
    assert result["status"] == "blocked"
    assert outreach_orchestrator._daily_email_count[client_id] == 0


def test_hunt_stores_a_found_email_without_composing_sending_or_enrolling(monkeypatch):
    from app import worker
    from app.core.database import DatabaseManager

    monkeypatch.setenv("ZERO_BUDGET_MODE", "0")
    monkeypatch.setattr(worker, "daily_hunt_counter", 0)
    lead = {"business": "Example Custom Homes", "url": "https://example.com",
            "owner": "Alex", "owner_confidence": 90,
            "email": "alex@example.com", "email_status": "found"}
    with patch.object(worker, "_reset_daily_counters"), \
         patch.object(worker, "find_leads", AsyncMock(return_value={"leads": [lead]})), \
         patch.object(worker, "enrich_lead_lite", AsyncMock(return_value=lead)), \
         patch.object(worker, "score_lead_icp", return_value={"score": 0}), \
         patch.object(DatabaseManager, "aget_metrics", AsyncMock(return_value={"cost": 0})), \
         patch.object(DatabaseManager, "asave_lead", AsyncMock(return_value=7)) as save, \
         patch.object(DatabaseManager, "aupdate_metrics", AsyncMock()), \
         patch.object(DatabaseManager, "get_state", AsyncMock(return_value=None)), \
         patch.object(DatabaseManager, "set_state", AsyncMock()), \
         patch("app.core.event_log.alog_event", AsyncMock()), \
         patch("app.core.durability.persist_leads_durably", AsyncMock(
             return_value={"sheets_synced": 1, "sheets_total": 1, "verified": True})) as persist, \
         patch.object(worker, "send_telegram_report", AsyncMock()), \
         patch("app.skills.outreach_orchestrator.compose_premium_outreach", AsyncMock()) as compose, \
         patch("app.core.approval_gate.gate_allows", AsyncMock(return_value=True)) as approval, \
         patch.object(worker, "send_outreach", AsyncMock()) as send, \
         patch("app.skills.email_sequence_skill.start_drip_campaign", AsyncMock()) as drip:
        asyncio.run(worker.run_lead_hunt_slow_lane(
            niche="custom home builder", location="California"))
    save.assert_awaited_once()
    persist.assert_awaited_once()
    compose.assert_not_awaited()
    approval.assert_not_awaited()
    send.assert_not_awaited()
    drip.assert_not_awaited()
    assert lead.get("status") not in {"Awaiting Approval", "Email Sent"}
