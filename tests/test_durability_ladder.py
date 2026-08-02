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


_ROWS = [{"id": 1, "business": "A"}, {"id": 2, "business": "B"}]


def test_sheets_syncs_even_when_drive_succeeds():
    """REPLACES test_drive_success_skips_sheets (2026-08-02).

    The old behaviour — and the old test — was that a successful Drive backup
    SKIPPED the Sheets copy. That made Drive a single point of failure: the
    moment its 7-day token expired there was nothing in Sheets to fall back
    to, because the fallback had been suppressed on every run where Drive
    still worked. Sheets is now Tier 1 and always runs.
    """
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               return_value={"ok": True, "filename": "snap.db"}), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               return_value=_ROWS), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock,
               return_value={"ok": True}) as m_sync:
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out["drive"] is True
    assert out["sheets_synced"] == 2, "a working Drive must NOT suppress the durable tier"
    assert m_sync.await_count == 2


def test_sheets_syncs_when_drive_token_is_dead():
    """The live steady state: invalid_grant every 7 days."""
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               return_value={"ok": False, "error": "invalid_grant"}), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               return_value=_ROWS), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock,
               return_value={"ok": True}) as m_sync:
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out == {"drive": False, "sheets_synced": 2, "sheets_total": 2}
    assert m_sync.await_count == 2


def test_drive_exploding_does_not_stop_the_sheets_tier():
    """Drive is optional; an exception there must not cost us the lead data."""
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               side_effect=RuntimeError("storageQuotaExceeded")), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               return_value=_ROWS), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock,
               return_value={"ok": True}) as m_sync:
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out["sheets_synced"] == 2
    assert out["drive"] is False
    assert m_sync.await_count == 2


def test_one_bad_row_does_not_stop_the_rest():
    """A single unsyncable lead must not cost the whole batch."""
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               return_value={"ok": False, "error": "invalid_grant"}), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               return_value=_ROWS), \
         patch("app.skills.sheets_sync.sync_lead_to_sheets", new_callable=AsyncMock,
               side_effect=[RuntimeError("bad row"), {"ok": True}]):
        out = asyncio.run(persist_leads_durably(recent_count=5, source="test"))
    assert out["sheets_synced"] == 1
    assert out["sheets_total"] == 2


def test_everything_failing_never_raises():
    with patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               side_effect=RuntimeError("drive down")), \
         patch("app.core.database.DatabaseManager.query", new_callable=AsyncMock,
               side_effect=RuntimeError("db down")):
        out = asyncio.run(persist_leads_durably(source="test"))  # must not raise
    assert out == {"drive": False, "sheets_synced": 0, "sheets_total": 0}


def test_reenrich_persists_per_upgrade_crash_safe():
    # Persistence now happens PER upgrade (not once at the end) so an OOM
    # mid-run can't lose a completed decision maker.
    from app.skills.contact_waterfall import reenrich_stored_leads, DecisionMakerResult
    stored = [{"id": 6, "business": "West Coast Exotic Cars", "owner": "",
               "owner_confidence": 0, "score": 75},
              {"id": 7, "business": "Luxury Motorcars", "owner": "",
               "owner_confidence": 0, "score": 60}]

    async def fake_query(sql, params=(), fetchall=False):
        return stored if fetchall else None

    dm = DecisionMakerResult(name="Eric Curran", confidence=40, source="serpapi")
    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.skills.contact_waterfall.resolve_decision_maker",
               new_callable=AsyncMock, return_value=dm), \
         patch("app.core.durability.persist_leads_durably",
               new_callable=AsyncMock, return_value={"drive": False, "sheets_synced": 1}) as m_persist:
        summary = asyncio.run(reenrich_stored_leads(limit=5))
    assert summary["upgraded"] == 2
    assert m_persist.await_count == 2  # one durable write per upgrade


def test_reenrich_halts_on_memory_pressure():
    # The memory gate must stop the loop before OOM, deferring the rest.
    from app.skills.contact_waterfall import reenrich_stored_leads, DecisionMakerResult
    stored = [{"id": i, "business": f"Biz {i}", "owner": "",
               "owner_confidence": 0, "score": 60} for i in range(5)]

    async def fake_query(sql, params=(), fetchall=False):
        return stored if fetchall else None

    dm = DecisionMakerResult(name="Ann Kim", confidence=40, source="serpapi")
    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.skills.contact_waterfall.resolve_decision_maker",
               new_callable=AsyncMock, return_value=dm), \
         patch("app.core.durability.persist_leads_durably", new_callable=AsyncMock), \
         patch("app.core.hardening.memory_monitor.check_memory",
               new_callable=AsyncMock, return_value={"critical": True, "memory_mb": 450}):
        summary = asyncio.run(reenrich_stored_leads(limit=5))
    assert summary["checked"] == 0            # halted before touching any lead
    assert summary["stopped"] is not None


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
