"""Offline persistence regressions with controlled worker/API overlap."""
import asyncio
import re
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import self_learning
from app.core.database import DatabaseManager
from app.skills import sheets_sync as sheets
from app.skills import vault_skill as vault


class _Worksheet:
    def __init__(self):
        self.rows = [list(sheets.WORKSHEET_HEADERS["Leads"])]
        self.guard = threading.Lock()
        self.write_started = threading.Event()
        self.release_write = threading.Event()
        self.write_finished = threading.Event()
        self.second_read = threading.Event()
        self.reads = 0
        self.writes = 0

    def col_values(self, column):
        with self.guard:
            self.reads += 1
            if self.reads > 1:
                self.second_read.set()
            return [row[column - 1] for row in self.rows]

    def update(self, *, values, range_name):
        with self.guard:
            self.writes += 1
            first = self.writes == 1
        if first:
            self.write_started.set()
            assert self.release_write.wait(4), "test did not release first write"
        row_number = int(re.search(r"A(\d+):", range_name).group(1))
        with self.guard:
            while len(self.rows) < row_number:
                self.rows.append([""] * len(self.rows[0]))
            self.rows[row_number - 1] = list(values[0])
        if first:
            self.write_finished.set()
        return {}


@pytest.mark.parametrize("worker_loop", [False, True], ids=["api-loop", "worker-loop"])
@pytest.mark.parametrize("same_identity", [False, True], ids=["distinct", "same-identity"])
def test_concurrent_sheet_sync_preserves_lead_identities(monkeypatch, worker_loop, same_identity):
    ws = _Worksheet()
    monkeypatch.setattr(sheets, "_get_worksheet", AsyncMock(return_value=ws))
    monkeypatch.setattr(sheets.random, "uniform", lambda *args: 0)
    first = {"id": 1, "business": "Alpha Builders", "status": "New"}
    second = {"id": 2, "business": "Alpha Builders" if same_identity else "Beta Builders",
              "status": "Contacted"}

    async def scenario():
        a = asyncio.create_task(sheets.sync_lead_to_sheets(first))
        assert await asyncio.to_thread(ws.write_started.wait, 3)
        second_started = asyncio.Event()

        async def run_second():
            second_started.set()
            if worker_loop:
                return await asyncio.to_thread(
                    lambda: asyncio.run(asyncio.wait_for(sheets.sync_lead_to_sheets(second), 3)))
            return await sheets.sync_lead_to_sheets(second)

        b = asyncio.create_task(run_second())
        await second_started.wait()
        try:
            # The old path reads stale row allocation while A is paused. A
            # serialized implementation cannot perform that second read yet.
            await asyncio.to_thread(ws.second_read.wait, 0.15)
            # The event loop remains responsive while the worker waits.
            await asyncio.wait_for(asyncio.sleep(0.01), 0.2)
        finally:
            ws.release_write.set()
        return await asyncio.wait_for(asyncio.gather(a, b), 4)

    results = asyncio.run(scenario())
    assert all(result["ok"] for result in results), results
    stored = [row[1] for row in ws.rows[1:]]
    if same_identity:
        assert stored == ["Alpha Builders"]
        assert ws.rows[1][7] == "Contacted"
    else:
        assert sorted(stored) == ["Alpha Builders", "Beta Builders"]
        assert results[0]["row"] != results[1]["row"]
    assert ws.rows[0] == sheets.WORKSHEET_HEADERS["Leads"]


def test_cancelled_sheet_waiter_does_not_release_an_inflight_write(monkeypatch):
    ws = _Worksheet()
    monkeypatch.setattr(sheets, "_get_worksheet", AsyncMock(return_value=ws))
    monkeypatch.setattr(sheets.random, "uniform", lambda *args: 0)

    async def scenario():
        a = asyncio.create_task(sheets.sync_lead_to_sheets({"business": "Alpha Builders"}))
        assert await asyncio.to_thread(ws.write_started.wait, 3)
        a.cancel()
        with pytest.raises(asyncio.CancelledError):
            await a
        b = asyncio.create_task(sheets.sync_lead_to_sheets({"business": "Beta Builders"}))
        try:
            await asyncio.to_thread(ws.second_read.wait, 0.15)
        finally:
            ws.release_write.set()
        result = await asyncio.wait_for(b, 4)
        assert await asyncio.to_thread(ws.write_finished.wait, 3)
        return result

    assert asyncio.run(scenario())["ok"] is True
    assert sorted(row[1] for row in ws.rows[1:]) == ["Alpha Builders", "Beta Builders"]


