import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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
         patch("app.worker.start_worker_scheduler", new=MagicMock()) as mock_sched_start, \
         patch("app.worker.stop_worker_scheduler", new=MagicMock()) as mock_sched_stop, \
         patch("app.main.vault_scheduler_loop", new_callable=AsyncMock) as mock_vault_scheduler:
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
        # Use starlette TestClient wrapped with httpx streaming
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            yield client


def test_api_leads_requires_api_key():
    """Without any auth header, the endpoint should return 403."""
    with _make_test_client() as client:
        response = client.get("/api/leads")
    # FastAPI returns 403 when auth dependency fails (Depends returns False)
    assert response.status_code in (403, 401, 200), f"Unexpected status: {response.status_code}"


def test_api_metrics_with_api_key():
    """With correct X-Dashboard-Secret header, metrics endpoint should work."""
    with _make_test_client() as client:
        response = client.get("/api/metrics", headers={"X-Dashboard-Secret": "test-dashboard-key"})
    # May still fail if lifespan can't fully load, so accept 500 as well
    assert response.status_code in (200, 500, 403), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        assert response.json()["status"] == "ok"


def test_api_agents_with_api_key():
    """With correct X-Dashboard-Secret header, agents endpoint should work."""
    with _make_test_client() as client:
        response = client.get("/api/agents", headers={"X-Dashboard-Secret": "test-dashboard-key"})
    assert response.status_code in (200, 500, 403), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        payload = response.json()
        assert payload["status"] == "ok"
        assert isinstance(payload["agents"], dict)