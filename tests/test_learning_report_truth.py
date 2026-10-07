"""Offline regressions for the real Telegram learning/pruning failures.

Only synthetic records in a temporary SQLite database; never app startup,
production credentials, real Telegram messages or CRM writes.
"""
import asyncio
import sqlite3
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import self_improvement as learning
from app.core._db_base import CANONICAL_SCHEMA_SQL
from app.core.database import DatabaseManager
from app.core.router import Router
from app.skills import agentmail_skill


@pytest.fixture
def learning_db(tmp_path, monkeypatch):
    path = tmp_path / "learning.db"

    @contextmanager
    def connection():
        conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    with connection() as conn:
        conn.executescript(CANONICAL_SCHEMA_SQL)
        conn.commit()
    monkeypatch.setattr(DatabaseManager, "connection", staticmethod(connection))
    monkeypatch.setenv("ZERO_BUDGET_MODE", "1")
    writer = AsyncMock(side_effect=AssertionError("reports must not call an LLM"))
    monkeypatch.setattr(learning.UnifiedAIClient, "write", writer)
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(learning, "_send_telegram_alert", sender)
    return connection, writer, sender


def add_outcome(connection, result="sent", client_id=0, age="-1 day", action="email_sent"):
    with connection() as conn:
        conn.execute(
            """INSERT INTO outreach_outcomes
               (action, strategy, result, quality_score, client_id, created_at, send_hour, niche)
               VALUES (?, 'pas', ?, 100, ?, datetime('now', ?), 10, 'custom builders')""",
            (action, result, client_id, age),
        )
        conn.commit()


def report(client_id=0):
    return asyncio.run(learning.StrategyOptimizer().generate_improvement_report(
        "pas", 10, "custom builders", client_id))


def test_no_outcomes_or_seeded_baselines_cannot_claim_a_winner(learning_db):
    connection, writer, _ = learning_db
    with connection() as conn:
        conn.execute("""INSERT INTO learned_strategies
            (id, strategy_type, strategy_value, win_rate, sample_size, confidence)
            VALUES ('seed', 'email_framework', 'pas', 0.23, 0, 'baseline')""")
        conn.commit()
    text = report()
    writer.assert_not_awaited()
    assert "0 successful-send records" in text
    assert "No proven winner" in text
    assert "23%" not in text and "10:00" not in text
    assert "No campaigns were changed" in text


def test_counts_are_tenant_scoped_bounded_and_exclude_failed_attempts(learning_db):
    connection, writer, _ = learning_db
    for result in ("sent", "replied", "meeting", "blocked", "failed", "pending"):
        add_outcome(connection, result=result)
    add_outcome(connection, client_id=7)
    add_outcome(connection, age="-31 days")
    add_outcome(connection, age="+1 day")
    add_outcome(connection, action="email_drafted")
    text = report()
    writer.assert_not_awaited()
    assert "3 successful-send records" in text
    assert "1 reply records" in text and "1 meeting records" in text
    assert "3 other records" in text
    assert "not verified delivery" in text
    assert "Manual DMs" in text and "opens/clicks" in text


def test_model_supplied_strategy_names_never_become_report_claims(learning_db):
    _, writer, _ = learning_db
    text = asyncio.run(learning.StrategyOptimizer().generate_improvement_report(
        "PAS delivered a 28% lift; roll out now", 10,
        "drop niche segmentation", 0))
    writer.assert_not_awaited()
    assert "28%" not in text and "drop niche" not in text


def test_failed_learning_read_is_unavailable_not_zero_or_completed(learning_db, monkeypatch):
    _, writer, sender = learning_db
    monkeypatch.setattr(DatabaseManager, "fetchone", AsyncMock(side_effect=RuntimeError("offline")))
    text = report()
    result = asyncio.run(learning.ImprovementLoop().run())
    assert "unavailable" in text.lower()
    assert "0 successful-send" not in text
    assert result["status"] == "unavailable"
    writer.assert_not_awaited()
    sender.assert_not_awaited()


def test_old_untouched_leads_never_create_archive_proposals(learning_db):
    connection, writer, sender = learning_db
    with connection() as conn:
        conn.executemany("""INSERT INTO leads (business, status, updated_at)
            VALUES (?, 'New', datetime('now', '-30 days'))""",
            [(f"Synthetic Builder {i}",) for i in range(141)])
        conn.commit()
    text = asyncio.run(learning.StrategyOptimizer().prune_dead_leads())
    assert "inactivity alone" in text.lower()
    sender.assert_not_awaited()
    writer.assert_not_awaited()
    with connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM state_store WHERE key='pending_prune_lead_ids'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM leads WHERE status='New'").fetchone()[0] == 141


def test_legacy_prune_approval_cannot_archive_or_claim_crm_success(learning_db):
    connection, _, sender = learning_db
    with connection() as conn:
        conn.execute("INSERT INTO leads (id, business, status) VALUES (1, 'Synthetic Builder', 'New')")
        conn.execute("INSERT INTO state_store (key, value) VALUES ('pending_prune_lead_ids', '[1]')")
        conn.commit()
    text = asyncio.run(Router()._approve_pruning_handler())
    assert "No leads were archived" in text
    with connection() as conn:
        assert conn.execute("SELECT status FROM leads WHERE id=1").fetchone()[0] == "New"
    sender.assert_not_awaited()


