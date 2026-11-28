"""Pool reset must never deadlock startup (2026-11-27).

On the starlette 1.x / anyio 4 stack a real credential-less boot hung ~1 in 4
times in the failed-Drive-restore branch of app.main's lifespan:

    queue.put  <- _init_sqlite_fallback  <- reset_sqlite_fresh

`_close_all_connections` drained the queue, but a thread still holding a
connection returned it afterwards, so refilling the SAME bounded queue with a
blocking put() stalled on the last slot forever. Tests never saw it because
they patch the lifespan out.

These tests drive the real pool against a scratch SQLite file and run each
re-init in a thread with a timeout, so a regression fails instead of hanging.
"""
import queue
import threading
import time

import pytest

from app.core.database import DatabaseManager


@pytest.fixture
def pool(tmp_path):
    """An isolated pool on a scratch DB. Subclass attributes shadow the real
    DatabaseManager's, so the shared on-disk pool is untouched."""

    class _ScratchDB(DatabaseManager):
        pass

    _ScratchDB._db_path = str(tmp_path / "scratch.db")
    _ScratchDB._pool = queue.Queue(maxsize=10)
    _ScratchDB._pool_lock = threading.Lock()
    _ScratchDB._max_connections = 10
    _ScratchDB._active_connections = 0
    _ScratchDB._live_conns = set()
    _ScratchDB._init_sqlite_fallback()
    yield _ScratchDB
    _ScratchDB._close_all_connections()


def _finishes(fn, timeout=10.0):
    t = threading.Thread(target=fn, daemon=True)
    t.start()
    t.join(timeout)
    return not t.is_alive()


def test_reinit_after_late_return_does_not_block(pool):
    """The exact production race: drain, a straggler returns, then refill."""
    held = pool.get_connection()          # a worker thread mid-query
    pool._close_all_connections()         # restore/reset drains the pool
    pool.return_connection(held)          # the worker finishes late
    assert _finishes(pool._init_sqlite_fallback), "pool re-init deadlocked"
    assert pool._pool.qsize() == pool._max_connections


def test_reset_sqlite_fresh_with_connections_checked_out(pool):
    held = [pool.get_connection() for _ in range(3)]

    def returner():
        for c in held:
            time.sleep(0.005)
            pool.return_connection(c)

    t = threading.Thread(target=returner)
    t.start()                             # returns race the reset
    assert _finishes(pool.reset_sqlite_fresh), "reset deadlocked"
    t.join(5)
    assert pool._pool.qsize() == pool._max_connections
    assert pool._active_connections == 0


def test_stale_connection_is_closed_not_repooled(pool):
    """A connection from before a reset points at a deleted file: it must be
    closed on return, never handed to the next caller."""
    stale = pool.get_connection()
    assert _finishes(pool.reset_sqlite_fresh)
    pool.return_connection(stale)
    pooled = [pool._pool.get_nowait() for _ in range(pool._pool.qsize())]
    assert all(c is not stale for c in pooled)
    for c in pooled:
        pool._pool.put_nowait(c)
    with pytest.raises(Exception):
        stale.execute("SELECT 1")         # closed


def test_pool_still_works_after_reset(pool):
    assert _finishes(pool.reset_sqlite_fresh)
    with pool.connection() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS probe (v TEXT)")
        conn.execute("INSERT INTO probe VALUES ('ok')")
        conn.commit()
    with pool.connection() as conn:
        assert conn.execute("SELECT v FROM probe").fetchone()[0] == "ok"
    assert pool._pool.qsize() == pool._max_connections


def test_app_does_not_hijack_uvicorn_sigterm():
    """loop.add_signal_handler(SIGTERM, ...) on the server loop replaces
    uvicorn's handler, so a redeploy's SIGTERM never shut the app down and the
    shutdown backup never ran (found on a real boot, 2026-11-27). uvicorn must
    own SIGTERM."""
    import inspect
    import re

    import app.core._db_base as db_base
    import app.main as main_module

    pattern = re.compile(r"add_signal_handler\(\s*signal\.SIGTERM")
    for mod in (main_module, db_base):
        assert not pattern.search(inspect.getsource(mod)), mod.__name__
    assert not hasattr(DatabaseManager, "register_sigterm_handler")