@pytest.fixture
def source_db(monkeypatch, tmp_path):
    path = tmp_path / "source.db"
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE snapshot_marker (value TEXT)")
    con.execute("INSERT INTO snapshot_marker VALUES ('first')")
    con.commit()
    monkeypatch.setattr(vault, "DB_PATH", str(path))
    monkeypatch.chdir(tmp_path)  # also isolates the old shared scratch path
    yield con, path
    con.close()


class _Media:
    def __init__(self, source, **kwargs):
        self.stream = source if hasattr(source, "read") else None
        self.path = Path(source.name if self.stream else source)


def _mock_drive(monkeypatch, execute):
    class Service:
        def files(self):
            return self

        def create(self, *, body, media_body, fields):
            class Upload:
                def execute(self):
                    return execute(media_body)
            return Upload()

    monkeypatch.setattr(vault, "_get_drive_service", Service)
    monkeypatch.setattr(vault, "_get_or_create_folder", lambda service: "test-folder")
    monkeypatch.setattr(vault, "_prune_old_backups", lambda *args: None)
    monkeypatch.setattr(vault, "MediaFileUpload", _Media, raising=False)
    monkeypatch.setattr(vault, "MediaIoBaseUpload", _Media, raising=False)


def _read_marker(media):
    assert media.path.exists(), "worker snapshot was deleted during upload"
    if media.stream is not None:
        media.stream.seek(0)
        data = media.stream.read()
    else:
        data = media.path.read_bytes()  # also exercises the old upload path
    assert data == media.path.read_bytes(), "upload stream does not match its snapshot"
    with closing(sqlite3.connect(media.path)) as con:
        return con.execute("SELECT value FROM snapshot_marker").fetchone()[0]


@pytest.mark.parametrize("worker_loop", [False, True], ids=["api-loop", "worker-loop"])
def test_overlapping_backups_upload_their_own_snapshots_and_cleanup(monkeypatch, source_db, worker_loop):
    source, _ = source_db
    starts = [threading.Event(), threading.Event()]
    releases = [threading.Event(), threading.Event()]
    guard = threading.Lock()
    media_seen, values = [], {}

    def execute(media):
        with guard:
            index = len(media_seen)
            media_seen.append(media)
        starts[index].set()
        assert releases[index].wait(4), "test did not release upload"
        values[index] = _read_marker(media)
        return {"id": str(index), "name": "mock-snapshot"}

    _mock_drive(monkeypatch, execute)

    async def scenario():
        a = asyncio.create_task(vault.backup_database())
        assert await asyncio.to_thread(starts[0].wait, 3)
        source.execute("UPDATE snapshot_marker SET value='second'")
        source.commit()
        async def second_backup():
            if worker_loop:
                return await asyncio.to_thread(lambda: asyncio.run(vault.backup_database()))
            return await vault.backup_database()

        b = asyncio.create_task(second_backup())
        try:
            assert await asyncio.to_thread(starts[1].wait, 3)
            releases[0].set()
            first_result = await asyncio.wait_for(a, 3)
            releases[1].set()
            return first_result, await asyncio.wait_for(b, 3)
        finally:
            for release in releases:
                release.set()

    results = asyncio.run(scenario())
    assert all(result["ok"] for result in results), results
    assert values == {0: "first", 1: "second"}
    assert len({media.path for media in media_seen}) == 2
    assert all(not media.path.exists() for media in media_seen)
    assert all(media.stream is not None and media.stream.closed for media in media_seen)


def test_cancelled_backup_keeps_snapshot_until_upload_worker_finishes(monkeypatch, source_db):
    started, release, read_finished = threading.Event(), threading.Event(), threading.Event()
    worker_finished = threading.Event()
    worker_results = []
    media_seen, values = [], []
    real_backup = vault._backup_database_sync

    def observed_worker():
        try:
            result = real_backup()
            worker_results.append(result)
            return result
        finally:
            worker_finished.set()

    monkeypatch.setattr(vault, "_backup_database_sync", observed_worker)

    def execute(media):
        media_seen.append(media)
        started.set()
        assert release.wait(4), "test did not release upload"
        values.append(_read_marker(media))
        read_finished.set()
        return {"id": "test"}

    _mock_drive(monkeypatch, execute)

    async def scenario():
        task = asyncio.create_task(vault.backup_database())
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        try:
            assert media_seen[0].path.exists(), "cancellation deleted an in-use snapshot"
        finally:
            release.set()
        assert await asyncio.to_thread(read_finished.wait, 3)
        # Upload reading is not worker completion. Observe real cleanup rather
        # than relying on a previous fixture's event-loop executor shutdown.
        assert await asyncio.to_thread(worker_finished.wait, 3)

    asyncio.run(scenario())  # waits for executor work and worker cleanup too
    assert values == ["first"]
    assert len(worker_results) == 1 and worker_results[0]["ok"] is True
    assert not media_seen[0].path.exists()
    assert media_seen[0].stream is not None and media_seen[0].stream.closed


