"""
vault_skill.py — OROVA Survivability Layer
Periodic + on-demand backup of nova.db to Google Drive.
Restore command pulls latest snapshot back to disk post-redeploy.
"""

import asyncio
import base64
import io
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app.core.database import DB_PATH

# Note: These imports require google-api-python-client and google-auth
try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ Google Drive API dependencies missing. /backup and /restore will be disabled.")

logger = logging.getLogger(__name__)

# ── Settings & Paths ──
BACKUP_PATH = Path("nova_backup.db")
DRIVE_FOLDER = "OROVA_BACKUPS"
BACKUP_PREFIX = "nova_backup_"
KEEP_N = 5
BACKUP_INTERVAL_SECONDS = 12 * 3600 # 12 hours

def _get_drive_service():
    """Build a Google Drive v3 service client.

    Credential precedence (first available wins):
      1. GOOGLE_REFRESH_TOKEN + GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET (user OAuth)
      2. GOOGLE_CREDENTIALS_JSON (base64 service-account JSON) — the SAME
         variable the Sheets integration already uses (sheets_sync.py), so a
         single Render credential powers Drive backup AND Sheets with no new
         env var to configure.
      3. GOOGLE_APPLICATION_CREDENTIALS (service-account file path)

    CORRECTION 2026-08-02: this docstring used to claim "backups land in the
    service account's own Drive (its 15GB), self-contained, no user-Drive
    sharing needed". That is FALSE, and it produced a bad recommendation —
    "just delete the OAuth vars and fall through to the service account" —
    which would have replaced a backup that dies weekly with one that never
    works at all.

    Service accounts have NO Drive storage quota and cannot own files. Tier 2
    and 3 below therefore fail with `403 storageQuotaExceeded` on a personal
    Google account; they only work against a Workspace shared drive or via
    domain-wide delegation. The SAME credential works for Sheets
    (sheets_sync.py) because the spreadsheet is owned by a real user and
    merely shared with the service account — nothing is being created in
    storage the service account would have to own.

    Practical consequence: path 1 (user OAuth) is the only one that works
    here, and its refresh token expires every 7 days while the OAuth consent
    screen is External + Testing. Publish the consent screen to make it
    durable. Until then Drive is best-effort and Sheets is the durable tier
    (see app/core/durability.py).
    """
    _DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]

    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    if all([refresh_token, client_id, client_secret]):
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_b64:
        creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        sa_creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=_DRIVE_SCOPES
        )
        return build("drive", "v3", credentials=sa_creds, cache_discovery=False)

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if os.path.exists(creds_path):
        sa_creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=_DRIVE_SCOPES
        )
        return build("drive", "v3", credentials=sa_creds, cache_discovery=False)

    raise ValueError(
        "No Google Drive credentials: set GOOGLE_REFRESH_TOKEN/GOOGLE_CLIENT_ID/"
        "GOOGLE_CLIENT_SECRET, or GOOGLE_CREDENTIALS_JSON, or "
        "GOOGLE_APPLICATION_CREDENTIALS."
    )

def _get_or_create_folder(service) -> str:
    """Return the Drive folder ID for OROVA_BACKUPS, creating it if absent."""
    query = f"name='{DRIVE_FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files: return files[0]["id"]

    meta = {"name": DRIVE_FOLDER, "mimeType": "application/vnd.google-apps.folder"}
    folder = service.files().create(body=meta, fields="id").execute()
    logger.info(f"[Vault] Created Drive folder '{DRIVE_FOLDER}' → {folder['id']}")
    return folder["id"]

