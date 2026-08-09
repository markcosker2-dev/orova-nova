"""Deduplication must not throw away better data.

## The gap (production, 2026-08-09)

Five leads were restored from the Leads sheet carrying stale values —
`principal_count` missing entirely, and a `vertical` that was the old search
query ("luxury home remodeling washington") rather than the licensed trade.
The next hunt re-found the same five businesses WITH the correct trade and a
principal count, and `save_lead` discarded all of it, because the business
already existed.

Dedup was treating "same business" as "ignore everything new", so those rows
could never heal. Sole-owner status stayed unknown, which meant the Retell
script would keep asking a question the licence registry had already answered.

The rule now: backfill only where the incoming value is strictly better.
Never downgrade an existing row.
"""
import sqlite3
from contextlib import contextmanager

import pytest

from app.core._db_base import CANONICAL_SCHEMA_SQL


@pytest.fixture
def db(monkeypatch):
    from app.core.database import DatabaseManager
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CANONICAL_SCHEMA_SQL)

    @contextmanager
    def _fake_connection(cls=None):
        yield conn

    monkeypatch.setattr(DatabaseManager, "connection", _fake_connection)
    yield conn
    conn.close()


def _registry_lead(**over):
    lead = {
        "business": "ACCRETE CONSTRUCTION LLC", "owner": "Michael Cholerton",
        "phone": "+12532863900", "state": "WA", "email": "", "url": "", "website": "",
        "owner_source": "wa_lni", "source": "wa_lni_licences",
        "vertical": "General", "principal_count": 5,
    }
    lead.update(over)
    return lead


def _row(conn):
    return dict(conn.execute("SELECT * FROM leads WHERE id = 1").fetchone())


def test_a_rediscovery_backfills_a_missing_principal_count(db):
    """The field that decides which pain the call script opens on."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead(principal_count=0))
    assert _row(db)["principal_count"] == 0

    assert DatabaseManager.save_lead(_registry_lead(principal_count=5)) == -1
    assert _row(db)["principal_count"] == 5, "the count was discarded as a duplicate"


def test_a_registry_trade_replaces_a_stored_search_query(db):
    """The exact production shape: restored rows held the query string."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead(vertical="luxury home remodeling washington"))
    assert "luxury" in _row(db)["vertical"]

    DatabaseManager.save_lead(_registry_lead(vertical="General"))
    assert _row(db)["vertical"] == "General", "the licensed trade was discarded"


def test_a_known_principal_count_is_never_downgraded(db):
    """Backfill fills gaps; it must not overwrite a good value with a worse one."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead(principal_count=5))
    DatabaseManager.save_lead(_registry_lead(principal_count=0))
    assert _row(db)["principal_count"] == 5, "a known count was clobbered by an unknown"


def test_a_non_registry_source_cannot_overwrite_the_trade(db):
    """Only a licence registry publishes an authoritative trade. A web search
    supplies the query it was found with, which is not a fact about the firm."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead(vertical="General"))
    DatabaseManager.save_lead(_registry_lead(
        vertical="roofing seattle", owner_source="", source="Web Search"))
    assert _row(db)["vertical"] == "General", "a search query overwrote the licensed trade"


def test_the_row_is_still_deduplicated(db):
    """Backfilling must not accidentally start inserting duplicates."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead())
    DatabaseManager.save_lead(_registry_lead())
    DatabaseManager.save_lead(_registry_lead())
    n = db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    assert n == 1, f"dedup broke — {n} rows"


def test_a_backfill_failure_never_loses_the_dedup(db, monkeypatch):
    """Fail-open: a bad UPDATE must not turn a harmless duplicate into chaos."""
    from app.core.database import DatabaseManager
    DatabaseManager.save_lead(_registry_lead())

    def _boom(*a, **k):
        raise RuntimeError("update exploded")

    monkeypatch.setattr(DatabaseManager, "_backfill_registry_fields", _boom)
    assert DatabaseManager.save_lead(_registry_lead()) == -1
    assert db.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1
