"""Regression tests for sheets_sync.restore_leads_from_sheets.

Live-observed failure (production boot log, 2026-07-10): a Leads-sheet row
whose ID cell held "lead_12345" raised `invalid literal for int()`, and the
function-level try/except turned that single bad cell into an EMPTY restore —
total lead loss after a deploy wiped Render's ephemeral disk. These tests pin
the per-row tolerance that fixes it. Fully offline — the worksheet is mocked.
"""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.skills import sheets_sync


def _run_restore_with_rows(rows):
    worksheet = MagicMock()
    worksheet.get_all_records.return_value = rows
    with patch("app.skills.sheets_sync._get_worksheet", AsyncMock(return_value=worksheet)):
        return asyncio.run(sheets_sync.restore_leads_from_sheets())


def test_prefixed_string_id_does_not_abort_restore():
    rows = [
        {"ID": "lead_12345", "Business": "iLusso", "Email": "todd@ilusso.com",
         "URL": "https://ilusso.com", "Score": "88", "ClientID": ""},
        {"ID": "7", "Business": "Acme Roofing", "Email": "jane@acme.com",
         "URL": "https://acme.com", "Score": "", "ClientID": "0"},
    ]
    leads = _run_restore_with_rows(rows)
    assert len(leads) == 2  # the bad ID row survives instead of killing everything
    assert leads[0]["id"] is None          # non-numeric -> DB assigns fresh id
    assert leads[0]["business"] == "iLusso"
    assert leads[1]["id"] == 7


def test_mixed_junk_cells_are_tolerated_per_field():
    rows = [{"ID": None, "Business": "Solo Biz", "Email": "a@b.com",
             "URL": "https://b.com", "Score": "not-a-number", "ClientID": "abc"}]
    leads = _run_restore_with_rows(rows)
    assert len(leads) == 1
    assert leads[0]["score"] is None
    assert leads[0]["client_id"] == 0


def test_empty_marker_rows_still_skipped():
    rows = [{"ID": "", "Business": "", "Email": "", "URL": ""}]
    assert _run_restore_with_rows(rows) == []


def test_int_or_none_coercions():
    f = sheets_sync._int_or_none
    assert f("42") == 42
    assert f(" 42 ") == 42
    assert f("lead_12345") is None
    assert f("") is None
    assert f(None) is None
    assert f(3) == 3
