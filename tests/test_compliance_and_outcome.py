"""CAN-SPAM footer + Telegram meeting-outcome capture (SDR Phase 0, 2026-07-15).

The footer is a legal requirement for commercial email (opt-out + postal
address, 15 U.S.C. §7704). Outcome capture is the learning loop's missing
ground truth: only Mark knows if a meeting was held/no-showed/closed.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.skills.agentmail_skill import _apply_compliance_footer, _OPT_OUT_LINE
from app.core import event_log


# ── CAN-SPAM footer ─────────────────────────────────────────────────────────

def test_footer_appends_opt_out():
    out = _apply_compliance_footer("Hi Todd — quick question.\n\nNova @ OROVA")
    assert _OPT_OUT_LINE in out
    assert out.startswith("Hi Todd")            # body preserved
    assert "OROVA" in out.split("—")[-1]        # identity in the footer block


def test_footer_is_idempotent():
    once = _apply_compliance_footer("body")
    twice = _apply_compliance_footer(once)
    assert twice == once
    assert twice.count(_OPT_OUT_LINE) == 1


def test_footer_includes_postal_address_when_configured(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "123 Main St, Los Angeles, CA 90001")
    out = _apply_compliance_footer("body")
    assert "123 Main St, Los Angeles, CA 90001" in out


def test_footer_without_address_still_ships_opt_out(monkeypatch):
    monkeypatch.delenv("BUSINESS_POSTAL_ADDRESS", raising=False)
    out = _apply_compliance_footer("body")
    assert _OPT_OUT_LINE in out
    assert "OROVA" in out


# ── /outcome command ────────────────────────────────────────────────────────

def _run(text):
    return asyncio.run(event_log.handle_outcome_command(text))


def test_non_outcome_text_returns_none():
    assert _run("what's the pipeline looking like?") is None
    assert _run("") is None
    assert _run(None) is None


def test_malformed_commands_return_usage():
    assert "Usage:" in _run("/outcome")
    assert "Usage:" in _run("/outcome 12")
    assert "must be a number" in _run("/outcome twelve held")
    assert "Unknown outcome" in _run("/outcome 12 exploded")


def test_happy_path_logs_event_and_updates_status():
    with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock) as mock_q:
        reply = _run("/outcome 12 held great call, wants P2 pricing")
    assert "meeting_held" in reply and "12" in reply
    mock_log.assert_awaited_once()
    args = mock_log.await_args
    assert args.args[0] == 12 and args.args[1] == "meeting_held" and args.args[2] == "desk"
    assert args.kwargs["payload"]["notes"] == "great call, wants P2 pricing"
    mock_q.assert_awaited_once()          # lead status update
    assert "Meeting Held" in str(mock_q.await_args)


def test_closed_and_noshow_variants():
    with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock):
        assert "deal_closed" in _run("/outcome 3 closed")
        assert "meeting_noshow" in _run("/outcome 4 no-show")
    assert mock_log.await_count == 2


def test_status_update_failure_still_logs_event():
    """The event is the ground truth — a status-update failure must not lose it."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
         patch.object(event_log.DatabaseManager, "query",
                      new=AsyncMock(side_effect=RuntimeError("db down"))):
        reply = _run("/outcome 5 booked")
    assert "meeting_booked" in reply
    mock_log.assert_awaited_once()
