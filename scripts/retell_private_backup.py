#!/usr/bin/env python
"""Create and verify an exact, encrypted Retell rollback snapshot.

The snapshot is written outside the repository and encrypted with Windows
DPAPI for the current Windows account. Nothing from the API response is printed.

    python scripts/retell_private_backup.py backup
    python scripts/retell_private_backup.py verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.retell_inbound_readiness import (
    EXPECTED_AGENT_ID,
    EXPECTED_LLM_ID,
    EXPECTED_PHONE_NUMBER,
    RETELL_BASE,
    _get_json,
    load_env,
)


BACKUP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OROVA" / "private-backups"
DESCRIPTION = "OROVA Retell exact rollback snapshot"


def _protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI backup encryption is available only on Windows")
    import win32crypt  # type: ignore[import-not-found]

    return win32crypt.CryptProtectData(data, DESCRIPTION, None, None, None, 0)


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI backup decryption is available only on Windows")
    import win32crypt  # type: ignore[import-not-found]

    return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]


def _read(url: str, key: str, label: str) -> dict[str, Any]:
    status, payload = _get_json(url, bearer=key)
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError(f"Retell {label} backup read failed (status={status})")
    return payload


def collect_snapshot() -> dict[str, Any]:
    """Read the exact live resources required to reconstruct the inbound flow."""
    env = load_env()
    key = env.get("RETELL_API_KEY", "")
    if not key:
        raise RuntimeError("RETELL_API_KEY is not configured")
    phone_path = EXPECTED_PHONE_NUMBER.replace(" ", "")
    resources = {
        "phone_number": _read(
            f"{RETELL_BASE}/get-phone-number/{phone_path}", key, "phone number"
        ),
        "agent_prod": _read(
            f"{RETELL_BASE}/get-agent/{EXPECTED_AGENT_ID}?version=prod",
            key,
            "production agent",
        ),
        "agent_v0": _read(
            f"{RETELL_BASE}/get-agent/{EXPECTED_AGENT_ID}?version=0",
            key,
            "agent version 0",
        ),
        "retell_llm": _read(
            f"{RETELL_BASE}/get-retell-llm/{EXPECTED_LLM_ID}", key, "response engine"
        ),
    }
    return {
        "schema": "orova-retell-rollback-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_id": EXPECTED_AGENT_ID,
        "llm_id": EXPECTED_LLM_ID,
        "resources": resources,
    }


def _validate(snapshot: dict[str, Any]) -> None:
    if snapshot.get("schema") != "orova-retell-rollback-v1":
        raise RuntimeError("backup schema is not recognised")
    if snapshot.get("agent_id") != EXPECTED_AGENT_ID:
        raise RuntimeError("backup contains another agent")
    if snapshot.get("llm_id") != EXPECTED_LLM_ID:
        raise RuntimeError("backup contains another response engine")
    resources = snapshot.get("resources")
    required = {"phone_number", "agent_prod", "agent_v0", "retell_llm"}
    if not isinstance(resources, dict) or not required <= resources.keys():
        raise RuntimeError("backup is missing a rollback resource")


def backup() -> Path:
    snapshot = collect_snapshot()
    _validate(snapshot)
    plaintext = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    encrypted = _protect(plaintext)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = BACKUP_DIR / f"retell-inbound-{stamp}.json.dpapi"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(encrypted)
    temporary.replace(destination)

    manifest = {
        "schema": "orova-retell-backup-manifest-v1",
        "created_at": snapshot["created_at"],
        "ciphertext_sha256": hashlib.sha256(encrypted).hexdigest(),
        "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
        "encrypted_bytes": len(encrypted),
        "agent_version": snapshot["resources"]["agent_prod"].get("version"),
        "agent_published": snapshot["resources"]["agent_prod"].get("is_published"),
        "llm_version": snapshot["resources"]["retell_llm"].get("version"),
        "llm_published": snapshot["resources"]["retell_llm"].get("is_published"),
    }
    destination.with_suffix(destination.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    verify(destination)
    return destination


def latest_backup() -> Path:
    candidates = sorted(BACKUP_DIR.glob("retell-inbound-*.json.dpapi"))
    if not candidates:
        raise RuntimeError("no encrypted Retell backup exists")
    return candidates[-1]


def verify(path: Path | None = None) -> Path:
    target = path or latest_backup()
    encrypted = target.read_bytes()
    snapshot = json.loads(_unprotect(encrypted).decode("utf-8"))
    if not isinstance(snapshot, dict):
        raise RuntimeError("decrypted backup is not an object")
    _validate(snapshot)
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("ciphertext_sha256") != hashlib.sha256(encrypted).hexdigest():
            raise RuntimeError("encrypted backup hash does not match manifest")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypted Retell rollback backup")
    parser.add_argument("command", choices=("backup", "verify"))
    parser.add_argument("--path", type=Path, help="specific encrypted backup to verify")
    args = parser.parse_args()
    try:
        target = backup() if args.command == "backup" else verify(args.path)
    except Exception as exc:  # noqa: BLE001 - print only the safe exception summary
        print(f"HOLD: {exc}")
        return 2
    action = "created and verified" if args.command == "backup" else "verified"
    print(f"OK: encrypted Retell rollback backup {action}")
    print(f"Location: {target}")
    print("Contents were not printed. Windows DPAPI current-user protection is required to decrypt it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
