import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

# Ensure stable auth values for test runs
os.environ.setdefault("DASHBOARD_API_KEY", "test-dashboard-key")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")

from app.main import app


@contextmanager
def _make_test_client():
    with patch("app.main.restore_leads_from_sheets", new_callable=AsyncMock) as mock_restore_sheets, \
         patch("app.main.restore_latest", new_callable=AsyncMock) as mock_restore_latest, \
         patch("app.main.AgentSoul.initialize", new_callable=AsyncMock) as mock_agent_initialize, \
         patch("app.main.DatabaseManager.init_db", new_callable=MagicMock) as mock_init_db, \
         patch("app.main.DatabaseManager.run_phase5_migrations", new_callable=AsyncMock) as mock_run_migrations, \
         patch("app.main.DatabaseManager.is_empty", new_callable=AsyncMock) as mock_is_empty, \
         patch("app.main.DatabaseManager.query", new_callable=AsyncMock) as mock_query, \
         patch("app.main.tg_queue.start", new_callable=AsyncMock) as mock_tg_start, \
         patch("app.main.tg_queue.stop", new_callable=AsyncMock) as mock_tg_stop, \
         patch("app.main.vault_scheduler_loop", new_callable=AsyncMock) as mock_vault_scheduler, \
         patch("app.main.cleanup_crawler", new_callable=AsyncMock) as mock_cleanup_crawler:
        mock_restore_sheets.return_value = []
        mock_restore_latest.return_value = {"ok": False}
        mock_agent_initialize.return_value = None
        mock_init_db.return_value = None
        mock_run_migrations.return_value = None
        mock_is_empty.return_value = False
        mock_query.return_value = []
        mock_tg_start.return_value = None
        mock_tg_stop.return_value = None
        mock_vault_scheduler.return_value = None
        mock_cleanup_crawler.return_value = None
        with TestClient(app) as client:
            yield client


def test_api_leads_requires_api_key():
    with _make_test_client() as client:
        response = client.get("/api/leads")
    assert response.status_code == 403
    assert response.json()["detail"] == "Unauthorized"


def test_api_metrics_with_api_key():
    with _make_test_client() as client:
        response = client.get("/api/metrics", headers={"X-API-Key": "test-dashboard-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_agents_with_api_key():
    with _make_test_client() as client:
        response = client.get("/api/agents", headers={"X-API-Key": "test-dashboard-key"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["agents"], list)
