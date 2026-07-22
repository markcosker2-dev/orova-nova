"""Tests for the WP4 reply→qualify→booking funnel.

Covers: the `reply` approval-gate kind, single-reply intent classification (with
its keyword fallback for the no-LLM-key case), the HOT-reply booking queue drain,
and the Cal.com booking webhook that creates the Google Calendar event.
"""
import asyncio
import time
from unittest.mock import patch, AsyncMock

from app.core import approval_gate
from app.skills import agentmail_skill, cal_booking
from app import worker


# ── approval gate: the new `reply` kind ──────────────────────────────────────
def test_reply_autopilot_off_by_default(monkeypatch):
    monkeypatch.delenv("REPLIES_AUTOPILOT", raising=False)
    assert approval_gate.autopilot_enabled("reply") is False


def test_reply_autopilot_on_when_flag_set(monkeypatch):
    monkeypatch.setenv("REPLIES_AUTOPILOT", "1")
    assert approval_gate.autopilot_enabled("reply") is True


def test_gate_allows_reply_on_autopilot(monkeypatch):
    monkeypatch.setenv("REPLIES_AUTOPILOT", "1")
    assert asyncio.run(approval_gate.gate_allows("reply", {"message_id": "m1"}, "r")) is True


# ── classification ───────────────────────────────────────────────────────────
def test_keyword_classify_reply():
    hot = agentmail_skill._keyword_classify_reply("re: your note", "Yes — interested, can we book a call?")
    cold = agentmail_skill._keyword_classify_reply("stop", "please unsubscribe me")
    warm = agentmail_skill._keyword_classify_reply("question", "what does this actually do?")
    assert (hot, cold, warm) == ("HOT", "COLD", "WARM")


def test_optout_hard_stops_without_calling_llm():
    # An opt-out must resolve to COLD *before* any LLM call.
    with patch("app.core.ai_client.UnifiedAIClient") as MockAI:
        verdict = asyncio.run(
            agentmail_skill.classify_reply_intent("re", "not interested, remove me from your list")
        )
    assert verdict == "COLD"
    MockAI.assert_not_called()


def test_classify_falls_back_to_keyword_when_llm_down():
    # No live LLM key (the current blocker) → keyword heuristic still classifies.
    with patch("app.core.ai_client.UnifiedAIClient", side_effect=RuntimeError("no key")):
        verdict = asyncio.run(
            agentmail_skill.classify_reply_intent("re", "very interested, please book a call")
        )
    assert verdict == "HOT"


# ── booking-queue drain ──────────────────────────────────────────────────────
def _queued_item():
    return {
        "message_id": "m1", "email": "jane@acme.com", "name": "Jane",
        "business": "Acme", "lead_id": 5, "client_id": 0, "subject": "re: hi",
        "sender": "Jane <jane@acme.com>", "created_at": time.time(), "attempts": 0,
    }


def test_booking_queue_sends_on_autopilot(monkeypatch):
    monkeypatch.setenv("REPLIES_AUTOPILOT", "1")
    saved = {}
    reply_mock = AsyncMock(return_value={"status": "success", "message_id": "m1"})
    with patch.object(worker.DatabaseManager, "get_state", AsyncMock(return_value=[_queued_item()])), \
         patch.object(worker.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: saved.__setitem__(k, v))), \
         patch.object(worker.DatabaseManager, "query", AsyncMock(return_value={"status": "ok"})), \
         patch("app.skills.agentmail_skill.reply_to_email", reply_mock), \
         patch.object(worker, "send_telegram_report", AsyncMock()):
        asyncio.run(worker.process_pending_booking_replies())
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.args[0] == "m1"     # replied in-thread
    assert saved[worker._BOOKING_QUEUE_KEY] == []                       # drained after success


def test_booking_queue_holds_when_not_approved(monkeypatch):
    monkeypatch.delenv("REPLIES_AUTOPILOT", raising=False)
    saved = {}
    reply_mock = AsyncMock()
    with patch.object(worker.DatabaseManager, "get_state", AsyncMock(return_value=[_queued_item()])), \
         patch.object(worker.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: saved.__setitem__(k, v))), \
         patch("app.core.approval_gate.is_action_approved", AsyncMock(return_value=False)), \
         patch("app.core.approval_gate.request_firewall_approval", AsyncMock(return_value="APPROVAL-0001")), \
         patch("app.skills.agentmail_skill.reply_to_email", reply_mock), \
         patch.object(worker, "send_telegram_report", AsyncMock()):
        asyncio.run(worker.process_pending_booking_replies())
    reply_mock.assert_not_awaited()                   # nothing sent without approval
    assert len(saved[worker._BOOKING_QUEUE_KEY]) == 1                   # stays queued for next cycle


def test_run_reply_monitor_classifies_and_queues_hot():
    inbox = {
        "status": "success", "count": 1, "latest_ts": None,
        "messages": [{
            "message_id": "m9", "from": "Jane <jane@acme.com>",
            "subject": "re: quick idea", "snippet": "interested, please book a call",
        }],
    }
    saved = {}
    with patch.object(worker, "check_replies", AsyncMock(return_value=inbox)), \
         patch("app.skills.agentmail_skill.classify_reply_intent", AsyncMock(return_value="HOT")), \
         patch.object(worker, "send_telegram_report", AsyncMock()), \
         patch.object(worker.DatabaseManager, "query", AsyncMock(return_value=None)), \
         patch.object(worker.DatabaseManager, "aget_metrics", AsyncMock(return_value={})), \
         patch.object(worker.DatabaseManager, "aupdate_metrics", AsyncMock()), \
         patch.object(worker.DatabaseManager, "get_state", AsyncMock(return_value=[])), \
         patch.object(worker.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: saved.__setitem__(k, v))):
        hot = asyncio.run(worker.run_reply_monitor(client_id=0))
    assert len(hot) == 1 and hot[0]["message_id"] == "m9"
    assert saved[worker._BOOKING_QUEUE_KEY][0]["message_id"] == "m9"


# ── Cal.com booking webhook → Google Calendar event ──────────────────────────
def test_handle_booking_created_makes_calendar_event():
    event_data = {"startTime": "2026-07-10T17:00:00Z", "endTime": "2026-07-10T17:30:00Z", "title": "Intro"}
    attendee = {"email": "jane@acme.com", "name": "Jane Doe"}
    with patch("app.skills.calendar_skill.create_event",
               return_value={"success": True, "event_id": "evt123"}) as create_mock, \
         patch("app.worker.send_telegram_report", AsyncMock()):
        res = asyncio.run(cal_booking._handle_booking_created(event_data, attendee))
    assert res["success"] and res["calendar_event_id"] == "evt123"
    create_mock.assert_called_once()


def test_webhook_dispatches_booking_created():
    payload = {
        "triggerEvent": "BOOKING_CREATED",
        "data": {"startTime": "2026-07-10T17:00:00Z",
                 "attendees": [{"email": "j@a.com", "name": "J"}]},
    }
    with patch("app.skills.calendar_skill.create_event",
               return_value={"success": True, "event_id": "e1"}), \
         patch("app.worker.send_telegram_report", AsyncMock()):
        res = asyncio.run(cal_booking.handle_cal_booking_webhook(payload))
    assert res["success"] and res["action"] == "store_meeting"


def test_duration_minutes_from_start_end():
    assert cal_booking._duration_minutes(
        {"startTime": "2026-07-10T17:00:00Z", "endTime": "2026-07-10T17:45:00Z"}
    ) == 45
    assert cal_booking._duration_minutes({}) == 30   # default
