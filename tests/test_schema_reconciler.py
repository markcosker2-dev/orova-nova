"""Schema reconciler + scheduler containment (2026-07-19 prod incident).

A Drive-restored snapshot predating several columns put production into a
1-second scheduler loop: the Lane-7 health check raised `no such column:
updated_at`, the schedule library never advanced its next_run, and the raise
aborted run_pending() so every other lane — including the 3-hourly backup —
starved. Two compounding causes, both pinned here:

1. The old hand-maintained migration list was missing metrics.metric_key /
   metrics.recorded_at / state_store.updated_at entirely, and its
   `DEFAULT CURRENT_TIMESTAMP` entries were silently rejected by SQLite
   (ALTER TABLE ADD COLUMN allows only constant defaults) under a bare
   except. Fix: _migrate_columns now diffs every table against a reference
   DB built from CANONICAL_SCHEMA_SQL.
2. A raising lane job wedged the whole scheduler. Fix: _safe_job contains
   lane exceptions so schedule always advances next_run.
"""
import sqlite3

import pytest

from app.core.database import DatabaseManager

# The leads/metrics/state_store shapes of the restored production snapshot
# (pre-updated_at, pre-metric_key era). Other tables are omitted on purpose:
# _init_tables must create them from scratch alongside reconciling these.
OLD_SNAPSHOT_SCHEMA = """
    CREATE TABLE leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business TEXT,
        owner TEXT,
        url TEXT,
        website TEXT,
        email TEXT,
        phone TEXT,
        vertical TEXT,
        status TEXT DEFAULT 'New',
        notes TEXT,
        icebreaker TEXT,
        score REAL DEFAULT 0,
        client_id INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER DEFAULT 0,
        metric_value REAL DEFAULT 0
    );
    CREATE TABLE state_store (
        key TEXT PRIMARY KEY,
        value TEXT
    );
"""


@pytest.fixture
def old_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "old_snapshot.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(OLD_SNAPSHOT_SCHEMA)
    conn.execute(
        "INSERT INTO leads (business, email, status) VALUES ('Legacy Motors', 'a@b.com', 'Contacted')"
    )
    conn.commit()
    yield conn
    conn.close()


def _cols(conn, table):
    return {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')}


def test_reconciler_adds_all_missing_columns(old_db):
    DatabaseManager._init_tables(old_db)
    assert "updated_at" in _cols(old_db, "leads")
    assert {"metric_key", "recorded_at"} <= _cols(old_db, "metrics")
    assert "updated_at" in _cols(old_db, "state_store")
    # Migration-era columns folded into the canonical schema arrive too.
    assert {"email_status", "owner_title", "linkedin_url"} <= _cols(old_db, "leads")


def test_reconciler_preserves_existing_rows(old_db):
    DatabaseManager._init_tables(old_db)
    row = old_db.execute("SELECT business, email FROM leads").fetchone()
    assert (row["business"], row["email"]) == ("Legacy Motors", "a@b.com")


def test_prod_failing_statements_run_after_reconcile(old_db):
    """The three statements that raised in production on 2026-07-19."""
    DatabaseManager._init_tables(old_db)
    old_db.execute(
        "SELECT COUNT(*) as cnt FROM leads WHERE status IN ('Email Sent', 'Contacted')"
        " AND datetime(updated_at) < datetime('now', '-2 days')"
    ).fetchone()
    old_db.execute(
        "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'calls_made'"
        " ORDER BY recorded_at DESC LIMIT 1",
        (0,),
    ).fetchone()
    old_db.execute(
        "INSERT OR REPLACE INTO state_store (key, value, updated_at)"
        " VALUES ('k', 'v', CURRENT_TIMESTAMP)"
    )


def test_reconciler_idempotent_on_fresh_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "fresh.db"))
    conn.row_factory = sqlite3.Row
    try:
        DatabaseManager._init_tables(conn)
        DatabaseManager._init_tables(conn)  # second run: no error, no change
        assert "metric_key" in _cols(conn, "metrics")
        assert "updated_at" in _cols(conn, "leads")
    finally:
        conn.close()


def test_missing_tables_are_created(old_db):
    """Tables absent from the old snapshot must be created outright."""
    DatabaseManager._init_tables(old_db)
    tables = {
        r["name"]
        for r in old_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"outreach_outcomes", "learned_strategies", "drip_campaigns"} <= tables


def test_safe_job_contains_exceptions():
    from app.worker import _safe_job

    def boom():
        raise RuntimeError("lane blew up")

    _safe_job(boom)  # must not raise — a failing lane stays on cadence


def test_safe_job_runs_the_job():
    from app.worker import _safe_job

    ran = []
    _safe_job(lambda: ran.append(True))
    assert ran == [True]
