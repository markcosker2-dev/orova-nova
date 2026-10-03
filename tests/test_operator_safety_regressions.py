"""Offline controls for approval lifetime, outcome truth, and excluded targets."""
import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core import event_log, nova_chat
from app.core.database import DatabaseManager
from app.skills import approval_workflow as approvals
from app.skills.lead_validator import off_icp_trade_reason, validate_lead_for_storage


NOW = 200_000
PARAMS = {"lead_id": 41}
RID = "APPROVAL-0041"
_REAL_PERSIST_STATE = approvals._persist_state


@pytest.fixture
def approval_state(monkeypatch):
    request = {
        "action": "auto_call", "action_hash": approvals._action_hash("auto_call", PARAMS),
        "details": "synthetic", "status": "pending", "created_at": NOW - 60,
        "resolved_at": None,
    }
    monkeypatch.setattr(approvals, "_loaded_from_db", True)
    monkeypatch.setattr(approvals, "_approval_counter", 41)
    monkeypatch.setattr(approvals, "_pending_approvals", {RID: request})
    monkeypatch.setattr(approvals.time, "time", lambda: NOW)
    monkeypatch.setattr(approvals, "_persist_state", AsyncMock(return_value=True))
    monkeypatch.setattr(approvals, "_send_telegram", AsyncMock(return_value=True))
    return request


def test_current_pending_approval_is_consumed_exactly_once(approval_state):
    async def scenario():
        assert "APPROVED:" in await approvals.handle_approval_response(f"approve {RID}")
        assert await approvals.is_action_approved("auto_call", PARAMS)
        assert not await approvals.is_action_approved("auto_call", PARAMS)
    asyncio.run(scenario())


@pytest.mark.parametrize("status", ["approved", "consumed", "rejected"])
def test_resolved_approval_cannot_be_reopened(approval_state, status):
    approval_state.update(status=status, resolved_at=NOW - 10)
    reply = asyncio.run(approvals.handle_approval_response(f"approve {RID}"))
    assert "APPROVED:" not in reply
    assert approval_state["status"] == status
    assert approval_state["resolved_at"] == NOW - 10


def test_consumed_approval_replay_cannot_authorize_a_second_action(approval_state):
    async def scenario():
        await approvals.handle_approval_response(f"approve {RID}")
        assert await approvals.is_action_approved("auto_call", PARAMS)
        await approvals.handle_approval_response(f"approve {RID}")
        assert not await approvals.is_action_approved("auto_call", PARAMS)
    asyncio.run(scenario())


@pytest.mark.parametrize("age", [86_400, 172_800])
def test_expired_pending_approval_cannot_be_renewed(approval_state, age):
    approval_state["created_at"] = NOW - age
    reply = asyncio.run(approvals.handle_approval_response(f"approve {RID}"))
    assert "APPROVED:" not in reply
    assert not asyncio.run(approvals.is_action_approved("auto_call", PARAMS))


def test_approval_expiry_is_not_extended_by_resolution(approval_state):
    approval_state.update(status="approved", created_at=NOW - 86_400,
                          resolved_at=NOW - 1)
    assert not asyncio.run(approvals.is_action_approved("auto_call", PARAMS))


def test_expired_pending_request_does_not_block_a_fresh_request(approval_state):
    approval_state["created_at"] = NOW - 86_400
    fresh = asyncio.run(approvals.request_firewall_approval("auto_call", PARAMS, "synthetic"))
    assert fresh != RID
    assert approvals._pending_approvals[fresh]["status"] == "pending"
    assert approvals._pending_approvals[fresh]["created_at"] == NOW
    approvals._send_telegram.assert_awaited_once()


def test_current_pending_request_is_reused_without_notification(approval_state):
    assert asyncio.run(approvals.request_firewall_approval("auto_call", PARAMS, "synthetic")) == RID
    approvals._send_telegram.assert_not_awaited()


def test_expired_requests_are_not_reported_pending(approval_state):
    approval_state["created_at"] = NOW - 86_400
    assert "EXPIRED" in asyncio.run(approvals.check_approval(RID))
    assert RID not in asyncio.run(approvals.list_pending())


def test_restoring_expired_requests_does_not_recycle_their_ids(approval_state, monkeypatch):
    approval_state["created_at"] = NOW - 86_400
    monkeypatch.setattr(approvals, "_loaded_from_db", False)
    monkeypatch.setattr(approvals, "_approval_counter", 0)
    monkeypatch.setattr(approvals, "_pending_approvals", {})
    monkeypatch.setattr(DatabaseManager, "get_state", AsyncMock(return_value={RID: approval_state}))
    fresh = asyncio.run(approvals.request_firewall_approval("auto_call", PARAMS, "synthetic"))
    assert fresh == "APPROVAL-0042"


