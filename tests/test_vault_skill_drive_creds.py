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


def _valid_sqlite_bytes(tmp_path, name="src.db") -> bytes:
    """Bytes of a well-formed SQLite database (passes PRAGMA integrity_check)."""
    import sqlite3
    p = tmp_path / name
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    data = p.read_bytes()
    p.unlink()
    return data


def _restore_with(monkeypatch, tmp_path, files, id_to_bytes):
    """Run restore_latest() with a fake Drive serving `files`, each file id
    mapped to the bytes it downloads. Returns the result dict."""
    fake_db = tmp_path / "orova.db"
    fake_db.write_bytes(_valid_sqlite_bytes(tmp_path, "old.db"))
    monkeypatch.setattr(vault_skill, "DB_PATH", str(fake_db))

    class FakeDownloader:
        def __init__(self, buf, request):
            self._buf = buf
            self._data = id_to_bytes[request]  # request == fileId (see side_effect)

        def next_chunk(self):
            self._buf.write(self._data)
            return None, True

    fake_service = MagicMock()
    fake_service.files.return_value.list.return_value.execute.return_value = {"files": files}
    fake_service.files.return_value.get_media.side_effect = lambda fileId: fileId

    with patch.object(vault_skill, "_get_drive_service", return_value=fake_service), \
         patch.object(vault_skill, "_get_or_create_folder", return_value="folder1"), \
         patch.object(vault_skill, "MediaIoBaseDownload", FakeDownloader):
        res = asyncio.run(vault_skill.restore_latest())
    return res, fake_db


def test_restore_latest_adopts_valid_snapshot(monkeypatch, tmp_path):
    """Happy path: a valid snapshot is written to DB_PATH (also covers the
    2026-07-13 str-DB_PATH regression — pathlib calls on a str used to crash)."""
    snap = _valid_sqlite_bytes(tmp_path, "snap.db")
    res, fake_db = _restore_with(
        monkeypatch, tmp_path,
        files=[{"id": "f1", "name": "nova_backup_test.db"}],
        id_to_bytes={"f1": snap},
    )
    assert res["ok"] is True and res["filename"] == "nova_backup_test.db"
    assert res["skipped_corrupt"] == 0
    assert fake_db.read_bytes() == snap
    assert (tmp_path / "nova_pre_restore.db").exists()  # old DB preserved


def test_restore_latest_skips_corrupt_and_uses_older_valid(monkeypatch, tmp_path):
    """The bug that took prod down (exit 3): the NEWEST snapshot was malformed.
    Restore must skip it and adopt the next valid one instead of crashing."""
    good = _valid_sqlite_bytes(tmp_path, "good.db")
    res, fake_db = _restore_with(
        monkeypatch, tmp_path,
        files=[{"id": "bad", "name": "newest_corrupt.db"},
               {"id": "ok", "name": "older_good.db"}],
        id_to_bytes={"bad": b"this is not a sqlite file", "ok": good},
    )
    assert res["ok"] is True and res["filename"] == "older_good.db"
    assert res["skipped_corrupt"] == 1
    assert fake_db.read_bytes() == good


def test_restore_latest_all_corrupt_falls_back(monkeypatch, tmp_path):
    """When every snapshot is corrupt, return ok=False (caller uses Sheets) and
    leave the live DB untouched — never adopt a malformed file."""
    original = None
    res, fake_db = _restore_with(
        monkeypatch, tmp_path,
        files=[{"id": "b1", "name": "c1.db"}, {"id": "b2", "name": "c2.db"}],
        id_to_bytes={"b1": b"garbage-1", "b2": b"garbage-2"},
    )
    assert res["ok"] is False
    assert "corrupt" in res["error"]
    # live DB was a valid sqlite file at start and must remain openable
    assert vault_skill._sqlite_ok(fake_db)
