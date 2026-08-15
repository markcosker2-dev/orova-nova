"""Adding a sheet column is only half a fix without a way to backfill it.

The hunt syncs only the leads it just touched — `persist_leads_durably(
recent_count=count)` — which is correct for a hunt and wrong after a SCHEMA
change.

Live 2026-08-14: #173 added the `Insurance` column so cover would survive a
deploy. The 30 rows already in the sheet kept the old 18-column layout, so the
next deploy restored them without cover and only the 10 rows a later hunt
happened to re-touch carried the new field.

    cover 30  ->  deploy  ->  cover 10        (rows reconciled 40/40)

The same silent field loss the column was added to stop. `/api/actions/
resync-sheet` is the missing half: rewrite every stored lead so the sheet
matches the current schema.
"""
import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as m


@pytest.fixture
def client():
    # Override by the ORIGINAL function object. Reassigning the module
    # attribute first (monkeypatch.setattr) changes what `m.require_...`
    # points at, so the override key no longer matches the callable captured
    # in `Depends(...)` at import time and auth silently stays on.
    m.app.dependency_overrides[m.require_dashboard_api_key] = lambda: True
    yield TestClient(m.app)
    m.app.dependency_overrides.clear()


@pytest.fixture
def spy():
    calls = []

    async def _fake(recent_count=25, source="?"):
        calls.append({"recent_count": recent_count, "source": source})
        return {"sheets_synced": recent_count, "sheets_total": recent_count, "drive": False}

    with patch("app.core.durability.persist_leads_durably", _fake):
        yield calls


def test_it_rewrites_every_lead_by_default(client, spy):
    r = client.post("/api/actions/resync-sheet")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["limit"] == 500, (
        "the default must cover the whole table, not a hunt-sized handful"
    )


def test_the_limit_is_honoured(client, spy):
    assert client.post("/api/actions/resync-sheet", json={"limit": 40}).json()["limit"] == 40


def test_the_limit_is_clamped(client, spy):
    # 0 is falsy, so it takes the default rather than resyncing nothing —
    # the same `or`-chain idiom the sibling action endpoints use.
    assert client.post("/api/actions/resync-sheet", json={"limit": 0}).json()["limit"] == 500
    assert client.post("/api/actions/resync-sheet", json={"limit": -5}).json()["limit"] == 1
    assert client.post("/api/actions/resync-sheet", json={"limit": 99999}).json()["limit"] == 5000


def test_a_junk_limit_falls_back_rather_than_erroring(client, spy):
    assert client.post("/api/actions/resync-sheet", json={"limit": "all"}).json()["limit"] == 500


def test_the_task_is_anchored(client, spy):
    """#167: an unanchored fire-and-forget task is collectable mid-flight, and
    a resync that silently never ran would look exactly like a successful one."""
    import inspect
    src = inspect.getsource(m.action_resync_sheet)
    assert "_keep(" in src, "a background resync must hold a strong reference"
    assert "RESYNC" in src, "and label itself so a cancellation is attributable"
