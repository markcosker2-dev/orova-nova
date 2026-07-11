"""Tests for vault_skill._get_drive_service credential precedence.

The Drive backup/restore layer (the "Survivability Layer" that saves Nova's
SQLite across Render's ephemeral-disk redeploys) must build a Drive client
from whatever Google credential is configured. The key case, added 2026-07-10:
GOOGLE_CREDENTIALS_JSON — the SAME base64 service-account variable the Sheets
integration already uses — so one existing Render credential powers Drive
backup without a new OAuth secret. Without this, every deploy wiped all
learning data (leads survived via Sheets; strategies/patterns did not).
"""
import base64
import json
from unittest.mock import patch, MagicMock

import pytest

from app.skills import vault_skill


def _clear(monkeypatch):
    for k in ("GOOGLE_REFRESH_TOKEN", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
              "GOOGLE_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(k, raising=False)


def _fake_sa_json() -> str:
    payload = {"type": "service_account", "project_id": "orova", "client_email": "svc@orova.iam"}
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_base64_service_account_builds_drive_client(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", _fake_sa_json())
    with patch("app.skills.vault_skill.service_account.Credentials.from_service_account_info",
               return_value=MagicMock()) as from_info, \
         patch("app.skills.vault_skill.build", return_value="drive-client") as build_mock:
        svc = vault_skill._get_drive_service()
    assert svc == "drive-client"
    # decoded the base64 into the real service-account dict
    assert from_info.call_args.args[0]["client_email"] == "svc@orova.iam"
    assert build_mock.call_args.args[:2] == ("drive", "v3")


def test_oauth_trio_takes_precedence_over_base64(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "rt")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", _fake_sa_json())
    with patch("app.skills.vault_skill.Credentials", return_value=MagicMock()) as oauth_creds, \
         patch("app.skills.vault_skill.service_account.Credentials.from_service_account_info") as sa_info, \
         patch("app.skills.vault_skill.build", return_value="drive-client"):
        svc = vault_skill._get_drive_service()
    assert svc == "drive-client"
    oauth_creds.assert_called_once()      # OAuth path used
    sa_info.assert_not_called()           # base64 path skipped


def test_no_credentials_raises_clear_error(monkeypatch):
    _clear(monkeypatch)
    # Guard: default creds_path "credentials.json" must not exist for this to raise.
    with patch("app.skills.vault_skill.os.path.exists", return_value=False):
        with pytest.raises(ValueError, match="GOOGLE_CREDENTIALS_JSON"):
            vault_skill._get_drive_service()
