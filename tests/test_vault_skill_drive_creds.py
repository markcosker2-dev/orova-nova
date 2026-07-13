"""Tests for vault_skill._get_drive_service credential precedence.

The Drive backup/restore layer (the "Survivability Layer" that saves Nova's
SQLite across Render's ephemeral-disk redeploys) must build a Drive client
from whatever Google credential is configured. The key case, added 2026-07-10:
GOOGLE_CREDENTIALS_JSON — the SAME base64 service-account variable the Sheets
integration already uses — so one existing Render credential powers Drive
backup without a new OAuth secret. Without this, every deploy wiped all
learning data (leads survived via Sheets; strategies/patterns did not).
"""
import asyncio
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


def test_restore_latest_writes_snapshot_to_disk(monkeypatch, tmp_path):
    """Regression: DB_PATH is a str, and restore_latest called pathlib methods
    on it — every Drive restore crashed with 'str' object has no attribute
    'exists' (live-observed on Render, 2026-07-13)."""
    fake_db = tmp_path / "orova.db"
    fake_db.write_bytes(b"OLD-DB")
    monkeypatch.setattr(vault_skill, "DB_PATH", str(fake_db))

    class FakeDownloader:
        def __init__(self, buf, request):
            self._buf = buf

        def next_chunk(self):
            self._buf.write(b"SNAPSHOT-BYTES")
            return None, True

    fake_service = MagicMock()
    fake_service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": "f1", "name": "nova_backup_test.db"}]
    }
    with patch.object(vault_skill, "_get_drive_service", return_value=fake_service), \
         patch.object(vault_skill, "_get_or_create_folder", return_value="folder1"), \
         patch.object(vault_skill, "MediaIoBaseDownload", FakeDownloader):
        res = asyncio.run(vault_skill.restore_latest())

    assert res == {"ok": True, "filename": "nova_backup_test.db"}
    assert fake_db.read_bytes() == b"SNAPSHOT-BYTES"
    # pre-restore safety copy of the old DB
    assert (tmp_path / "nova_pre_restore.db").read_bytes() == b"OLD-DB"
