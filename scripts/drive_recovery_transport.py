"""Explicit staging transport; never restore, promote, prune, or boot Nova.

Uses a private owner-approved OAuth JSON file, not dotenv/application imports.
Creates/reuses one non-auto-restore file in the existing private backup folder,
then downloads the remote bytes and independently verifies their SHA-256.
This does NOT turn an incomplete candidate into a full database backup.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER_ID = "1M3NpifCpgMh_NWHq0iBSuzuc15klL-Js"
SCOPE = "https://www.googleapis.com/auth/drive.file"
MAX_BYTES = 64 * 1024 * 1024
FILE_FIELDS = "id,name,size,parents,mimeType,shared,trashed,permissions(type,role)"


class TransportHold(ValueError):
    """Only fixed diagnostic codes, never provider responses or source data."""


def private_path(value: Path) -> Path:
    value = Path(value)
    protected = (ROOT, Path("C:/Users/Mike/OneDrive/Desktop/Cosker/OROVA/vault"))
    for parent in (value, *value.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise TransportHold("linked_private_path")
        if (parent / ".git").exists():
            raise TransportHold("private_path_inside_git")
    resolved = value.resolve()
    if any(p.resolve() == resolved or p.resolve() in resolved.parents for p in protected):
        raise TransportHold("private_path_inside_repository_or_vault")
    return resolved


def candidate_bytes(path: Path, expected_sha: str) -> bytes:
    path = private_path(path)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha):
        raise TransportHold("invalid_expected_sha256")
    if not path.is_file() or not 16 <= path.stat().st_size <= MAX_BYTES:
        raise TransportHold("invalid_candidate_size")
    # One immutable buffer closes the hash-versus-upload file-change window.
    with path.open("rb") as source:
        data = source.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not data.startswith(b"SQLite format 3\x00"):
        raise TransportHold("invalid_sqlite_candidate")
    if hashlib.sha256(data).hexdigest() != expected_sha.lower():
        raise TransportHold("candidate_checksum_mismatch")
    return data


def validate_name(name: str) -> None:
    if not re.fullmatch(r"OROVA_PARTIAL_RECOVERY_STAGING_[A-Za-z0-9_]+\.db", name):
        raise TransportHold("invalid_staging_name")
    if "nova_backup_" in name.lower():
        raise TransportHold("auto_restore_name_forbidden")


def owner_private(metadata: dict) -> bool:
    permissions = metadata.get("permissions")
    return (
        metadata.get("shared") is False
        and isinstance(permissions, list)
        and len(permissions) == 1
        and permissions[0].get("type") == "user"
        and permissions[0].get("role") == "owner"
    )


def stage_and_verify(service, data: bytes, name: str, media_factory, download) -> dict:
    validate_name(name)
    files = service.files()
    parent = files.get(
        fileId=FOLDER_ID,
        fields="id,name,mimeType,shared,permissions(type,role),capabilities(canAddChildren)",
    ).execute(num_retries=0)
    if not (
        parent.get("id") == FOLDER_ID and parent.get("name") == "OROVA_BACKUPS"
        and parent.get("mimeType") == "application/vnd.google-apps.folder"
        and parent.get("capabilities", {}).get("canAddChildren") is True
        and owner_private(parent)
    ):
        raise TransportHold("backup_folder_not_private_and_writable")
    found = files.list(
        q=f"'{FOLDER_ID}' in parents and name='{name}' and trashed=false",
        pageSize=2, fields="nextPageToken,files(id)",
    ).execute(num_retries=0)
    matches = found.get("files", [])
    if not isinstance(matches, list) or len(matches) > 1 or found.get("nextPageToken"):
        raise TransportHold("ambiguous_staging_files")
    reused = bool(matches)
    if reused:
        file_id = matches[0].get("id")
    else:
        # No retries: an ambiguous creation is reconciled by the exact-name read
        # on the next explicitly authorized invocation, never blindly replayed.
        file_id = files.create(
            body={"name": name, "parents": [FOLDER_ID], "mimeType": "application/octet-stream"},
            media_body=media_factory(io.BytesIO(data)), fields="id",
        ).execute(num_retries=0).get("id")
    if not isinstance(file_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
        raise TransportHold("staging_id_unverified")
    remote = files.get(fileId=file_id, fields=FILE_FIELDS).execute(num_retries=0)
    if not (
        remote.get("id") == file_id and remote.get("name") == name
        and remote.get("parents") == [FOLDER_ID] and remote.get("trashed") is False
        and remote.get("mimeType") == "application/octet-stream"
        and str(remote.get("size")) == str(len(data)) and owner_private(remote)
    ):
        raise TransportHold("staging_metadata_or_privacy_unverified")
    expected = hashlib.sha256(data).hexdigest()
    actual = download(files.get_media(fileId=file_id), len(data))
    if not isinstance(actual, bytes) or len(actual) != len(data):
        raise TransportHold("download_size_mismatch")
    if hashlib.sha256(actual).hexdigest() != expected:
        raise TransportHold("download_checksum_mismatch")
    return {
        "file_id": file_id, "name": name, "bytes": len(data), "sha256": expected,
        "reused": reused, "owner_only": True, "nova_oauth_download_verified": True,
        "automatic_restore_eligible": False, "full_database_backup": False,
        "permits_restart_or_deploy": False,
    }


class BoundedDownload(io.BytesIO):
    def __init__(self, expected_size: int):
        super().__init__()
        self.expected_size = expected_size

    def write(self, value):
        if self.tell() + len(value) > self.expected_size:
            raise TransportHold("download_exceeds_expected_size")
        return super().write(value)


def google_transport(credentials_path: Path, data: bytes, name: str) -> dict:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    import httplib2

    values = json.loads(private_path(credentials_path).read_text(encoding="utf-8"))
    required = ("client_id", "client_secret", "refresh_token")
    if not isinstance(values, dict) or not all(isinstance(values.get(k), str) and values[k] for k in required):
        raise TransportHold("private_credentials_incomplete")
    credentials = Credentials(
        token=None, refresh_token=values["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token", client_id=values["client_id"],
        client_secret=values["client_secret"], scopes=[SCOPE],
    )
    credentials.refresh(Request())
    authorized_http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=30))
    service = build("drive", "v3", http=authorized_http, cache_discovery=False, static_discovery=True)

    def media(stream):
        return MediaIoBaseUpload(stream, mimetype="application/octet-stream", resumable=False)

    def download(request, size):
        with BoundedDownload(size) as target:
            transfer = MediaIoBaseDownload(target, request, chunksize=1024 * 1024)
            done = False
            while not done:
                _, done = transfer.next_chunk(num_retries=0)
            return target.getvalue()

    try:
        return stage_and_verify(service, data, name, media, download)
    finally:
        authorized_http.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--credentials-json", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--upload-approved", action="store_true")
    args = parser.parse_args(argv)
    # Libraries must not dump credential-bearing HTTP details into stderr.
    for logger in ("google", "googleapiclient", "httplib2", "urllib3"):
        logging.getLogger(logger).setLevel(logging.CRITICAL)
    try:
        if not args.upload_approved:
            raise TransportHold("explicit_upload_approval_required")
        validate_name(args.name)
        data = candidate_bytes(args.candidate, args.expected_sha256)
        receipt = google_transport(args.credentials_json, data, args.name)
    except TransportHold as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)}))
        return 2
    except Exception as exc:
        # Never print exception text, tracebacks, request/response bodies or URLs.
        status = getattr(getattr(exc, "resp", None), "status", None)
        print(json.dumps({"status": "HOLD", "reason": "google_transport_failed", "http_status": status}))
        return 2
    print(json.dumps({"status": "VERIFIED", **receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
