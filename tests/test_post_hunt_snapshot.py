"""Post-hunt Drive snapshot (2026-07-20).

Deploys wipe Render's ephemeral disk; the Drive backup ran on a 12-hour
interval. The first real production hunt (5 on-ICP dealers, 05:12) was
destroyed by the very next merge's deploy (~05:25) because no snapshot ran
in between. The slow lane now snapshots immediately after saving leads —
fail-open, a backup failure must never fail the hunt.
"""
import asyncio
from unittest.mock import AsyncMock, patch


def _run_hunt():
    from app.worker import run_lead_hunt_slow_lane
    return asyncio.run(run_lead_hunt_slow_lane(client_id=0, niche="exotic car dealer",
                                               location="California"))


def _common_patches(found_leads):
    return [
        patch("app.worker.find_leads", new_callable=AsyncMock,
              return_value={"leads": found_leads, "text": "t"}),
        patch("app.worker.enrich_lead_lite", new_callable=AsyncMock,
              side_effect=lambda l: l),
        patch("app.worker.DatabaseManager.asave_lead", new_callable=AsyncMock,
              return_value=7),
        patch("app.worker.DatabaseManager.aget_metrics", new_callable=AsyncMock,
              return_value={"cost": 0}),
        patch("app.worker.DatabaseManager.aupdate_metrics", new_callable=AsyncMock),
        patch("app.worker.send_telegram_report", new_callable=AsyncMock),
        patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
              return_value={"ok": True, "filename": "nova_backup_test.db"}),
    ]


def test_hunt_snapshots_after_saving_leads():
    lead = {"business": "Vivid Motors", "url": "https://vividmotors.com",
            "owner_name": "Dana Ferrari", "email": "", "phone": "", "score": 0}
    patches = _common_patches([lead])
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6] as mock_backup:
        _run_hunt()
    mock_backup.assert_awaited_once()


def test_hunt_without_leads_does_not_snapshot():
    patches = _common_patches([])
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patches[6] as mock_backup:
        _run_hunt()
    mock_backup.assert_not_awaited()


def test_backup_failure_does_not_fail_the_hunt():
    lead = {"business": "Vivid Motors", "url": "https://vividmotors.com",
            "owner_name": "", "email": "", "phone": "", "score": 0}
    patches = _common_patches([lead])
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
         patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
               side_effect=RuntimeError("drive down")):
        _run_hunt()  # must not raise