async def backup_database() -> dict:
    """[P6] Atomic hot-copy and upload to Google Drive."""
    try:
        # Step 1: Atomic Hot-Copy (WAL safe)
        src_con = sqlite3.connect(str(DB_PATH))
        dst_con = sqlite3.connect(str(BACKUP_PATH))
        with dst_con:
            src_con.backup(dst_con)
        src_con.close()
        dst_con.close()

        # Step 2: Upload
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{BACKUP_PREFIX}{ts}.db"
        
        service = await asyncio.to_thread(_get_drive_service)
        folder_id = await asyncio.to_thread(_get_or_create_folder, service)

        media = MediaFileUpload(str(BACKUP_PATH), mimetype="application/octet-stream")
        file_meta = {"name": filename, "parents": [folder_id]}

        uploaded = await asyncio.to_thread(
            lambda: service.files().create(body=file_meta, media_body=media, fields="id, name").execute()
        )
        logger.info(f"[Vault] Uploaded → {filename}")
        
        # Step 3: Rolling Prune
        await asyncio.to_thread(_prune_old_backups, service, folder_id)
        
        return {"ok": True, "filename": filename}
    except Exception as e:
        logger.error(f"[Vault] Backup failed: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        if BACKUP_PATH.exists(): BACKUP_PATH.unlink()

def _prune_old_backups(service, folder_id: str):
    query = f"'{folder_id}' in parents and name contains '{BACKUP_PREFIX}' and trashed=false"
    results = service.files().list(q=query, orderBy="createdTime asc", fields="files(id, name)").execute()
    files = results.get("files", [])
    if len(files) > KEEP_N:
        for f in files[:-KEEP_N]:
            service.files().delete(fileId=f["id"]).execute()
            logger.info(f"[Vault] Pruned: {f['name']}")

def _sqlite_ok(path: Path) -> bool:
    """True only if `path` is a well-formed SQLite database.

    A corrupt snapshot that passes as 'downloaded' but is malformed took the
    whole service down with exit 3 on 2026-07-13 (startup opened it, SQLite
    raised 'database disk image is malformed', the lifespan died). We now
    validate every snapshot with an integrity check before adopting it."""
    try:
        con = sqlite3.connect(str(path))
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            return bool(row) and row[0] == "ok"
        finally:
            con.close()
    except Exception:
        return False


def _prepare_db_for_swap(db_path: Path):
    """Make it safe to overwrite the live DB file with a restored snapshot.

    Two hazards, both root causes of the 2026-07-13 'database disk image is
    malformed' crash: (1) the live connection pool holds WAL locks and would
    checkpoint stale pages onto the new file when closed, and (2) the empty
    DB's `-wal`/`-shm` sidecars, if left in place, mismatch the swapped-in main
    file. So we close the pool first, keep a pre-restore copy, then delete the
    main DB *and* its sidecars — leaving a clean slate for the snapshot."""
    try:
        from app.core.database import DatabaseManager
        DatabaseManager._close_all_connections()
    except Exception as e:
        logger.warning(f"[Vault] Could not close DB connections before swap: {e}")
    if db_path.exists():
        try:
            shutil.copy2(db_path, db_path.with_name("nova_pre_restore.db"))
        except Exception as e:
            logger.warning(f"[Vault] Could not stash pre-restore copy: {e}")
    for p in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        try:
            if p.exists():
                p.unlink()
        except Exception as e:
            logger.warning(f"[Vault] Could not remove {p.name} before swap: {e}")


async def restore_latest() -> dict:
    """[P6] Pull the latest VALID snapshot from Drive (Recovery Path).

    Downloads snapshots newest-first and validates each before adopting it, so a
    corrupt newest snapshot neither overwrites the live DB nor crashes startup —
    it is skipped in favour of an older good one. Returns ok=False only when NO
    snapshot is valid, so the caller falls back to Sheets."""
    try:
        service = await asyncio.to_thread(_get_drive_service)
        folder_id = await asyncio.to_thread(_get_or_create_folder, service)

        query = f"'{folder_id}' in parents and name contains '{BACKUP_PREFIX}' and trashed=false"
        results = await asyncio.to_thread(
            lambda: service.files().list(q=query, orderBy="createdTime desc", pageSize=10, fields="files(id, name)").execute()
        )
        files = results.get("files", [])
        if not files: return {"ok": False, "error": "No backups found."}

        db_path = Path(DB_PATH)  # DB_PATH is a str — pathlib calls on it crash the restore
        incoming = db_path.with_name("nova_restore_incoming.db")
        corrupt = 0
        for latest in files:
            try:
                request = service.files().get_media(fileId=latest["id"])
                buf = io.BytesIO()
                downloader = MediaIoBaseDownload(buf, request)
                done = False
                while not done:
                    _, done = await asyncio.to_thread(downloader.next_chunk)

                # Validate on a scratch file BEFORE touching the live DB.
                data = buf.getvalue()
                incoming.write_bytes(data)
                if not _sqlite_ok(incoming):
                    corrupt += 1
                    logger.warning(f"[Vault] Snapshot {latest['name']} failed integrity check — skipping.")
                    continue

                # Valid: close the pool + clear stale sidecars, then write the
                # snapshot as a clean standalone DB. Caller re-inits the pool.
                _prepare_db_for_swap(db_path)
                db_path.write_bytes(data)
                msg = f"[Vault] Restored from {latest['name']}"
                if corrupt:
                    msg += f" (skipped {corrupt} corrupt)"
                logger.info(msg)
                return {"ok": True, "filename": latest["name"], "skipped_corrupt": corrupt}
            except Exception as inner:
                corrupt += 1
                logger.warning(f"[Vault] Snapshot {latest.get('name')} restore attempt failed: {inner}")
            finally:
                try:
                    incoming.unlink()
                except FileNotFoundError:
                    pass

        return {"ok": False, "error": f"no valid snapshot ({corrupt} corrupt of {len(files)})"}
    except Exception as e:
        logger.error(f"[Vault] Restore failed: {e}")
        return {"ok": False, "error": str(e)}

async def vault_scheduler_loop():
    """Background task for automatic backups."""
    logger.info(f"[Vault] Scheduler active (Interval: {BACKUP_INTERVAL_SECONDS}s)")
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        await backup_database()
