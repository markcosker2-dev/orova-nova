"""
vault_skill.py — OROVA Survivability Layer
Periodic + on-demand backup of nova.db to Google Drive.
Restore command pulls latest snapshot back to disk post-redeploy.
"""

import asyncio
import io
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

    Tries user OAuth env vars first, then falls back to the service-account
    file (GOOGLE_APPLICATION_CREDENTIALS) that drive_backup.py and the
    Sheets integration already use — one set of Render credentials powers
    every Drive feature.
    """
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

    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if os.path.exists(creds_path):
        sa_creds = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=sa_creds, cache_discovery=False)

    raise ValueError(
        "No Google Drive credentials: set GOOGLE_REFRESH_TOKEN/GOOGLE_CLIENT_ID/"
        "GOOGLE_CLIENT_SECRET or GOOGLE_APPLICATION_CREDENTIALS."
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

async def restore_latest() -> dict:
    """[P6] Pull latest snapshot from Drive (Recovery Path)."""
    try:
        service = await asyncio.to_thread(_get_drive_service)
        folder_id = await asyncio.to_thread(_get_or_create_folder, service)

        query = f"'{folder_id}' in parents and name contains '{BACKUP_PREFIX}' and trashed=false"
        results = await asyncio.to_thread(
            lambda: service.files().list(q=query, orderBy="createdTime desc", pageSize=1, fields="files(id, name)").execute()
        )
        files = results.get("files", [])
        if not files: return {"ok": False, "error": "No backups found."}

        latest = files[0]
        request = service.files().get_media(fileId=latest["id"])
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = await asyncio.to_thread(downloader.next_chunk)

        if DB_PATH.exists():
            shutil.copy2(DB_PATH, DB_PATH.with_name("nova_pre_restore.db"))
        
        DB_PATH.write_bytes(buf.getvalue())
        logger.info(f"[Vault] Restored from {latest['name']}")
        return {"ok": True, "filename": latest["name"]}
    except Exception as e:
        logger.error(f"[Vault] Restore failed: {e}")
        return {"ok": False, "error": str(e)}

async def vault_scheduler_loop():
    """Background task for automatic backups."""
    logger.info(f"[Vault] Scheduler active (Interval: {BACKUP_INTERVAL_SECONDS}s)")
    while True:
        await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
        await backup_database()
