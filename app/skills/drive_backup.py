import os
import io
import time
import shutil
import logging
import requests
import json
try:
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from google.auth.transport.requests import Request as AuthRequest
    HAS_GOOGLE_AUTH = True
except ImportError:
    HAS_GOOGLE_AUTH = False

logger = logging.getLogger(__name__)

# Constants
SCOPES = ["https://www.googleapis.com/auth/drive"]
BACKUP_FILENAME = "orova_cloud_backup.db"

def _get_access_token():
    if not HAS_GOOGLE_AUTH:
        logger.warning("[DRIVE BACKUP] google-auth not installed. Skipping.")
        return None
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(creds_path):
        return None
    try:
        # Service account credentials do not necessarily have a token until refreshed.
        creds = ServiceAccountCredentials.from_service_account_file(creds_path, scopes=SCOPES)
        creds.refresh(AuthRequest())
        return creds.token
    except Exception as e:
        logger.error(f"[DRIVE BACKUP] Failed to get OAuth token: {e}")
        return None

def _find_backup_file_id(token):
    """Searches Google Drive for an existing backup file."""
    headers = {"Authorization": f"Bearer {token}"}
    query = f"name='{BACKUP_FILENAME}' and trashed=false"
    url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id, name)"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        files = res.json().get("files", [])
        if files:
            return files[0]["id"]
    except Exception as e:
        logger.error(f"[DRIVE SEARCH] Error: {e}")
    return None

def upload_database(db_path: str):
    """Back up the local SQLite db to Google Drive."""
    token = _get_access_token()
    if not token:
        logger.warning("⚠️ No Google Credentials found. Cloud Backup skipped.")
        return

    if not os.path.exists(db_path):
        logger.warning(f"⚠️ Cloud Backup skipped — DB not found: {db_path}")
        return

    # Create safe copy to upload (avoids SQLite lock)
    backup_path = db_path + ".backup"
    shutil.copy2(db_path, backup_path)
    
    file_id = _find_backup_file_id(token)
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        with open(backup_path, "rb") as f:
            file_data = f.read()

        if file_id:
            logger.info(f"☁️ [DRIVE BACKUP] Updating existing cloud database ({file_id})...")
            url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
            requests.patch(url, headers=headers, data=file_data, timeout=30)
        else:
            logger.info("☁️ [DRIVE BACKUP] Creating new cloud database backup...")
            url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
            
            metadata = {"name": BACKUP_FILENAME}
            files = {
                'metadata': ('', json.dumps(metadata), 'application/json'),
                'file': (BACKUP_FILENAME, file_data, 'application/octet-stream')
            }
            # requests' multipart helpers don't work with Drive's multipart/related easily;
            # send the multipart/related body explicitly.
            boundary = '-------314159265358979323846'
            body = (
                f"--{boundary}\r\n"
                f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n"
                f"--{boundary}\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n"
            ).encode('utf-8') + file_data + f"\r\n--{boundary}--\r\n".encode('utf-8')

            h = headers.copy()
            h["Content-Type"] = f"multipart/related; boundary={boundary}"
            requests.post(url, headers=h, data=body, timeout=30)
            
        logger.info("✅ [DRIVE BACKUP] Database securely uploaded to Google Drive.")
    except Exception as e:
        logger.error(f"❌ [DRIVE BACKUP] Failed to upload: {e}")
    finally:
        if os.path.exists(backup_path):
            os.remove(backup_path)

def backup_database(db_path: str):
    """Backwards-compatible alias used by app.main shutdown hook."""
    return upload_database(db_path)

def restore_database(db_path: str) -> bool:
    """Download database from Drive if local doesn't exist or is empty."""
    if os.path.exists(db_path) and os.path.getsize(db_path) > 100 * 1024:
        # Local DB already exists and has data (>100KB), no need to restore
        return False

    token = _get_access_token()
    if not token:
        return False

    file_id = _find_backup_file_id(token)
    if not file_id:
        logger.info("[DRIVE RESTORE] No cloud backup found. Starting fresh.")
        return False

    logger.info(f"☁️ [DRIVE RESTORE] Downloading cloud database ({file_id})...")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        res = requests.get(url, headers=headers, timeout=30)
        if res.status_code == 200:
            with open(db_path, "wb") as f:
                f.write(res.content)
            logger.info("✅ [DRIVE RESTORE] Database successfully restored from Cloud!")
            return True
        else:
            logger.error(f"[DRIVE RESTORE] Download failed: HTTP {res.status_code}")
    except Exception as e:
        logger.error(f"❌ [DRIVE RESTORE] Exception: {e}")
    
    return False
