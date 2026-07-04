"""Tests for the autonomous-outbound approval gate (WP4)."""
import asyncio
from unittest.mock import patch, AsyncMock

from app.core import approval_gate


def test_autopilot_off_by_default(monkeypatch):
    monkeypatch.delenv("OUTREACH_AUTOPILOT", raising=False)
    assert approval_gate.autopilot_enabled("email") is False


def test_autopilot_on_when_flag_set(monkeypatch):
    monkeypatch.setenv("CALLS_AUTOPILOT", "1")
    assert approval_gate.autopilot_enabled("call") is True


def test_gate_allows_when_autopilot_on(monkeypatch):
    monkeypatch.setenv("OUTREACH_AUTOPILOT", "1")
    assert asyncio.run(approval_gate.gate_allows("email", {"lead_id": 1}, "r")) is True


def test_gate_allows_when_already_approved(monkeypatch):
    monkeypatch.delenv("OUTREACH_AUTOPILOT", raising=False)
    with patch.object(approval_gate, "is_action_approved", AsyncMock(return_value=True)):
        assert asyncio.run(approval_gate.gate_allows("email", {"lead_id": 1}, "r")) is True


def test_gate_requests_approval_and_blocks(monkeypatch):
    monkeypatch.delenv("OUTREACH_AUTOPILOT", raising=False)
    req = AsyncMock(return_value="APPROVAL-0001")
    with patch.object(approval_gate, "is_action_approved", AsyncMock(return_value=False)), \
         patch.object(approval_gate, "request_firewall_approval", req):
        assert asyncio.run(approval_gate.gate_allows("email", {"lead_id": 1}, "r")) is False
    req.assert_awaited_once()


def test_gate_fails_closed_on_error(monkeypatch):
    # If the approval system errors, we must NOT send unsupervised.
    monkeypatch.delenv("OUTREACH_AUTOPILOT", raising=False)
    with patch.object(approval_gate, "is_action_approved", AsyncMock(side_effect=RuntimeError("db down"))):
        assert asyncio.run(approval_gate.gate_allows("email", {"lead_id": 1}, "r")) is False