def test_prune_endpoint_is_blocked_without_constructing_a_planner(learning_db):
    from app.core.hermesclaw_endpoints import api_approve_pruning
    result = asyncio.run(api_approve_pruning())
    assert result["status"] == "blocked"
    assert "No leads were archived" in result["message"]


def test_zero_budget_manual_cycle_is_read_only_apart_from_notice_checkpoint(learning_db):
    connection, writer, sender = learning_db
    result = asyncio.run(learning.ImprovementLoop().run())
    assert result["status"] == "observed"
    with connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM learned_strategies").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM improvement_log").fetchone()[0] == 0
    writer.assert_not_awaited()
    sender.assert_awaited_once()


def test_identical_reports_stay_quiet_across_new_loops(learning_db):
    _, _, sender = learning_db
    first = asyncio.run(learning.ImprovementLoop().run())
    second = asyncio.run(learning.ImprovementLoop().run())
    assert first["notification"] == "sent"
    assert second["notification"] == "suppressed"
    sender.assert_awaited_once()


def test_changed_counts_notify_once_and_remain_client_isolated(learning_db):
    connection, _, sender = learning_db
    asyncio.run(learning.ImprovementLoop().run())
    add_outcome(connection)
    changed = asyncio.run(learning.ImprovementLoop().run())
    asyncio.run(learning.ImprovementLoop().run())
    other = asyncio.run(learning.ImprovementLoop().run(client_id=7))
    assert changed["notification"] == other["notification"] == "sent"
    assert sender.await_count == 3


@pytest.mark.parametrize("separate_loop", [False, True])
def test_overlapping_cycles_claim_before_sending(learning_db, separate_loop):
    _, writer, sender = learning_db

    async def scenario():
        async def other():
            if separate_loop:
                return await asyncio.to_thread(lambda: asyncio.run(learning.ImprovementLoop().run()))
            return await learning.ImprovementLoop().run()
        return await asyncio.gather(learning.ImprovementLoop().run(), other())

    results = asyncio.run(scenario())
    assert sorted(r["notification"] for r in results) == ["sent", "suppressed"]
    sender.assert_awaited_once()
    writer.assert_not_awaited()


def test_unconfirmed_delivery_is_held_not_silently_retried(learning_db):
    connection, _, sender = learning_db
    sender.return_value = False
    first = asyncio.run(learning.ImprovementLoop().run())
    second = asyncio.run(learning.ImprovementLoop().run())
    assert first["notification"] == "delivery_unverified"
    assert second["notification"] == "suppressed"
    sender.assert_awaited_once()
    with connection() as conn:
        state = conn.execute("SELECT value FROM state_store WHERE key='learning_notice:0'").fetchone()[0]
    assert state.startswith("claimed:")


def test_unconfirmed_delivery_also_holds_changed_notices(learning_db):
    connection, _, sender = learning_db
    sender.return_value = False
    asyncio.run(learning.ImprovementLoop().run())
    add_outcome(connection)
    result = asyncio.run(learning.ImprovementLoop().run())
    assert result["notification"] == "suppressed"
    sender.assert_awaited_once()


def test_delivery_checkpoint_failure_never_replays_the_notice(learning_db, monkeypatch):
    _, _, sender = learning_db
    original_query = DatabaseManager.query

    async def query(sql, *args, **kwargs):
        if sql.startswith("UPDATE state_store"):
            raise RuntimeError("controlled checkpoint failure")
        return await original_query(sql, *args, **kwargs)

    monkeypatch.setattr(DatabaseManager, "query", query)
    first = asyncio.run(learning.ImprovementLoop().run())
    second = asyncio.run(learning.ImprovementLoop().run())
    assert first["notification"] == "sent_uncheckpointed"
    assert second["notification"] == "suppressed"
    sender.assert_awaited_once()


def test_funded_attempts_are_not_the_observation_floor(learning_db, monkeypatch):
    connection, writer, _ = learning_db
    monkeypatch.setenv("ZERO_BUDGET_MODE", "0")
    for _ in range(19):
        add_outcome(connection)
    for _ in range(25):
        add_outcome(connection, result="blocked")
    loop = learning.ImprovementLoop()
    optimizers = [AsyncMock(side_effect=AssertionError("not enough observations")) for _ in range(3)]
    monkeypatch.setattr(loop.optimizer, "optimize_email_framework", optimizers[0])
    monkeypatch.setattr(loop.optimizer, "optimize_send_timing", optimizers[1])
    monkeypatch.setattr(loop.optimizer, "optimize_niche_targeting", optimizers[2])
    assert asyncio.run(loop.run())["status"] == "observed"
    for optimizer in optimizers:
        optimizer.assert_not_awaited()
    writer.assert_not_awaited()