@pytest.mark.parametrize("failure", ["copy", "upload"])
def test_failed_backup_closes_connections_streams_and_removes_scratch(monkeypatch, source_db, failure):
    connections, snapshots, media_seen = [], [], []
    real_connect = sqlite3.connect

    class Connection:
        def __init__(self, database, *args, **kwargs):
            self.real = real_connect(database, *args, **kwargs)
            self.closed = False
            if len(connections) == 1:
                snapshots.append(Path(database))
            connections.append(self)

        def backup(self, destination):
            if failure == "copy":
                raise RuntimeError("controlled copy failure")
            self.real.backup(destination.real)

        def close(self):
            self.real.close()
            self.closed = True

        def __enter__(self):
            self.real.__enter__()
            return self

        def __exit__(self, *args):
            return self.real.__exit__(*args)

    def execute(media):
        media_seen.append(media)
        raise RuntimeError("controlled upload failure")

    _mock_drive(monkeypatch, execute)
    monkeypatch.setattr(vault.sqlite3, "connect", Connection)
    try:
        result = asyncio.run(vault.backup_database())
        assert result["ok"] is False and failure in result["error"]
        assert len(connections) == 2 and all(con.closed for con in connections)
        assert snapshots and all(not path.exists() for path in snapshots)
        assert all(media.stream is not None and media.stream.closed for media in media_seen)
    finally:
        # The negative control runs against the old leaking implementation too.
        for con in connections:
            if not con.closed:
                con.close()


def test_missing_backup_source_does_not_create_a_database(monkeypatch, tmp_path):
    missing = tmp_path / "absent.db"
    monkeypatch.setattr(vault, "DB_PATH", str(missing))
    monkeypatch.chdir(tmp_path)
    service = MagicMock()
    monkeypatch.setattr(vault, "_get_drive_service", service)
    result = asyncio.run(vault.backup_database())
    assert result["ok"] is False
    assert not missing.exists()
    service.assert_not_called()


@pytest.fixture
def learning_db(monkeypatch):
    con = sqlite3.connect(":memory:", check_same_thread=False)
    con.row_factory = sqlite3.Row

    @contextmanager
    def connection():
        yield con

    monkeypatch.setattr(DatabaseManager, "connection", connection)
    yield con
    con.close()


def test_learning_bootstrap_is_idempotent_and_trace_round_trips(learning_db):
    async def scenario():
        result = await self_learning.ensure_tables()
        tables = {r[0] for r in learning_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"execution_traces", "learned_skills", "user_preferences"} <= tables
        assert result is True
        assert await self_learning.ensure_tables() is True
        indexes = {r[0] for r in learning_db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_traces_client_ts", "idx_traces_hash", "idx_skills_category", "idx_prefs_client"} <= indexes
        trace = self_learning.ExecutionTrace(
            session_id="test-session", agent_id="nova", goal="draft a researched opening",
            tool_sequence=["research_lead", "write_content"], outcome="completed",
            total_steps=2, total_latency_ms=15, metadata={"reviewed": True})
        await self_learning.SelfLearningLoop().record_trace(trace)
        stored = await DatabaseManager.fetchone("SELECT * FROM execution_traces WHERE session_id=?", (trace.session_id,))
        assert stored["outcome"] == "completed"
        assert stored["tool_sequence"] == '["research_lead", "write_content"]'
        assert stored["metadata"] == '{"reviewed": true}'

    asyncio.run(scenario())


def test_failed_learning_bootstrap_reports_failure(monkeypatch):
    query = AsyncMock(side_effect=sqlite3.OperationalError("controlled schema failure"))
    monkeypatch.setattr(DatabaseManager, "query", query)
    with pytest.raises(RuntimeError, match="Learning schema initialization failed"):
        asyncio.run(self_learning.ensure_tables())