def test_approval_persistence_failure_does_not_claim_or_grant_permission(approval_state, monkeypatch):
    # Exercise the real best-effort persistence wrapper, not a throwing mock.
    monkeypatch.setattr(approvals, "_persist_state", _REAL_PERSIST_STATE)
    monkeypatch.setattr(DatabaseManager, "set_state", AsyncMock(side_effect=RuntimeError("synthetic write failure")))
    reply = asyncio.run(approvals.handle_approval_response(f"approve {RID}"))
    assert "APPROVED:" not in reply
    assert approval_state["status"] == "pending"


def test_consumption_persistence_failure_blocks_the_action(approval_state, monkeypatch):
    approval_state.update(status="approved", resolved_at=NOW - 10)
    monkeypatch.setattr(approvals, "_persist_state", AsyncMock(return_value=False))
    assert not asyncio.run(approvals.is_action_approved("auto_call", PARAMS))


def test_failed_initial_approval_read_retries_before_allocating_ids(approval_state, monkeypatch):
    monkeypatch.setattr(approvals, "_loaded_from_db", False)
    monkeypatch.setattr(approvals, "_approval_counter", 0)
    monkeypatch.setattr(approvals, "_pending_approvals", {})
    read = AsyncMock(side_effect=[RuntimeError("synthetic read failure"), {RID: approval_state}])
    monkeypatch.setattr(DatabaseManager, "get_state", read)

    async def scenario():
        assert not await approvals.is_action_approved("auto_call", PARAMS)
        assert not approvals._loaded_from_db
        fresh = await approvals.request_firewall_approval("auto_call", {"lead_id": 43}, "synthetic")
        assert fresh == "APPROVAL-0042"
        assert read.await_count == 2
    asyncio.run(scenario())


def test_unpersisted_request_is_not_notified_or_reused(approval_state, monkeypatch):
    approval_state["status"] = "consumed"
    monkeypatch.setattr(approvals, "_persist_state", AsyncMock(return_value=False))
    with pytest.raises(RuntimeError, match="persist"):
        asyncio.run(approvals.request_firewall_approval("auto_call", PARAMS, "synthetic"))
    approvals._send_telegram.assert_not_awaited()
    assert not any(req["status"] == "pending" for req in approvals._pending_approvals.values())


@pytest.mark.parametrize("_iteration", range(2))
def test_concurrent_first_reads_do_not_overwrite_new_requests_or_reuse_ids(approval_state, monkeypatch, _iteration):
    monkeypatch.setattr(approvals, "_loaded_from_db", False)
    monkeypatch.setattr(approvals, "_approval_counter", 0)
    monkeypatch.setattr(approvals, "_pending_approvals", {})

    async def scenario():
        first_read_started = asyncio.Event()
        release_first_read = asyncio.Event()

        async def read_state(*args):
            if read.await_count == 1:
                first_read_started.set()
                await release_first_read.wait()
            return {RID: dict(approval_state)}

        read = AsyncMock(side_effect=read_state)
        monkeypatch.setattr(DatabaseManager, "get_state", read)
        first = asyncio.create_task(approvals.request_firewall_approval("auto_call", {"lead_id": 43}, "synthetic"))
        await first_read_started.wait()
        second = asyncio.create_task(approvals.request_firewall_approval("auto_call", {"lead_id": 44}, "synthetic"))
        # Let the second call reach its load while the first read is held.
        await asyncio.sleep(0)
        release_first_read.set()
        ids = await asyncio.gather(first, second)
        assert ids == ["APPROVAL-0042", "APPROVAL-0043"]
        assert read.await_count == 1
        assert len(approvals._pending_approvals) == 3
        assert approvals._pending_approvals[ids[0]]["action_hash"] != approvals._pending_approvals[ids[1]]["action_hash"]

    asyncio.run(scenario())


