"""Unified SDR event log (ADR-0007). Additive spine — these tests pin:
table creation is idempotent, logging round-trips, fetch filters work, and
logging is fail-open (a broken DB never raises into the pipeline)."""
import asyncio
import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

from app.core import event_log
from app.core.database import DatabaseManager

@pytest.fixture(autouse=True)
def isolated_event_database(monkeypatch):
    """Exercise real SQLite event writes without touching the application DB."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    async def query(sql, params=(), fetchone=False, fetchall=False):
        cur = conn.execute(sql, params)
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        conn.commit()
        return {"status": "ok", "rows_affected": cur.rowcount}

    monkeypatch.setattr(DatabaseManager, "query", query)
    yield
    conn.close()


def test_ensure_events_table_idempotent():
    assert asyncio.run(event_log.ensure_events_table()) is True
    assert asyncio.run(event_log.ensure_events_table()) is True  # second run: no error


def test_log_and_fetch_roundtrip():
    asyncio.run(event_log.ensure_events_table())
    assert asyncio.run(event_log.alog_event(99001, "outreach_sent", "courier",
                                           payload={"to": "x@y.com"}, variant_id="pas")) is True
    rows = asyncio.run(event_log.aget_events(prospect_id=99001))
    assert rows, "event not found after logging"
    ev = rows[0]
    assert ev["event_type"] == "outreach_sent"
    assert ev["agent"] == "courier"
    assert ev["variant_id"] == "pas"
    assert json.loads(ev["payload"])["to"] == "x@y.com"


def test_fetch_filters_by_type():
    asyncio.run(event_log.ensure_events_table())
    asyncio.run(event_log.alog_event(99002, "lead_discovered", "scout"))
    asyncio.run(event_log.alog_event(99002, "outreach_sent", "courier"))
    only_sent = asyncio.run(event_log.aget_events(prospect_id=99002, event_type="outreach_sent"))
    assert only_sent and all(e["event_type"] == "outreach_sent" for e in only_sent)


def test_logging_is_fail_open():
    """A broken DB must never raise into the pipeline (sends > telemetry)."""
    with patch.object(event_log.DatabaseManager, "query",
                      new=AsyncMock(side_effect=RuntimeError("db down"))):
        assert asyncio.run(event_log.alog_event(1, "outreach_sent", "courier")) is False
        assert asyncio.run(event_log.aget_events()) == []                  # no raise
        assert asyncio.run(event_log.ensure_events_table()) is False       # reported, not raised
