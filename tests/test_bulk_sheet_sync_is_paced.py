"""A bulk resync must stay inside Google's Sheets read quota.

`sync_lead_to_sheets` costs a READ (find the row) plus a WRITE. Google's
default is 60 read requests per minute per user. A hunt syncs five leads and
never noticed; the full resync added in #174 syncs every lead and burst
straight through it:

    [SheetsSync] APIError: [429]: Quota exceeded for quota metric 'Read requests'
    [DURABILITY:resync] 📋 Sheets: 33/40 leads synced
    [DURABILITY:resync] ⚠️ could not verify the Sheets backup

Two consecutive passes each stalled around 33-34 of 40. The operation could
never finish, and the rows it dropped were the ones still missing the new
column — precisely the rows it existed to repair.

The write path already retries 429s with exponential backoff, but backoff
cannot rescue a burst that is over quota from the first second, and the READ
side has no backoff at all.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.core import durability as d


def _rows(n):
    return [{"id": i, "business": f"FIXTURE {i}", "status": "New"} for i in range(n)]


def _run(n, sleeps):
    async def _fake_sync(lead):
        return {"ok": True}

    async def _fake_sleep(s):
        sleeps.append(s)

    class _DB:
        @staticmethod
        async def query(sql, params=None, fetchall=False):
            return _rows(n)

    with patch("app.core.database.DatabaseManager", _DB), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", _fake_sync), \
         patch("app.skills.sheets_sync.count_lead_rows", side_effect=RuntimeError("skip")), \
         patch.object(d.asyncio, "sleep", _fake_sleep):
        return asyncio.run(d.persist_leads_durably(recent_count=n, source="test"))


def test_a_bulk_run_is_paced():
    sleeps = []
    res = _run(40, sleeps)
    assert res["sheets_synced"] == 40, "every lead must be written, not 33 of 40"
    assert len(sleeps) == 39, "one pause between leads, none before the first"
    assert all(s == d.SHEETS_SYNC_PACING_S for s in sleeps)


def test_the_pacing_stays_under_the_read_quota():
    """40 leads at the configured pace must not exceed ~60 reads/minute."""
    reads_per_minute = 60 / d.SHEETS_SYNC_PACING_S
    assert reads_per_minute < 60, (
        f"{reads_per_minute:.0f} reads/min still bursts the quota"
    )


def test_a_hunt_sized_run_is_not_slowed():
    """Five leads were never near the quota; pacing there is pure latency."""
    sleeps = []
    res = _run(5, sleeps)
    assert res["sheets_synced"] == 5
    assert sleeps == [], "a hunt must not pay for the resync's problem"


def test_the_threshold_is_the_boundary():
    below, at = [], []
    _run(d.SHEETS_PACING_THRESHOLD - 1, below)
    _run(d.SHEETS_PACING_THRESHOLD, at)
    assert below == []
    assert len(at) == d.SHEETS_PACING_THRESHOLD - 1