@pytest.fixture
def outcome_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE leads (id INTEGER PRIMARY KEY, client_id INTEGER, status TEXT);
        INSERT INTO leads VALUES (41, 0, 'New'), (42, 1, 'New');
        CREATE TABLE events (prospect_id INTEGER, campaign_id INTEGER, agent TEXT,
                             event_type TEXT, variant_id TEXT, payload TEXT);
    """)
    state = SimpleNamespace(conn=conn, fail_insert=False, fail_update=False,
                            zero_update=False, fail_read=False, calls=[])

    async def query(sql, params=(), fetchone=False, fetchall=False):
        state.calls.append((sql, params))
        if (state.fail_read and sql.lstrip().startswith("SELECT")
                or state.fail_insert and sql.lstrip().startswith("INSERT")
                or state.fail_update and sql.lstrip().startswith("UPDATE")):
            raise RuntimeError("synthetic database failure")
        if state.zero_update and sql.lstrip().startswith("UPDATE"):
            return {"status": "ok", "rows_affected": 0}
        cur = conn.execute(sql, params)
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        conn.commit()
        return {"status": "ok", "rows_affected": cur.rowcount}

    # Module-local facade: root logger/background DB state writes must not
    # enter this command's fake query recorder or change its SQLite fixture.
    monkeypatch.setattr(event_log, "DatabaseManager", SimpleNamespace(query=query))
    monkeypatch.setattr(event_log, "_mirror_dial_to_sheets", AsyncMock())
    yield state
    conn.close()


@pytest.mark.parametrize("lead_id", [-1, 0, 999, 42])
def test_outcome_requires_a_positive_existing_orova_lead(outcome_db, lead_id):
    reply = asyncio.run(event_log.handle_outcome_command(f"/outcome {lead_id} booked"))
    assert "Logged" not in reply
    assert outcome_db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in outcome_db.calls)
    assert outcome_db.conn.execute("SELECT status FROM leads WHERE id=42").fetchone()[0] == "New"


def test_outcome_read_failure_does_not_claim_or_write_an_outcome(outcome_db):
    outcome_db.fail_read = True
    reply = asyncio.run(event_log.handle_outcome_command("/outcome 41 booked"))
    assert "Logged" not in reply
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in outcome_db.calls)


def test_failed_canonical_event_does_not_update_status_or_mirror(outcome_db):
    outcome_db.fail_insert = True
    reply = asyncio.run(event_log.handle_outcome_command("/outcome 41 talked synthetic"))
    assert "Logged" not in reply
    assert outcome_db.conn.execute("SELECT status FROM leads WHERE id=41").fetchone()[0] == "New"
    event_log._mirror_dial_to_sheets.assert_not_awaited()


@pytest.mark.parametrize("failure", ["fail_update", "zero_update"])
def test_failed_status_projection_reports_only_the_recorded_event(outcome_db, failure):
    setattr(outcome_db, failure, True)
    reply = asyncio.run(event_log.handle_outcome_command("/outcome 41 booked"))
    assert "Logged 'meeting_booked'" in reply
    assert "status update failed" in reply.lower()
    assert "→ status 'Meeting Booked'" not in reply
    assert outcome_db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
    assert outcome_db.conn.execute("SELECT status FROM leads WHERE id=41").fetchone()[0] == "New"


def test_successful_outcome_acknowledges_canonical_event_and_status(outcome_db):
    reply = asyncio.run(event_log.handle_outcome_command("/outcome 41 booked synthetic"))
    assert "Logged 'meeting_booked'" in reply and "→ status 'Meeting Booked'" in reply
    assert outcome_db.conn.execute("SELECT status FROM leads WHERE id=41").fetchone()[0] == "Meeting Booked"
    assert outcome_db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_event_logger_exposes_success_without_raising_on_failure(outcome_db):
    assert asyncio.run(event_log.alog_event(41, "meeting_held", "desk")) is True
    outcome_db.fail_insert = True
    assert asyncio.run(event_log.alog_event(41, "meeting_held", "desk")) is False


def test_similar_command_name_does_not_record_an_outcome(outcome_db):
    assert asyncio.run(event_log.handle_outcome_command("/outcome_typo 41 booked")) is None
    assert outcome_db.calls == []


@pytest.mark.parametrize("business,vertical", [
    ("Pacific Med Spa", ""), ("Pacific Medical Spa", ""), ("Pacific MedSpa", ""),
    ("Pacific Luxury Med-Spa", "luxury"), ("Pacific Wellness", "med spa california"),
    ("Pacific Wellness", "medical spa"), ("Pacific Wellness", "medspa"),
])
def test_explicit_med_spa_records_are_excluded(business, vertical):
    lead = {"business": business, "vertical": vertical}
    assert "ADR-0015" in off_icp_trade_reason(lead)
    assert validate_lead_for_storage(lead)["ok"] is False


@pytest.mark.parametrize("business", [
    "Pacific Spa Remodeling", "Aesthetic Home Builders", "Whitestone Custom Homes",
    "Alderwood Design Build", "Summit Ridge Remodeling", "Harbor Oak Kitchen and Bath",
    "Cascade Heritage Builders", "Evergreen Custom Home Builders", "Pinnacle Luxury Renovations",
    "Northgate Mechanical Contractors", "Retirement Living Builders", "Autumn Ridge Custom Homes",
    "Bellevue Luxury Properties Group",
])
def test_med_spa_exclusion_preserves_builder_and_real_estate_controls(business):
    assert off_icp_trade_reason({"business": business}) == ""


def test_focus_skips_med_spas_in_favor_of_a_stored_builder(monkeypatch):
    rows = [
        {"id": 41, "business": "Pacific Med Spa", "vertical": "", "status": "New", "score": 100},
        {"id": 43, "business": "Pacific Custom Homes", "vertical": "custom home builder", "status": "New", "score": 70},
    ]
    monkeypatch.setattr(DatabaseManager, "fetchall", AsyncMock(return_value=rows))
    monkeypatch.setattr(nova_chat, "lead_contact_cards", AsyncMock(return_value="synthetic card"))
    reply = asyncio.run(nova_chat.operator_focus())
    assert "lead #43" in reply and "lead #41" not in reply
    nova_chat.lead_contact_cards.assert_awaited_once_with(43)
