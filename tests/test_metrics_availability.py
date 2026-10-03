"""A failed database read must not become a claim of an empty pipeline."""
import asyncio
import sqlite3
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.core._metrics_repo import _MetricsRepo
from app.core.database import DatabaseManager
from app.core.nova_chat import _pipeline_snapshot, pipeline_status


def test_database_failure_marks_metrics_unavailable():
    class UnavailableRepo(_MetricsRepo):
        @classmethod
        @contextmanager
        def connection(cls):
            raise sqlite3.OperationalError("database unavailable")
            yield  # pragma: no cover

    metrics = UnavailableRepo.get_metrics()
    assert metrics["metrics_available"] is False


def test_readable_empty_database_is_a_real_zero():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE leads (client_id INTEGER, status TEXT)")
    conn.execute("CREATE TABLE metrics (client_id INTEGER, metric_key TEXT, metric_value REAL, recorded_at TEXT)")

    class EmptyRepo(_MetricsRepo):
        @classmethod
        @contextmanager
        def connection(cls):
            yield conn

    try:
        metrics = EmptyRepo.get_metrics()
        assert metrics["metrics_available"] is True
        assert metrics["leads_found"] == 0
    finally:
        conn.close()


def test_telegram_status_does_not_report_fallback_zero_as_fact():
    with patch.object(DatabaseManager, "aget_metrics", AsyncMock(return_value={
        "metrics_available": False, "leads_found": 0, "meetings_booked": 0,
    })):
        response = asyncio.run(pipeline_status())
    assert "unavailable" in response.lower()
    assert "0 stored leads" not in response


def test_ai_snapshot_keeps_partial_records_without_inventing_counts():
    with patch.object(DatabaseManager, "aget_metrics", AsyncMock(return_value={
        "metrics_available": False, "leads_found": 0,
    })), patch.object(DatabaseManager, "query", AsyncMock(return_value=[{
        "business": "North Ridge Custom Homes", "status": "New", "score": 70,
    }])), patch.object(DatabaseManager, "get_state", AsyncMock(return_value={})):
        snapshot = asyncio.run(_pipeline_snapshot())
    assert "counts unavailable" in snapshot.lower()
    assert "leads: 0" not in snapshot
    assert "North Ridge Custom Homes" in snapshot
