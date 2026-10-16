"""Lean human Nova chat (2026-07-22) — the Telegram brain that replaced the
agentic planner. Grounded in a live snapshot, no tools, fail-open."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, mock_open, patch

import pytest

import app.core.nova_chat as nc


@pytest.mark.parametrize("zone", ["Europe/London", "Asia/Manila"])
def test_operator_timezone_context_uses_configured_iana_zone_without_assuming_hours(zone):
    context = json.dumps({"company": {"operator_timezone": zone}})
    with patch("builtins.open", mock_open(read_data=context)), \
         patch.object(nc, "_pipeline_snapshot", AsyncMock(return_value="No records")), \
         patch("app.core.ai_client.UnifiedAIClient") as client:
        client.return_value.chat = AsyncMock(return_value=SimpleNamespace(content="Prepared"))
        assert asyncio.run(nc.nova_reply("What hours can I offer?")) == "Prepared"
    system = client.return_value.chat.call_args.args[0][0]["content"]
    assert zone in system
    assert "availability" in system.lower()
    assert "fixed" in system.lower()
    assert "in the Philippines" not in system


@pytest.mark.parametrize("company", [{}, {"operator_timezone": "Unknown/Zone"},
                                     {"operator_timezone": "Europe/London; send now"}])
def test_unverified_operator_timezone_never_recreates_an_old_location(company):
    with patch("builtins.open", mock_open(read_data=json.dumps({"company": company}))), \
         patch.object(nc, "_pipeline_snapshot", AsyncMock(return_value="No records")), \
         patch("app.core.ai_client.UnifiedAIClient") as client:
        client.return_value.chat = AsyncMock(return_value=SimpleNamespace(content="Prepared"))
        assert asyncio.run(nc.nova_reply("What hours can I offer?")) == "Prepared"
    system = client.return_value.chat.call_args.args[0][0]["content"]
    assert "operator time zone is unverified" in system.lower()
    assert "in the Philippines" not in system
    assert "Europe/London" not in system


def _snapshot_rows(*leads):
    async def q(sql, params=(), fetchall=False):
        if "COUNT(*)" in sql:
            return [{"n": 0}]
        return list(leads)
    return q


def test_reply_is_grounded_and_returns_ai_text():
    captured = {}

    async def fake_chat(self, messages, **kw):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[-1]["content"]
        return SimpleNamespace(content="You've got 2 leads — West Coast looks hottest.", tool_calls=None)

    with patch("app.core.database.DatabaseManager.aget_metrics", new_callable=AsyncMock,
               return_value={"leads_found": 2, "emails_sent": 0, "replies_received": 0, "meetings_booked": 0}), \
         patch("app.core.database.DatabaseManager.query",
               side_effect=_snapshot_rows({"business": "West Coast Exotic Cars", "owner": "Eric Curran",
                                           "owner_title": "", "status": "New", "score": 75})), \
         patch("app.core.ai_client.UnifiedAIClient.chat", new=fake_chat):
        out = asyncio.run(nc.nova_reply("how's the pipeline?", chat_id=1))
    assert out == "You've got 2 leads — West Coast looks hottest."
    # the live snapshot (real lead) was injected into the system prompt
    assert "West Coast Exotic Cars" in captured["system"]
    assert "Eric Curran" in captured["system"]
    assert "how's the pipeline?" == captured["user"]


def test_provider_failure_gives_friendly_message_not_raw_error():
    async def failing_chat(self, messages, **kw):
        return SimpleNamespace(content="[!!] All AI providers failed for role 'default'", tool_calls=None)

    with patch("app.core.database.DatabaseManager.aget_metrics", new_callable=AsyncMock, return_value={}), \
         patch("app.core.database.DatabaseManager.query", side_effect=_snapshot_rows()), \
         patch("app.core.ai_client.UnifiedAIClient.chat", new=failing_chat):
        out = asyncio.run(nc.nova_reply("hey", chat_id=1))
    assert "[!!]" not in out
    assert "minute" in out.lower() or "trouble" in out.lower()


def test_empty_record_view_does_not_invent_crm_totals():
    with patch("app.core.database.DatabaseManager.aget_metrics", new_callable=AsyncMock, return_value={}), \
         patch("app.core.database.DatabaseManager.query", side_effect=_snapshot_rows()):
        snap = asyncio.run(nc._pipeline_snapshot())
    assert "no records returned" in snap.lower()
    assert "pipeline is empty" not in snap.lower()


def test_reply_never_raises_on_total_failure():
    with patch("app.core.nova_chat._pipeline_snapshot", new_callable=AsyncMock, side_effect=RuntimeError("db down")):
        out = asyncio.run(nc.nova_reply("hi", chat_id=1))  # must not raise
    assert isinstance(out, str) and out
