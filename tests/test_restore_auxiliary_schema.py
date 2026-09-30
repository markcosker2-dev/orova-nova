"""Restore adoption must ensure both schemas, without starting the service."""
import ast
import asyncio
import inspect
import sqlite3
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def main_module():
    with patch("dotenv.load_dotenv", return_value=False):
        from app import main
    return main


def test_old_restored_snapshot_gets_both_auxiliary_schemas(main_module):
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE preserved (value TEXT)")
    connection.execute("INSERT INTO preserved VALUES ('snapshot data')")
    connection.commit()

    @contextmanager
    def isolated_connection():
        yield connection

    with patch.object(main_module.DatabaseManager, "connection", isolated_connection):
        assert asyncio.run(main_module._ensure_auxiliary_restore_schema()) is True
        assert asyncio.run(main_module._ensure_auxiliary_restore_schema()) is True
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"events", "execution_traces", "learned_skills", "user_preferences"} <= names
    assert connection.execute("SELECT value FROM preserved").fetchone()[0] == "snapshot data"
    connection.close()


@pytest.mark.parametrize("event_result", [False, RuntimeError("schema unavailable")])
def test_auxiliary_failure_is_observable_and_does_not_reset_snapshot(main_module, event_result):
    events = AsyncMock(side_effect=event_result) if isinstance(event_result, Exception) else AsyncMock(return_value=event_result)
    with patch("app.core.event_log.ensure_events_table", events), \
         patch("app.core.self_learning.ensure_tables", AsyncMock(return_value=True)) as learning, \
         patch.object(main_module.DatabaseManager, "reset_sqlite_fresh") as reset:
        assert asyncio.run(main_module._ensure_auxiliary_restore_schema()) is False
        learning.assert_awaited_once()
        reset.assert_not_called()


def test_both_restore_branches_call_auxiliary_bootstrap(main_module):
    # Wiring check complements the executable helper tests. Never run lifespan:
    # that would register a webhook and start background jobs.
    tree = ast.parse(inspect.getsource(main_module.lifespan))
    restore_decisions = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                         and ast.unparse(node.test) in {"restore_res.get('ok')", "not restored_ok"}]
    assert len(restore_decisions) == 2
    for branch in restore_decisions:
        assert any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "_ensure_auxiliary_restore_schema" for node in ast.walk(branch))
