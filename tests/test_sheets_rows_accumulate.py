"""Consecutive lead syncs must land on DIFFERENT rows.

## The bug (production, 2026-08-09 15:03)

The `updatedRange` instrument caught it on its first run. Five distinct
businesses, five appends, one second apart:

    append -> updatedRange='Leads!A2:L2' business='HEARTWOOD BUILDERS INC'
    append -> updatedRange='Leads!A2:L2' business='PEAK BUILDERS INC'
    append -> updatedRange='Leads!A2:L2' business='LEWCO CONTRACTING'
    append -> updatedRange='Leads!A2:L2' business='ELLCO CONSTRUCTION INC'
    append -> updatedRange='Leads!A2:L2' business='ACCRETE CONSTRUCTION LLC'

Every one targeted the same cells and overwrote its predecessor. The Leads tab
therefore held exactly one row no matter how many leads were "synced", and
`Sheets: 5/5 leads synced` was simultaneously true and worthless — five API
calls really did succeed, into a single row.

`append_row` depends on Google's table-range detection from A1, which resolved
to just the header row and kept returning row 2. The fix stops guessing:
column 2 is already read to match on business name, its length is the last used
row, so the write goes to that +1 explicitly.

This is what destroyed lead backups for weeks, and it is why a restore never
returned more than one real lead.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.skills import sheets_sync as ss


class _Worksheet:
    """A sheet that actually stores what it is told to store."""

    def __init__(self, rows=None):
        # rows[0] is the header row
        self.rows = rows if rows is not None else [["ID", "Business"]]
        self.appended_via_append_row = 0

    def col_values(self, n):
        return [(r[n - 1] if len(r) >= n else "") for r in self.rows]

    def update(self, *args, **kwargs):
        rng = kwargs.get("range_name") or (args[0] if args else "")
        vals = kwargs.get("values") or (args[1] if len(args) > 1 else [[]])
        idx = int("".join(c for c in rng.split(":")[0] if c.isdigit()))
        while len(self.rows) < idx:
            self.rows.append([""] * 12)
        self.rows[idx - 1] = list(vals[0])
        return {"updatedRange": f"Leads!{rng}"}

    def append_row(self, row, value_input_option=None):
        self.appended_via_append_row += 1
        # Reproduces the production defect: always writes row 2.
        while len(self.rows) < 2:
            self.rows.append([""] * 12)
        self.rows[1] = list(row)
        return {"updates": {"updatedRange": "Leads!A2:L2"}}


def _run(sheet, business):
    lead = {"business": business, "owner": "X Y", "phone": "+12065550000"}

    async def _fake_get_worksheet(tab, workbook_name=None):
        return sheet

    with patch.object(ss, "_get_worksheet", _fake_get_worksheet):
        return asyncio.run(ss.sync_lead_to_sheets(lead))


def test_five_distinct_businesses_occupy_five_rows():
    """The exact production shape that was silently collapsing to one row."""
    sheet = _Worksheet()
    names = ["HEARTWOOD BUILDERS INC", "PEAK BUILDERS INC", "LEWCO CONTRACTING",
             "ELLCO CONSTRUCTION INC", "ACCRETE CONSTRUCTION LLC"]
    for n in names:
        res = _run(sheet, n)
        assert res["ok"] is True, res

    stored = [r[1] for r in sheet.rows[1:] if len(r) > 1 and str(r[1]).strip()]
    assert len(stored) == 5, f"rows did not accumulate — sheet holds {stored}"
    assert set(stored) == set(names), f"lost or duplicated businesses: {stored}"


def test_each_write_targets_a_new_row():
    sheet = _Worksheet()
    rows_written = []
    real_update = sheet.update

    def _spy(*a, **k):
        rng = k.get("range_name") or (a[0] if a else "")
        rows_written.append(rng)
        return real_update(*a, **k)

    sheet.update = _spy
    for n in ("ALPHA BUILDERS", "BETA CONSTRUCTION", "GAMMA REMODELING"):
        _run(sheet, n)
    assert len(set(rows_written)) == 3, f"writes collided: {rows_written}"


def test_append_row_is_not_used_for_new_leads():
    """append_row's table detection is what produced the A2:L2 collision."""
    sheet = _Worksheet()
    _run(sheet, "DELTA BUILDERS")
    assert sheet.appended_via_append_row == 0, "still relying on table-range detection"


def test_an_existing_business_is_updated_in_place_not_duplicated():
    """The upsert behaviour must survive the fix — re-syncing must not grow the sheet."""
    sheet = _Worksheet()
    _run(sheet, "ALPHA BUILDERS")
    _run(sheet, "ALPHA BUILDERS")
    stored = [r[1] for r in sheet.rows[1:] if len(r) > 1 and str(r[1]).strip()]
    assert stored == ["ALPHA BUILDERS"], f"re-sync duplicated the row: {stored}"


def test_the_header_row_is_never_overwritten():
    sheet = _Worksheet()
    for n in ("ONE BUILDERS", "TWO BUILDERS"):
        _run(sheet, n)
    assert sheet.rows[0][1] == "Business", "header was clobbered"
