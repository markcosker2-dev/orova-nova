"""Canonical durability ladder + background reenrich (2026-07-21).

An OOM restart destroyed a 5-lead CSV import and a waterfall upgrade —
work that only lived on Render's ephemeral disk. The ladder
(Drive → Sheets fallback) is now one helper wired into ALL write paths
(hunt, csv_import, reenrich), and reenrich runs in the background so a
long multi-lead run can never exceed the proxy timeout again.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.core.durability import persist_leads_durably


def test_drive_success_skips_sheets():
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               return_value={"ok": True, "filename": "snap.db"}), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock) as m_sync:
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out["drive"] is True
    m_sync.assert_not_awaited()


def test_drive_failure_falls_to_sheets():
    rows = [{"id": 1, "business": "A"}, {"id": 2, "business": "B"}]
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               return_value={"ok": False, "error": "invalid_grant"}), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               return_value=rows), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock,
               return_value={"ok": True}) as m_sync:
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out == {"drive": False, "sheets_synced": 2}
    assert m_sync.await_count == 2


def test_everything_failing_never_raises():
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               side_effect=RuntimeError("drive down")), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               side_effect=RuntimeError("db down")):
        out = asyncio.run(persist_leads_durably(source="test"))  # must not raise
    assert out == {"drive": False, "sheets_synced": 0}


def test_reenrich_persists_after_upgrades():
    from app.skills.contact_waterfall import reenrich_stored_leads, DecisionMakerResult, Evidence
    stored = [{"id": 6, "business": "West Coast Exotic Cars", "owner": "",
               "owner_confidence": 0, "score": 75}]

    async def fake_query(sql, params=(), fetchall=False):
        return stored if fetchall else None

    dm = DecisionMakerResult(name="Eric Curran", confidence=40, source="serpapi")
    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.skills.contact_waterfall.resolve_decision_maker",
               new_callable=AsyncMock, return_value=dm), \
         patch("app.core.durability.persist_leads_durably",
               new_callable=AsyncMock, return_value={"drive": False, "sheets_synced": 1}) as m_persist:
        summary = asyncio.run(reenrich_stored_leads(limit=5))
    assert summary["upgraded"] == 1
    m_persist.assert_awaited_once()


def test_reenrich_without_upgrades_does_not_persist():
    from app.skills.contact_waterfall import reenrich_stored_leads, DecisionMakerResult

    async def fake_query(sql, params=(), fetchall=False):
        return [] if fetchall else None

    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.core.durability.persist_leads_durably", new_callable=AsyncMock) as m_persist:
        asyncio.run(reenrich_stored_leads(limit=5))
    m_persist.assert_not_awaited()


# ── endpoint modes ───────────────────────────────────────────────────────────

def test_reenrich_endpoint_backgrounds_by_default():
    from tests.test_dashboard_api import _make_test_client
    with _make_test_client() as client, \
         patch("app.skills.contact_waterfall.reenrich_stored_leads",
               new_callable=AsyncMock, return_value={"checked": 0, "upgraded": 0}) as m:
        resp = client.post("/api/actions/reenrich-leads", json={"limit": 10},
                           headers={"X-API-Key": "test-dashboard-key"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "background"


def test_reenrich_endpoint_sync_mode_forces_limit_one():
    from tests.test_dashboard_api import _make_test_client
    with _make_test_client() as client, \
         patch("app.skills.contact_waterfall.reenrich_stored_leads",
               new_callable=AsyncMock,
               return_value={"checked": 1, "upgraded": 0, "found_names": []}) as m:
        resp = client.post("/api/actions/reenrich-leads", json={"limit": 50, "sync": "1"},
                           headers={"X-API-Key": "test-dashboard-key"})
    assert resp.json()["mode"] == "sync"
    m.assert_awaited_once_with(limit=1)
