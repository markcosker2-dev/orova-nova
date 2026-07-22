"""Tests for the DNC/consent gate on the outbound calling lane."""
import asyncio
from unittest.mock import patch, AsyncMock

from app.core import dnc


def test_normalize():
    assert dnc._normalize("(323) 935-2985") == "3239352985"
    assert dnc._normalize("+1 323 935 2985") == "+13239352985"
    assert dnc._normalize("") == ""


def test_empty_number_is_suppressed():
    assert asyncio.run(dnc.is_suppressed("")) is True
    assert asyncio.run(dnc.is_suppressed(None)) is True


def test_clean_number_not_suppressed():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[])):
        assert asyncio.run(dnc.is_suppressed("+13239352985")) is False


def test_listed_number_is_suppressed_regardless_of_formatting():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=["3239352985"])):
        assert asyncio.run(dnc.is_suppressed("(323) 935-2985")) is True


def test_fails_closed_on_db_error():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(side_effect=RuntimeError("db down"))):
        assert asyncio.run(dnc.is_suppressed("+13239352985")) is True


def test_add_suppression_persists_normalized():
    # Capture set_state PER KEY: the app's background log-flush concurrently
    # calls set_state('agent_logs', ...), which would clobber a single global
    # capture. Keying by state-key isolates the DNC write we're asserting on.
    saved = {}
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[])), \
         patch.object(dnc.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: saved.__setitem__(k, v))):
        ok = asyncio.run(dnc.add_suppression("(323) 935-2985", reason="opt-out"))
    assert ok is True
    assert saved[dnc._DNC_KEY] == ["3239352985"]


def test_dialer_blocks_suppressed_number(monkeypatch):
    monkeypatch.setenv("RETELL_API_KEY", "k")
    monkeypatch.setenv("RETELL_FROM_NUMBER", "+15550000000")
    monkeypatch.setenv("RETELL_AGENT_ID", "a")
    from app.skills import outbound_dialer
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=True)):
        res = asyncio.run(outbound_dialer.trigger_retell_call("+13239352985", {}))
    assert res["success"] is False
    assert "DNC" in res["error"]
