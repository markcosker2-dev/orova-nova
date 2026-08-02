"""Connection-pool poisoning — the cause of the silent 80% lead loss.

Found by the first real production hunt, 2026-08-02:

    -> Found 5 leads. Saving to SQLite...
    [DRIP] ... for lead 1 (SNO-KING CONSTRUCTION LLC)
    Error saving lead: database is locked      (+6s)
    Error saving lead: database is locked      (+5s)

Five leads found. ONE saved. The 5-second spacing is exactly
`PRAGMA busy_timeout=5000` elapsing, so a writer was holding the lock.

MECHANISM. _lead_repo.save_lead had `return` statements inside its
`with cls.connection()` block that neither committed nor rolled back —
including its `except` handler. A failed INSERT handed the connection back to
the pool still holding SQLite's write lock. Every later write on a different
pooled connection then blocked for busy_timeout and failed... which re-entered
that same unguarded handler and poisoned another connection. Self-amplifying:
the pool degrades until restart.

These tests reproduce the poisoning against a real SQLite pool, not a mock.
"""
import asyncio
import sqlite3

import pytest

from app.core.database import DatabaseManager

DatabaseManager.init_db()


def _write(sql, params=()):
    return asyncio.run(DatabaseManager.query(sql, params))


@pytest.fixture(autouse=True)
def _scratch_table():
    _write("CREATE TABLE IF NOT EXISTS pool_probe (id INTEGER PRIMARY KEY, v TEXT)")
    yield
    _write("DELETE FROM pool_probe")


# ── the containment guarantee ───────────────────────────────────────────────

def test_connection_holding_a_write_txn_is_rolled_back_before_pooling():
    """The core invariant: nothing re-enters the pool mid-transaction."""
    conn = DatabaseManager.get_connection()
    conn.execute("INSERT INTO pool_probe (v) VALUES ('uncommitted')")
    assert conn.in_transaction, "precondition: the write txn should be open"

    DatabaseManager.return_connection(conn)

    assert not conn.in_transaction, (
        "a connection went back to the pool still holding the write lock — "
        "this is the poisoning that cost 4 of 5 leads in production"
    )


def test_a_write_still_succeeds_after_a_connection_was_left_mid_transaction():
    """The production symptom itself: the NEXT write must not time out."""
    dirty = DatabaseManager.get_connection()
    dirty.execute("INSERT INTO pool_probe (v) VALUES ('leaked')")
    DatabaseManager.return_connection(dirty)     # poisoned, pre-fix

    out = _write("INSERT INTO pool_probe (v) VALUES ('after')")
    assert out["status"] == "ok", "the write lock was never released"


def test_the_rolled_back_work_is_actually_discarded():
    """Rollback must drop the uncommitted row, not silently commit it."""
    conn = DatabaseManager.get_connection()
    conn.execute("INSERT INTO pool_probe (v) VALUES ('should_vanish')")
    DatabaseManager.return_connection(conn)

    rows = asyncio.run(DatabaseManager.query(
        "SELECT v FROM pool_probe WHERE v = 'should_vanish'", (), fetchall=True))
    assert not rows, "uncommitted work was committed by the cleanup"


def test_committed_work_survives_the_cleanup():
    """The guard must not eat legitimately committed writes."""
    conn = DatabaseManager.get_connection()
    conn.execute("INSERT INTO pool_probe (v) VALUES ('keep_me')")
    conn.commit()
    DatabaseManager.return_connection(conn)

    rows = asyncio.run(DatabaseManager.query(
        "SELECT v FROM pool_probe WHERE v = 'keep_me'", (), fetchall=True))
    assert rows, "rollback-on-return destroyed committed data"


def test_unrollbackable_connection_is_discarded_not_pooled():
    """If we cannot clean it, drop it — never hand a poisoned conn back."""
    class _Stubborn:
        in_transaction = True

        def rollback(self):
            raise sqlite3.OperationalError("cannot rollback")

        def close(self):
            self.closed = True

    bad = _Stubborn()
    before = DatabaseManager._pool.qsize()
    DatabaseManager.return_connection(bad)
    assert DatabaseManager._pool.qsize() == before, "poisoned conn entered the pool"
    assert getattr(bad, "closed", False) is True


# ── the end-to-end symptom, through save_lead ───────────────────────────────

def _registry_lead(business: str) -> dict:
    """A lead shaped exactly like WA L&I / Yelp output: real phone, NO email."""
    return {"business": business, "owner": "Carson Keller",
            "phone": "+12538860136", "email": "", "score": 65,
            "vertical": "custom home builder"}


def test_many_email_less_leads_can_coexist():
    """THE bug behind "Found 5 leads. Saving to SQLite..." → 1 saved.

    save_lead stores `email` as '' (never NULL), and the dedup index was a
    plain UNIQUE on (lower(email), client_id). Since lower('') = '' is an
    ordinary value, the SECOND email-less lead collided with the first and was
    discarded as `[DEDUP-UNIQUE] Race caught by UNIQUE index:` — note the empty
    address after the colon, which is what disguised it as a real dedup.

    Licence registries and Yelp carry no email, so this silently capped the
    entire pipeline at one registry lead per client.
    """
    saved = [DatabaseManager.save_lead(_registry_lead(f"Registry Builders {i}"))
             for i in range(5)]
    assert all(s not in (-1, -2) for s in saved), (
        f"email-less leads are still colliding on the dedup index: {saved}"
    )
    assert len(set(saved)) == 5, f"expected 5 distinct lead ids, got {saved}"


def test_real_duplicate_emails_are_still_deduped():
    """The partial index must not weaken the guarantee it exists for."""
    lead = dict(_registry_lead("Dupe Check Construction"), email="owner@dupecheck.com")
    first = DatabaseManager.save_lead(lead)
    assert first not in (-1, -2)
    second = DatabaseManager.save_lead(dict(lead, business="Dupe Check Two"))
    assert second == -1, "a genuine duplicate address was allowed through"


# ── coverage note ───────────────────────────────────────────────────────────
# An end-to-end "make save_lead fail, then prove the next save works" test was
# attempted and deliberately dropped. Every way of forcing a failure INSIDE the
# transaction turned out to be fragile or dishonest:
#   · score=object() does not raise — sqlite3 accepted it and the save quietly
#     succeeded, so the test was asserting on a failure that never happened;
#   · sqlite3.Connection is an immutable type, so its execute() cannot be
#     patched to raise;
#   · a duplicate address cannot reach the INSERT, because save_lead's dedup
#     SELECT uses the same lower(email) comparison as the index and catches it
#     first.
# The guarantee itself is already covered directly and without mocks by
# test_a_write_still_succeeds_after_a_connection_was_left_mid_transaction,
# which reproduces the exact production symptom at the pool level. Contorting
# save_lead into failing would have tested the scaffolding, not the fix.
