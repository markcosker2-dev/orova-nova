"""The durable tier must verify itself, not assert itself.

## The incident this exists to prevent

2026-08-07, production, twice in one day:

    [DURABILITY:hunt] 📋 Sheets: 5/5 leads synced        <- reported success
    ...
    ♻️ Restored 1/4 leads from Google Sheets             <- next boot

15 leads became 1. Both log lines were INFO. Nothing anywhere said a backup had
failed, because nothing ever checked: `sync_lead_to_sheets` returning `ok`
means the API accepted a call, NOT that a row is readable afterwards.

A backup that reports success without being readable is worse than having no
backup at all, because it suppresses the alarm you would otherwise act on.

So `persist_leads_durably` now reads the sheet back and compares it against
what the database actually holds, and says so loudly when they disagree.
"""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, patch

from app.core import durability


def _real_row(**cols):
    """A genuine sqlite3.Row — the shape DatabaseManager actually returns.

    This is not pedantry. These tests used to mock fetchone with a plain dict,
    and `sqlite3.Row` has no `.get()`. So the verification block raised
    AttributeError on every single production run from the day it shipped
    (#153) while all of these tests passed. A fixture that is easier to
    satisfy than production is not a test, it is a decoy — so build the real
    type here and let the mock be as awkward as the real thing.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    keys = list(cols)
    sql = "SELECT " + ", ".join(f"? AS {k}" for k in keys)
    return conn.execute(sql, tuple(cols[k] for k in keys)).fetchone()


def _run(sheet_rows, n_leads, n_distinct=None):
    """Run persist_leads_durably with a sheet that reports `sheet_rows`.

    `n_distinct` is how many DISTINCT businesses those `n_leads` rows cover
    (defaults to all-unique). The sheet upserts by URL/business name, so it is
    a deduplicated projection of the leads table — the two counts legitimately
    differ and only `n_distinct` is the number a complete backup must reach.
    """
    if n_distinct is None:
        n_distinct = n_leads
    rows = [{"id": i, "business": f"Biz {i}", "url": f"https://b{i}.com"}
            for i in range(1, n_leads + 1)]

    class _DB:
        @staticmethod
        async def query(sql, params=None, fetchall=False):
            return rows

        @staticmethod
        async def fetchone(sql, params=None):
            return _real_row(total=n_leads, distinct_ids=n_distinct)

    with patch("app.core.database.DatabaseManager", _DB), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets",
               AsyncMock(return_value={"ok": True})), \
         patch("app.skills.sheets_sync.count_lead_rows",
               AsyncMock(return_value=sheet_rows)), \
         patch("app.skills.vault_skill.backup_database",
               AsyncMock(return_value={"ok": False, "error": "invalid_grant"})):
        return asyncio.run(durability.persist_leads_durably(recent_count=25, source="test"))


def test_a_complete_backup_is_reported_verified():
    res = _run(sheet_rows=10, n_leads=10)
    assert res["verified"] is True
    assert res["sheet_rows"] == 10
    assert res["db_total"] == 10


def test_the_exact_production_failure_is_now_caught(caplog):
    """5 syncs report ok, the sheet holds 4 rows, DB holds 15.

    This is the real 2026-08-07 shape. Before this change it logged
    "Sheets: 5/5 leads synced" and nothing else.
    """
    with caplog.at_level("ERROR"):
        res = _run(sheet_rows=4, n_leads=15)
    assert res["verified"] is False
    assert "BACKUP INCOMPLETE" in caplog.text
    assert "15" in caplog.text and "4" in caplog.text


def test_a_silent_total_failure_is_caught():
    """Every sync claims ok and the sheet is empty — the worst case."""
    res = _run(sheet_rows=0, n_leads=12)
    assert res["verified"] is False


def test_an_unverifiable_check_is_not_treated_as_an_empty_sheet(caplog):
    """None means "we could not look", which is NOT the same as "it is gone".

    Conflating the two would either cry wolf on a transient API blip or, worse,
    let a real emptiness be logged as a mere check failure.
    """
    with caplog.at_level("WARNING"):
        res = _run(sheet_rows=None, n_leads=9)
    assert res.get("verified") is not False, "an unknown must not be reported as a failure"
    assert "UNKNOWN" in caplog.text


def test_verification_never_breaks_the_sync_itself():
    """Durability is best-effort — a failing CHECK must not lose the WRITE."""
    rows = [{"id": 1, "business": "Biz 1", "url": "https://b1.com"}]

    class _DB:
        @staticmethod
        async def query(sql, params=None, fetchall=False):
            return rows

        @staticmethod
        async def fetchone(sql, params=None):
            raise RuntimeError("db exploded during verification")

    with patch("app.core.database.DatabaseManager", _DB), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets",
               AsyncMock(return_value={"ok": True})), \
         patch("app.skills.sheets_sync.count_lead_rows",
               AsyncMock(return_value=1)), \
         patch("app.skills.vault_skill.backup_database",
               AsyncMock(return_value={"ok": False, "error": "x"})):
        res = asyncio.run(durability.persist_leads_durably(recent_count=25, source="test"))
    assert res["sheets_synced"] == 1, "the write was lost because the check failed"


def test_the_check_survives_a_real_sqlite_row():
    """The regression that made #153's instrument useless in production.

    `DatabaseManager.fetchone` hands back a sqlite3.Row, not a dict. The old
    code called `.get("c")` on it, raised AttributeError, and logged
    "durability UNKNOWN this run" on every hunt — so the one number that would
    have settled weeks of speculation was never actually read. Assert the
    reading is TAKEN, not merely that nothing crashed.
    """
    res = _run(sheet_rows=10, n_leads=10)
    assert res.get("db_total") == 10, "the verification never read the database"
    assert res.get("verified") is True


def test_duplicate_lead_rows_are_not_reported_as_a_lost_backup():
    """The exact 2026-08-09 production shape: 24 lead rows, 13 businesses.

    save_lead only dedups on email or website domain, and licence-registry
    leads (WA L&I / OR CCB / CSLB) have neither — so the same contractor is
    re-inserted every hunt. The sheet upserts by business name and correctly
    collapses them. Comparing 13 against 24 would report a catastrophe that
    is not happening, and a monitor nobody believes is worse than no monitor.
    """
    res = _run(sheet_rows=13, n_leads=24, n_distinct=13)
    assert res["verified"] is True, "duplicate DB rows must not read as data loss"
    assert res["db_total"] == 24 and res["db_distinct"] == 13


def test_a_real_loss_is_still_caught_underneath_the_duplicates():
    """Dedup-awareness must not become blindness.

    13 distinct businesses, sheet holds 9 — four businesses really are absent
    and will not survive the next restart. This must still be loud.
    """
    res = _run(sheet_rows=9, n_leads=24, n_distinct=13)
    assert res["verified"] is False


def test_drive_being_dead_still_does_not_gate_sheets():
    """The regression that started all of this: Drive must never suppress Tier 1."""
    res = _run(sheet_rows=3, n_leads=3)
    assert res["drive"] is False
    assert res["sheets_synced"] == 3
    assert res["verified"] is True
