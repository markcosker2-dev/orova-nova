"""CSV lead import (SDR Stage 1: any source → pipeline). 2026-07-14.

Uses the same mocked TestClient harness as test_dashboard_api: DB calls are
mocked, so these tests exercise parsing, header mapping, quality gates,
dedup, and scoring — the endpoint's actual logic."""
import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DASHBOARD_API_KEY", "test-dashboard-key")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")

from app.main import app


@contextmanager
def _client(existing_rows=None, saved_ids=None):
    saved = saved_ids if saved_ids is not None else iter(range(100, 200))
    with patch("app.main.restore_leads_from_sheets", new_callable=AsyncMock, return_value=[]), \
         patch("app.main.restore_latest", new_callable=AsyncMock, return_value={"ok": False}), \
         patch("app.main.AgentSoul.initialize", new_callable=AsyncMock), \
         patch("app.main.DatabaseManager.init_db", new_callable=MagicMock), \
         patch("app.main.DatabaseManager.run_phase5_migrations", new_callable=AsyncMock), \
         patch("app.main.DatabaseManager.is_empty", new_callable=AsyncMock, return_value=False), \
         patch("app.main.DatabaseManager.query", new_callable=AsyncMock, return_value=existing_rows or []), \
         patch("app.main.DatabaseManager.asave_lead", new_callable=AsyncMock, side_effect=lambda *a, **k: next(saved)) as mock_save, \
         patch("app.main.tg_queue.start", new_callable=AsyncMock), \
         patch("app.main.tg_queue.stop", new_callable=AsyncMock), \
         patch("app.main.vault_scheduler_loop", new_callable=AsyncMock):
        from starlette.testclient import TestClient
        with TestClient(app) as client:
            yield client, mock_save


HDRS = {"X-Dashboard-Secret": "test-dashboard-key"}


def test_import_happy_path_with_flexible_headers():
    csv_body = (
        "Company,Contact Name,Email Address,Phone,URL,Industry\n"
        "Exotic Motors LA,Todd Rowsell,todd@exoticmotors.com,+13105551234,https://exoticmotors.com,exotic car dealer\n"
        "Beverly Wraps,Jane Smith,jane@beverlywraps.com,,https://beverlywraps.com,wrap shop\n"
    )
    with _client() as (client, mock_save):
        r = client.post("/api/leads/import-csv", content=csv_body, headers=HDRS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["imported"] == 2
    assert mock_save.await_count == 2
    # scored, not flat: full-contact luxury lead must be HOT-range
    assert body["leads"][0]["score"] >= 70


def test_import_rejects_junk_email_but_keeps_lead():
    csv_body = (
        "business,owner,email\n"
        "Auto Spa,Bob Lee,a-logo-black-@1x.png\n"
    )
    with _client() as (client, mock_save):
        r = client.post("/api/leads/import-csv", content=csv_body, headers=HDRS)
    body = r.json()
    assert body["imported"] == 1                       # lead kept
    saved_lead = mock_save.await_args_list[0].args[0]
    assert saved_lead["email"] == ""                   # junk email dropped
    assert any("invalid email" in s["reason"] for s in body["skipped_detail"])


def test_import_dedups_against_existing_db():
    existing = [{"email": "todd@exoticmotors.com", "business": "Exotic Motors LA"}]
    csv_body = (
        "business,email\n"
        "Exotic Motors LA,todd@exoticmotors.com\n"
        "Fresh Detail Co,ana@freshdetail.com\n"
    )
    with _client(existing_rows=existing) as (client, mock_save):
        r = client.post("/api/leads/import-csv", content=csv_body, headers=HDRS)
    body = r.json()
    assert body["imported"] == 1
    assert body["skipped"] >= 1
    assert mock_save.await_count == 1


def test_import_requires_business_column_and_body():
    with _client() as (client, _):
        r1 = client.post("/api/leads/import-csv", content="", headers=HDRS)
        r2 = client.post("/api/leads/import-csv", content="foo,bar\n1,2\n", headers=HDRS)
    assert r1.json()["status"] == "error"
    assert "business" in r2.json()["error"].lower() or "company" in r2.json()["error"].lower()
