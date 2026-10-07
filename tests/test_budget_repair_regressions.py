"""Offline regressions for the September $0 repair's sending/scheduling sinks."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import ai_client
from app.core.database import DatabaseManager
from app.skills import agentmail_skill as mail


@pytest.fixture(autouse=True)
def zero_budget_defaults(monkeypatch, funded_workflow_test_mode):
    monkeypatch.delenv("ZERO_BUDGET_MODE", raising=False)
    monkeypatch.delenv("CEO_AUTO_EXECUTE", raising=False)


def _inbound(**changes):
    fields = dict(from_="Alex <alex@example.com>", to=["nova@example.com"],
                  reply_to=None, subject="Re: hello", text="Please tell me more.",
                  extracted_text=None)
    fields.update(changes)
    return SimpleNamespace(**fields)


def _reply(original, *, suppressed=False, allowed=True, body="Happy to explain.", checked=False):
    client = MagicMock()
    client.inboxes.messages.get.return_value = original
    with patch.object(mail, "_get_client", return_value=(client, None)), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=suppressed)), \
         patch("app.core.approval_gate.gate_allows", AsyncMock(return_value=allowed)) as gate:
        result = asyncio.run(mail.reply_to_email(
            "message-1", body, "nova@example.com", _approval_checked=checked))
    return result, client.inboxes.messages.reply, gate


def test_reply_to_outbound_message_cannot_bypass_cold_outreach_block():
    result, send, gate = _reply(
        _inbound(from_="Nova <nova@example.com>", to=["alex@example.com"]), checked=True)
    assert result["status"] == "blocked"
    send.assert_not_called()
    gate.assert_not_awaited()


def test_reply_requires_evidence_message_was_addressed_to_this_inbox():
    result, send, gate = _reply(_inbound(to=[]), checked=True)
    assert result["status"] == "blocked"
    send.assert_not_called()
    gate.assert_not_awaited()


def test_approved_inbound_reply_checks_suppression():
    result, send, gate = _reply(_inbound(), suppressed=True, checked=True)
    assert result["status"] == "blocked"
    send.assert_not_called()
    gate.assert_not_awaited()


def test_reply_checks_actual_reply_to_address_for_suppression():
    client = MagicMock()
    client.inboxes.messages.get.return_value = _inbound(reply_to=["blocked@example.com"])
    with patch.object(mail, "_get_client", return_value=(client, None)), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(
             side_effect=lambda address: address == "blocked@example.com")):
        result = asyncio.run(mail.reply_to_email(
            "message-1", "Hello", "nova@example.com", _approval_checked=True))
    assert result["status"] == "blocked"
    client.inboxes.messages.reply.assert_not_called()


def test_reply_honors_optout_in_extracted_inbound_content():
    result, send, gate = _reply(
        _inbound(extracted_text="Please stop emailing me."), checked=True)
    assert result["status"] == "blocked"
    send.assert_not_called()
    gate.assert_not_awaited()


def test_reply_does_not_treat_quoted_outbound_footer_as_an_optout():
    original = _inbound(
        reply_to=["Alex <reply@example.com>"],
        extracted_text="Yes, please tell me more.",
        text="Yes, please tell me more.\n> Not relevant? Reply no thanks.")
    result, send, gate = _reply(original)
    assert result["status"] == "success"
    gate.assert_awaited_once()
    send.assert_called_once_with(
        inbox_id="nova@example.com", message_id="message-1",
        to=["reply@example.com"], reply_all=False, text="Happy to explain.")


def test_reply_pending_approval_never_sends():
    result, send, gate = _reply(_inbound(), allowed=False)
    assert result["status"] == "pending"
    send.assert_not_called()
    gate.assert_awaited_once()


def test_even_approved_reply_cannot_quote_unapproved_commercial_terms():
    result, send, gate = _reply(_inbound(), body="It costs $100 per month.", checked=True)
    assert result["status"] == "blocked"
    send.assert_not_called()
    gate.assert_not_awaited()


def test_reply_monitor_does_not_classify_quoted_footer_as_recipient_optout():
    client = MagicMock()
    client.inboxes.messages.list.return_value = SimpleNamespace(messages=[_inbound(
        message_id="message-1", created_at=datetime.now(timezone.utc),
        extracted_text="Yes, please tell me more.",
        text="Yes, please tell me more.\n> Not relevant? Reply no thanks.")])
    with patch.object(mail, "_get_client", return_value=(client, None)), \
         patch.object(mail, "_get_last_reply_check", AsyncMock(
             return_value=datetime.now(timezone.utc) - timedelta(hours=1))):
        result = asyncio.run(mail.check_replies("nova@example.com", advance_checkpoint=False))
    assert result["status"] == "success"
    assert not mail.is_optout_reply(result["messages"][0]["subject"], result["messages"][0]["snippet"])


def test_zero_budget_scheduler_contains_guard_failure(caplog):
    from app import worker
    job = MagicMock(__name__="slow_lane_job")
    with patch.object(worker, "slow_lane_job", job), \
         patch.object(DatabaseManager, "connection", side_effect=RuntimeError("database unavailable")):
        worker._safe_job(job)
    job.assert_not_called()
    assert "contained; lane stays on cadence" in caplog.text


@pytest.mark.parametrize("count, should_run", [(19, True), (20, False), (200, False)])
def test_zero_budget_scheduled_hunt_pauses_at_existing_pipeline_limit(count, should_run):
    from app import worker
    job = MagicMock(__name__="slow_lane_job")
    connection = MagicMock()
    connection.__enter__.return_value.execute.return_value.fetchone.return_value = (count,)
    with patch.object(worker, "slow_lane_job", job), \
         patch.object(DatabaseManager, "connection", return_value=connection):
        worker._safe_job(job)
    assert job.called is should_run


@pytest.mark.parametrize("job_name, should_run", [
    ("fast_lane_job", False), ("cold_escalation_job", False),
    ("phone_first_job", False), ("self_improvement_job", False),
    ("sequence_drip_job", False), ("health_check_job", False),
    ("cloud_backup_job", True), ("reply_and_drip_check_job", True),
])
def test_zero_budget_scheduler_keeps_only_operational_lanes(job_name, should_run):
    from app import worker
    job = MagicMock(__name__=job_name)
    with patch.object(worker, job_name, job):
        worker._safe_job(job)
    assert job.called is should_run


def test_zero_budget_morning_brief_keeps_requested_client_scope():
    from app.core.ceo_brain import CEOBrain
    brain = object.__new__(CEOBrain)
    with patch("app.core.nova_chat.pipeline_status", AsyncMock(return_value="Stored CRM counts")) as status, \
         patch("app.core.ceo_brain._send_telegram_alert", AsyncMock()):
        result = asyncio.run(brain.morning_brief(client_id=8))
    status.assert_awaited_once_with(8)
    assert result == "Stored CRM counts"


def _ai_client():
    client = object.__new__(ai_client.UnifiedAIClient)
    client.groq_client = None
    client.google_client = None
    client.primary_client = MagicMock()
    client.primary_client.chat.completions.create = AsyncMock()
    return client


def _ai_response(content):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content, tool_calls=None))])


def test_paid_override_cannot_enable_paid_openrouter_models_in_zero_budget(monkeypatch):
    monkeypatch.setenv("OPENROUTER_ALLOW_PAID", "1")
    client = _ai_client()
    client.ROLE_MODELS = {"default": "example/paid-model"}
    client.FALLBACK_CHAIN = ["example/another-paid", "example/valid:free"]
    client.primary_client.chat.completions.create.return_value = _ai_response("Answer")
    with patch.object(ai_client, "_BREAKER", {}), \
         patch.object(ai_client, "_is_open", return_value=False):
        result = asyncio.run(client.chat("Hello"))
    assert result.content == "Answer"
    assert client.primary_client.chat.completions.create.await_args.kwargs["model"] == "example/valid:free"
    assert client.primary_client.chat.completions.create.await_count == 1


def test_blank_groq_and_openrouter_responses_fall_through_to_useful_model():
    client = _ai_client()
    client.groq_client = MagicMock()
    client.groq_client.chat.completions.create = AsyncMock(return_value=_ai_response(""))
    client.ROLE_MODELS = {"default": "example/first:free"}
    client.FALLBACK_CHAIN = ["example/second:free"]
    client.primary_client.chat.completions.create.side_effect = [
        _ai_response("  "), _ai_response("Useful answer")]
    with patch.object(ai_client, "_is_open", return_value=False), \
         patch.object(ai_client, "_record_success"), patch.object(ai_client, "_record_failure"):
        result = asyncio.run(client.chat("Hello"))
    assert result.content == "Useful answer"
    assert client.primary_client.chat.completions.create.await_count == 2


@pytest.mark.parametrize("rejected_id", [-2, -1, 0, None])
def test_rejected_storage_result_cannot_produce_discovery_or_outreach(rejected_id, monkeypatch):
    from app import worker
    monkeypatch.setattr(worker, "daily_hunt_counter", 0)
    lead = dict(business="Example Custom Homes", url="https://example.com",
                owner="Alex", owner_confidence=90, email="alex@example.com")
    with patch.object(worker, "_reset_daily_counters"), \
         patch.object(worker, "find_leads", AsyncMock(return_value={"leads": [lead]})), \
         patch.object(worker, "enrich_lead_lite", AsyncMock(return_value=lead)), \
         patch.object(worker, "score_lead_icp", return_value={"score": 0}), \
         patch.object(DatabaseManager, "aget_metrics", AsyncMock(return_value={"cost": 0})), \
         patch.object(DatabaseManager, "asave_lead", AsyncMock(return_value=rejected_id)), \
         patch("app.core.event_log.alog_event", AsyncMock()) as event, \
         patch.object(worker, "send_outreach", AsyncMock()) as send, \
         patch("app.skills.email_sequence_skill.start_drip_campaign", AsyncMock()) as drip, \
         patch.object(worker, "send_telegram_report", AsyncMock()) as report, \
         patch("app.skills.vault_skill.backup_database", AsyncMock()) as backup:
        asyncio.run(worker.run_lead_hunt_slow_lane(niche="custom home builder", location="California"))
    event.assert_not_awaited()
    send.assert_not_awaited()
    drip.assert_not_awaited()
    report.assert_not_awaited()
    backup.assert_not_awaited()
