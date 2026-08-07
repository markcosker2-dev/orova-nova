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
from unittest.mock import AsyncMock, patch

import pytest

from app.core import durability


@pytest.fixture
def db_with(monkeypatch):
    """Fake DB holding `n` leads, and a sync that always claims success."""
    def _make(n_leads):
        rows = [{"id": i, "business": f"Biz {i}", "url": f"https://b{i}.com"}
                for i in range(1, n_leads + 1)]

        async def _query(sql, params=None, fetchall=False):
            return rows

        async def _fetchone(sql, params=None):
            return {"c": n_leads}

        monkeypatch.setattr(durability.__dict__.get("DatabaseManager", object), "x", None, raising=False)
        return rows, _query, _fetchone
    return _make


def _run(sheet_rows, n_leads):
    """Run persist_leads_durably with a sheet that reports `sheet_rows`."""
    rows = [{"id": i, "business": f"Biz {i}", "url": f"https://b{i}.com"}
            for i in range(1, n_leads + 1)]

    class _DB:
        @staticmethod
        async def query(sql, params=None, fetchall=False):
            return rows

        @staticmethod
        async def fetchone(sql, params=None):
            return {"c": n_leads}

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


def test_drive_being_dead_still_does_not_gate_sheets():
    """The regression that started all of this: Drive must never suppress Tier 1."""
    res = _run(sheet_rows=3, n_leads=3)
    assert res["drive"] is False
    assert res["sheets_synced"] == 3
    assert res["verified"] is True
