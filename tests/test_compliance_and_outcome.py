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


# ── dial dispositions (2026-08-21) ──────────────────────────────────────────
# Before these, every outcome was post-meeting, so the only loggable result of
# a hand-placed call was `booked` — about one dial in ten. The other nine left
# no record, which is exactly the biased sample that cannot tell you whether
# the ICP is real.

def test_talked_is_loggable_and_marks_contact():
    """The event that means 'a prospect conversation happened'."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
         patch.object(event_log, "_mirror_dial_to_sheets", new_callable=AsyncMock), \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock) as mock_q:
        reply = _run("/outcome 12 talked backlog is 3 weeks, wants numbers")
    assert "call_talked" in reply
    assert mock_log.await_args.kwargs["payload"]["notes"] == "backlog is 3 weeks, wants numbers"
    assert "Contacted" in str(mock_q.await_args)


def test_retryable_dispositions_do_not_touch_status():
    """A dial that changes nothing about where the lead stands changes no status.

    'noanswer', 'voicemail' and 'gatekeeper' all mean try again. Marking them
    'Contacted' would enrol the lead in the cold/re-touch pool
    (_lead_repo.py) on the strength of a phone that rang out.
    """
    for cmd, event in (("noanswer", "call_no_answer"),
                       ("voicemail", "call_voicemail"),
                       ("gatekeeper", "call_gatekeeper")):
        with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
             patch.object(event_log, "_mirror_dial_to_sheets", new_callable=AsyncMock), \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock) as mock_q:
            reply = _run(f"/outcome 7 {cmd}")
        assert event in reply and "status unchanged" in reply
        mock_log.assert_awaited_once()
        # No UPDATE. Reads are fine — the point is nothing WROTE a status.
        assert not any("UPDATE" in str(c).upper()
                       for c in mock_q.await_args_list)


def test_bad_number_never_marks_a_lead_invalid():
    """'Invalid' is excluded from the Sheets backup (durability.py), and boot
    restores FROM that backup onto an ephemeral disk — so 'Invalid' deletes the
    lead on the next deploy. A wrong phone number is not a wrong prospect."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock), \
         patch.object(event_log, "_mirror_dial_to_sheets", new_callable=AsyncMock), \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock) as mock_q:
        reply = _run("/outcome 9 badnumber")
    assert "call_bad_number" in reply
    written = str(mock_q.await_args)
    assert "Bad Number" in written
    assert "Invalid" not in written
    assert all(v[1] != "Invalid" for v in event_log._OUTCOME_MAP.values())


def test_short_aliases_resolve_to_the_same_events():
    for alias, full in (("na", "noanswer"), ("vm", "voicemail"), ("gk", "gatekeeper"),
                        ("ni", "notinterested"), ("cb", "callback"), ("bad", "badnumber")):
        assert event_log._OUTCOME_MAP[alias] == event_log._OUTCOME_MAP[full]


def test_no_is_not_an_alias_for_not_interested():
    """'no' sits one keystroke from 'noanswer' and 'noshow', and it would be the
    alias that ARCHIVES the lead. The safe abbreviation is 'ni'."""
    assert "no" not in event_log._OUTCOME_MAP
    assert event_log._OUTCOME_MAP["ni"][1] == "Archived"
    assert event_log._OUTCOME_MAP["na"][0] == "call_no_answer"


def test_usage_lists_the_dial_dispositions():
    usage = _run("/outcome 12")
    for word in ("noanswer", "voicemail", "gatekeeper", "talked",
                 "notinterested", "callback", "badnumber"):
        assert word in usage


def test_dial_is_mirrored_to_the_call_log_sheet():
    """The events table is created fresh on boot and no sheet tab carries it,
    so a disposition that is not mirrored dies at the next deploy — and deploys
    happen on every push to main. Sheets is the only tier that survives."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock), \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock), \
         patch.object(event_log, "_mirror_dial_to_sheets", new_callable=AsyncMock) as mock_m:
        _run("/outcome 12 talked he is booked out 6 weeks")
    mock_m.assert_awaited_once()
    assert mock_m.await_args.args[1] == "call_talked"
    assert mock_m.await_args.args[2] == "he is booked out 6 weeks"


def test_meeting_outcomes_are_not_mirrored_to_the_call_log():
    """CallLog is a log of calls. A meeting outcome is not one."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock), \
         patch.object(event_log.DatabaseManager, "query", new_callable=AsyncMock), \
         patch.object(event_log, "_mirror_dial_to_sheets", new_callable=AsyncMock) as mock_m:
        _run("/outcome 12 held")
    mock_m.assert_not_awaited()


def test_a_sheets_outage_never_costs_the_event():
    """The event log is canonical; the mirror is only a projection of it."""
    with patch.object(event_log, "alog_event", new_callable=AsyncMock) as mock_log, \
         patch.object(event_log.DatabaseManager, "query",
                      new=AsyncMock(side_effect=RuntimeError("sheets down"))):
        reply = _run("/outcome 12 talked")
    assert "call_talked" in reply
    mock_log.assert_awaited_once()