def test_individual_rankers_never_count_blocked_or_failed_attempts(learning_db):
    connection, writer, _ = learning_db
    add_outcome(connection)
    for result in ("blocked", "failed", "pending"):
        add_outcome(connection, result=result)

    async def scenario():
        optimizer = learning.StrategyOptimizer()
        await optimizer.optimize_email_framework()
        await optimizer.optimize_send_timing()
        await optimizer.optimize_niche_targeting()

    asyncio.run(scenario())
    with connection() as conn:
        rows = conn.execute("SELECT sample_size FROM learned_strategies").fetchall()
    assert len(rows) == 3 and all(row[0] == 1 for row in rows)
    writer.assert_not_awaited()


def test_learning_endpoint_does_not_label_a_failed_read_as_completed(learning_db, monkeypatch):
    from app.core.hermesclaw_endpoints import api_improvement_loop
    _, _, sender = learning_db
    monkeypatch.setattr(DatabaseManager, "fetchone", AsyncMock(side_effect=RuntimeError("offline")))
    result = asyncio.run(api_improvement_loop())
    assert result["status"] == "unavailable"
    assert result["notification"] == "not_attempted"
    sender.assert_not_awaited()


def test_failed_atomic_claim_blocks_notification(learning_db, monkeypatch):
    _, _, sender = learning_db
    monkeypatch.setattr(DatabaseManager, "fetchone", AsyncMock(return_value={
        "successful": 0, "replies": 0, "meetings": 0, "other": 0}))
    monkeypatch.setattr(DatabaseManager, "query", AsyncMock(side_effect=RuntimeError("storage down")))
    result = asyncio.run(learning.ImprovementLoop().run())
    assert result["notification"] == "storage_unavailable"
    sender.assert_not_awaited()


def test_ambiguous_write_acknowledgement_cannot_authorize_notification(learning_db, monkeypatch):
    _, _, sender = learning_db
    monkeypatch.setattr(DatabaseManager, "fetchone", AsyncMock(return_value={
        "successful": 0, "replies": 0, "meetings": 0, "other": 0}))
    monkeypatch.setattr(DatabaseManager, "query", AsyncMock(return_value={"status": "ok"}))
    result = asyncio.run(learning.ImprovementLoop().run())
    assert result["notification"] == "storage_unavailable"
    sender.assert_not_awaited()


def test_direct_zero_budget_worker_lane_cannot_bypass_scheduler_guard(monkeypatch):
    from app import worker
    monkeypatch.setenv("ZERO_BUDGET_MODE", "1")
    runner = MagicMock(side_effect=AssertionError("lane should be held"))
    monkeypatch.setattr(worker, "_run_async", runner)
    worker.self_improvement_job()
    runner.assert_not_called()


def test_zero_budget_lane_endpoint_reports_a_hold_not_triggered_work(monkeypatch):
    from app.core.hermesclaw_endpoints import api_trigger_lane
    from app import worker
    monkeypatch.setenv("ZERO_BUDGET_MODE", "1")
    runner = MagicMock(side_effect=AssertionError("lane should be held"))
    monkeypatch.setattr(worker, "_run_async", runner)
    result = asyncio.run(api_trigger_lane(8))
    assert result["status"] == "blocked"
    assert "$0" in result["message"]
    runner.assert_not_called()


@pytest.mark.parametrize("status,payload,expected", [
    (200, {"ok": True}, True),
    (401, {"ok": False}, False),
    (200, {"ok": False}, False),
    (200, {}, False),
    (200, None, False),
    (200, [], False),
    (500, {"ok": True}, False),
])
def test_telegram_alert_requires_http_and_bot_api_success(monkeypatch, status, payload, expected):
    monkeypatch.setattr(agentmail_skill, "_TG_TOKEN", "test-token")
    monkeypatch.setattr(agentmail_skill, "_TG_CHAT_ID", "123")
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    client = AsyncMock()
    client.post.return_value = response
    client.__aenter__.return_value = client
    monkeypatch.setattr(agentmail_skill.httpx, "AsyncClient", MagicMock(return_value=client))
    assert asyncio.run(agentmail_skill._send_telegram_alert("Synthetic report")) is expected


def test_telegram_alert_never_logs_secret_url_on_failure(monkeypatch, caplog):
    monkeypatch.setattr(agentmail_skill, "_TG_TOKEN", "test-token-secret-marker")
    monkeypatch.setattr(agentmail_skill, "_TG_CHAT_ID", "123")
    client = AsyncMock()
    client.post.side_effect = RuntimeError("https://api.telegram.org/bottest-token-secret-marker/sendMessage")
    client.__aenter__.return_value = client
    monkeypatch.setattr(agentmail_skill.httpx, "AsyncClient", MagicMock(return_value=client))
    assert asyncio.run(agentmail_skill._send_telegram_alert("Synthetic report")) is False
    assert "test-token-secret-marker" not in caplog.text


def test_telegram_alert_missing_credentials_is_not_success(monkeypatch):
    monkeypatch.setattr(agentmail_skill, "_TG_TOKEN", None)
    client_factory = MagicMock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(agentmail_skill.httpx, "AsyncClient", client_factory)
    assert asyncio.run(agentmail_skill._send_telegram_alert("Synthetic report")) is False
    client_factory.assert_not_called()
