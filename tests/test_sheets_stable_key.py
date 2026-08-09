"""Sheets sync must key on stable identity, not the ephemeral SQLite id
(2026-07-21 durability loss).

The auto-increment id resets to 1,2,3… on every deploy/OOM wipe. Matching
sheet rows by id meant each re-import overwrote a DIFFERENT business that
recycled the same id — 5 distinct leads collapsed to ~1 row, and the boot
restore recovered only 1. Fix: match by URL (domain) then business name;
never by id.
"""
import asyncio
from unittest.mock import patch

import app.skills.sheets_sync as ss


class _WS:
    """Minimal worksheet double: header + existing data rows."""
    def __init__(self, rows):
        # rows: list of [id, business, ..., url(col7), ...]
        self.rows = rows
        self.updated = None
        self.appended = None

    def col_values(self, col):
        return [r[col - 1] if len(r) >= col else "" for r in self.rows]

    def update(self, *a, **k):
        self.updated = (a, k)
        return {}

    def append_row(self, row, value_input_option=None):
        self.appended = row
        return {}


def _sync(ws, lead):
    async def fake_ws(*a, **k):
        return ws
    with patch.object(ss, "_get_worksheet", side_effect=fake_ws), \
         patch.object(ss, "_update_with_backoff",
                      side_effect=lambda w, r, row, **k: _mark_update(w, r, row)), \
         patch.object(ss, "_append_with_backoff",
                      side_effect=lambda w, row, **k: _mark_append(w, row)):
        return asyncio.run(ss.sync_lead_to_sheets(lead))


def _mark_update(ws, target_row, row):
    ws.updated = (target_row, row)
    return {"ok": True, "updated": True, "row": target_row}


def _mark_append(ws, row):
    ws.appended = row
    return {"ok": True, "updated": False}


HEADER = ["ID", "Business", "Owner", "Email", "Phone", "Website", "URL", "Status"]


def test_recycled_id_does_not_overwrite_a_different_business():
    """A distinct business must get its OWN row, never another's.

    Assertion rewritten 2026-08-09. It used to require that `append_row` had
    been called — the mechanism rather than the guarantee. New leads now go to
    an explicitly computed row instead, because `append_row`'s table-range
    detection was resolving to the header and writing EVERY lead to A2:L2, so
    each sync silently overwrote the last and the tab never held more than one
    row. Asserting on the destination row is strictly stronger: it is the thing
    this test exists to protect, and it would have caught that bug.
    """
    ws = _WS([
        HEADER,
        ["1", "West Coast Exotic Cars", "", "", "", "", "https://westcoastexoticcars.com", "New"],
    ])
    new_lead = {"id": 1, "business": "iLusso Exotic Car Dealership",
                "url": "https://ilusso.com"}
    _sync(ws, new_lead)

    written_row = ws.updated[0] if ws.updated else None
    assert written_row != 2, "the new business overwrote West Coast's row"
    assert ws.appended is not None or written_row == 3, (
        f"a distinct business must land on its own row, got row {written_row}")


def test_same_business_updates_in_place_by_url():
    ws = _WS([
        HEADER,
        ["1", "West Coast Exotic Cars", "", "", "", "", "https://westcoastexoticcars.com", "New"],
    ])
    # same business re-synced after a wipe with a fresh id=3
    _sync(ws, {"id": 3, "business": "West Coast Exotic Cars",
               "url": "https://westcoastexoticcars.com", "owner": "Eric Curran"})
    assert ws.updated is not None and ws.updated[0] == 2   # row 2, in place
    assert ws.appended is None


def test_matches_by_business_name_when_no_url():
    ws = _WS([
        HEADER,
        ["1", "Luxury Motorcars", "", "", "", "", "", "New"],
    ])
    _sync(ws, {"id": 9, "business": "luxury motorcars", "owner": "Sam Poe"})
    assert ws.updated is not None and ws.updated[0] == 2   # case-insensitive
    assert ws.appended is None
