"""An append must report WHERE it wrote, not just that it returned.

## Why this exists (production, 2026-08-09)

With the workbook pinned by ID and the id in the logs matching the owner's own
browser URL — so both parties provably on the same document — production logged:

    [SheetsSync] workbook id=1udNrtV09Y7Eg2bWkU8-5cNbat-8TxZt9ZNoD5j3x-BM
    [DURABILITY:csv_import] 4/4 leads synced
    [DURABILITY:csv_import] BACKUP INCOMPLETE — db holds 5 distinct businesses
                            but the Leads sheet has only 1 rows

Four appends raised nothing and appeared nowhere. Duplicate workbooks, duplicate
collapse and a read-after-write race were all ruled out by then.

The Sheets API answers this directly: append returns `updates.updatedRange`,
naming the exact cells written including the tab. `_append_with_backoff` was
discarding the response, so the one fact that distinguishes "wrote to a
different tab" from "wrote nowhere" was being thrown away on every call.

The lesson this session kept re-teaching: instrument the thing you cannot
explain, rather than reasoning further from evidence that has already run out.
"""
import asyncio

import pytest

from app.skills import sheets_sync as ss


class _Sheet:
    def __init__(self, resp):
        self._resp = resp
        self.appended = []

    def append_row(self, row, value_input_option=None):
        self.appended.append(row)
        return self._resp


ROW = ["", "HAWK CONSTRUCTION", "Kulwinder Gakhal", "", "+12065550104",
       "", "", "New", 45, "csv_import", "2026-08-09", ""]


def test_the_written_range_is_returned():
    sheet = _Sheet({"updates": {"updatedRange": "Leads!A3:L3", "updatedRows": 1}})
    res = asyncio.run(ss._append_with_backoff(sheet, ROW))
    assert res["ok"] is True
    assert res["updated_range"] == "Leads!A3:L3", "the write location must be reported"


def test_the_written_range_is_logged_with_the_business(caplog):
    """The log line is the artifact — it has to name both range and business."""
    sheet = _Sheet({"updates": {"updatedRange": "Leads!A7:L7"}})
    with caplog.at_level("INFO"):
        asyncio.run(ss._append_with_backoff(sheet, ROW))
    assert "Leads!A7:L7" in caplog.text
    assert "HAWK CONSTRUCTION" in caplog.text


def test_a_write_landing_on_another_tab_is_visible():
    """The failure mode this is built to catch.

    If appends land on a tab count_lead_rows never reads, the range says so
    outright — no inference required.
    """
    sheet = _Sheet({"updates": {"updatedRange": "Sheet1!A2:L2"}})
    res = asyncio.run(ss._append_with_backoff(sheet, ROW))
    assert res["updated_range"].startswith("Sheet1!"), "must surface the real tab"


@pytest.mark.parametrize("resp", [None, {}, {"updates": {}}, "unexpected-string"])
def test_a_missing_or_odd_response_never_breaks_the_write(resp):
    """Durability is best-effort — instrumentation must not become a new failure.

    gspread's return shape varies by version, and a diagnostic that raises
    would turn a working backup into a broken one.
    """
    sheet = _Sheet(resp)
    res = asyncio.run(ss._append_with_backoff(sheet, ROW))
    assert res["ok"] is True, "the append must still count as successful"
    assert "updated_range" in res
