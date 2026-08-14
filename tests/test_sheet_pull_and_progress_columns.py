"""The sheet becomes two-way for ONE field, and reports progress for two more.

## Why the pull exists (2026-08-09)

The Leads sheet was WRITE-ONLY. `restore_leads_from_sheets` is called in
exactly one place — the "database appears empty" branch at startup — so once
the DB holds any lead, nothing ever reads the sheet again. The owner planned to
find emails by hand and type them into the sheet, expecting Nova to use them.
Without a pull they would have sat there forever while every outreach lane saw
a blank field, and hours of manual work would have gone nowhere.

It is deliberately narrow: `email` only, and only into a lead that has none.
The database is the canonical owner of prospect data (CLAUDE.md SSoT) and the
sheet is its projection. A projection that can overwrite arbitrary columns of
its source is not a projection, and one mis-sorted column would corrupt the
pipeline silently.

EmailSent and Called are the reverse direction — pure read-outs, derived from
the database on every sync. Editing them in Sheets does nothing.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.skills import sheets_sync as ss


# ── the progress read-outs ──────────────────────────────────────────────────

@pytest.mark.parametrize("status,expected", [
    ("New", "No"),
    ("", "No"),
    ("Email Sent", "Yes"),
    ("email sent", "Yes"),
    ("Contacted", "Yes"),
    ("Replied", "Yes"),
    ("Meeting Booked", "Yes"),
])
def test_email_sent_is_derived_from_status(status, expected):
    assert ss._email_sent_cell({"status": status}) == expected


def test_email_status_alone_can_mark_it_sent():
    assert ss._email_sent_cell({"status": "New", "email_status": "sent"}) == "Yes"


@pytest.mark.parametrize("count,expected", [
    (0, "No"), (None, "No"), ("", "No"), ("junk", "No"), (1, "Yes"), (3, "Yes"),
])
def test_called_counts_real_placed_calls(count, expected):
    assert ss._called_cell({"call_count": count}) == expected


def test_a_blocked_lead_does_not_read_as_called():
    """A lead the consent or DNC gate refused has NOT been worked. If it showed
    as Called the owner would skip it, and a compliance block would look like
    outreach."""
    assert ss._called_cell({"call_count": 0, "status": "New"}) == "No"


def test_the_row_width_still_matches_the_header():
    written = {}

    class _WS:
        def col_values(self, n):
            return ["Business"]

        def update(self, *a, **k):
            written["row"] = (k.get("values") or a[1])[0]
            return {}

    async def _fake_ws(tab, workbook_name=None):
        return _WS()

    with patch.object(ss, "_get_worksheet", _fake_ws):
        asyncio.run(ss.sync_lead_to_sheets(
            {"business": "PEAK BUILDERS INC", "status": "Email Sent", "call_count": 2}))

    headers = ss.WORKSHEET_HEADERS["Leads"]
    row = written["row"]
    assert len(row) == len(headers)
    cell = dict(zip(headers, row))
    assert cell["EmailSent"] == "Yes"
    assert cell["Called"] == "Yes"


# ── the pull ────────────────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    async def fetchall(self, sql, params=None):
        """Mirrors the real query: business + optional state + client_id.

        The fake used to answer `fetchone` and match on business alone, which
        made it easier to satisfy than production — the shape that let the
        row-2 overwrite hide for weeks. It now honours every filter the real
        SELECT applies, so a missing one fails here instead of in the sheet.
        """
        biz, state, _state2, client_id = params
        out = []
        for r in self.rows:
            if r["business"].lower() != biz:
                continue
            if state and str(r.get("state") or "").upper() != state:
                continue
            if int(r.get("client_id") or 0) != int(client_id):
                continue
            out.append(dict(r))
        return out

    async def query(self, sql, params=None, **k):
        self.updates.append(params)
        return None


def _pull(records, db_rows):
    class _WS:
        def get_all_records(self):
            return records

    async def _fake_ws(tab, workbook_name=None):
        return _WS()

    db = _FakeDB(db_rows)
    with patch.object(ss, "_get_worksheet", _fake_ws), \
         patch("app.core.database.DatabaseManager", db):
        res = asyncio.run(ss.pull_manual_edits_from_sheets())
    return res, db


def test_an_owner_typed_email_reaches_the_database():
    res, db = _pull(
        [{"Business": "ACCRETE CONSTRUCTION LLC", "Email": "michael@accrete.com", "State": "WA"}],
        [{"id": 7, "business": "ACCRETE CONSTRUCTION LLC", "email": "",
           "state": "WA", "client_id": 0}])
    assert res["updated"] == 1, res
    assert db.updates and db.updates[0][0] == "michael@accrete.com"
    assert db.updates[0][1] == 7


def test_an_existing_address_is_never_overwritten():
    """The DB is canonical. A stale sheet cell must not clobber a real address."""
    res, db = _pull(
        [{"Business": "ACCRETE CONSTRUCTION LLC", "Email": "typo@accrete.com", "State": "WA"}],
        [{"id": 7, "business": "ACCRETE CONSTRUCTION LLC", "email": "real@accrete.com",
           "state": "WA", "client_id": 0}])
    assert res["updated"] == 0
    assert res["skipped"] == 1
    assert db.updates == []


def test_a_bad_address_is_rejected_by_the_same_validator_as_every_ingest():
    res, _ = _pull(
        [{"Business": "ACCRETE CONSTRUCTION LLC", "Email": "not-an-email", "State": "WA"}],
        [{"id": 7, "business": "ACCRETE CONSTRUCTION LLC", "email": "",
           "state": "WA", "client_id": 0}])
    assert res["updated"] == 0
    assert res["rejected"] == 1


def test_a_business_not_in_the_database_is_skipped_not_created():
    """The pull updates leads; it must never become a second ingest path that
    bypasses the storage gate."""
    res, db = _pull(
        [{"Business": "GHOST BUILDERS", "Email": "x@ghost.com", "State": "WA"}], [])
    assert res["updated"] == 0
    assert db.updates == []


def test_a_blank_state_cell_with_two_matching_firms_is_skipped_not_guessed():
    """A bare name can hit two genuinely different firms.

    `save_lead` refuses to merge on a name alone for exactly this reason.
    Writing the owner's address onto an arbitrary one of them is worse than
    skipping, because it looks like it worked — he would never re-check it.
    """
    res, db = _pull(
        [{"Business": "SUMMIT BUILDERS", "Email": "owner@summit.com", "State": ""}],
        [{"id": 1, "business": "SUMMIT BUILDERS", "email": "", "state": "WA", "client_id": 0},
         {"id": 2, "business": "SUMMIT BUILDERS", "email": "", "state": "OR", "client_id": 0}])
    assert res["updated"] == 0
    assert res["skipped"] == 1
    assert db.updates == [], "an ambiguous match must never be guessed"


def test_a_blank_state_cell_still_works_when_only_one_firm_matches():
    """The guard must not block the ordinary case."""
    res, db = _pull(
        [{"Business": "SUMMIT BUILDERS", "Email": "owner@summit.com", "State": ""}],
        [{"id": 1, "business": "SUMMIT BUILDERS", "email": "", "state": "WA", "client_id": 0}])
    assert res["updated"] == 1
    assert db.updates[0][1] == 1


def test_another_clients_lead_is_never_touched():
    """Every other lead query scopes by client_id; this one must too."""
    res, db = _pull(
        [{"Business": "ACCRETE CONSTRUCTION LLC", "Email": "michael@accrete.com", "State": "WA"}],
        [{"id": 9, "business": "ACCRETE CONSTRUCTION LLC", "email": "",
          "state": "WA", "client_id": 3}])
    assert res["updated"] == 0
    assert db.updates == [], "a sheet must not write across client boundaries"


def test_blank_email_cells_are_ignored_entirely():
    res, db = _pull(
        [{"Business": "ACCRETE CONSTRUCTION LLC", "Email": "", "State": "WA"}],
        [{"id": 7, "business": "ACCRETE CONSTRUCTION LLC", "email": "",
           "state": "WA", "client_id": 0}])
    assert res["checked"] == 0 and res["updated"] == 0
    assert db.updates == []
