"""Build an OFFLINE, quarantined SQLite candidate from a partial API export.

No application imports, dotenv, network, live restore, upload, or deployment.
This candidate is NOT a full copy of production and does not authorize release.
"""
import argparse
import ast
import hashlib
import json
import math
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ORIGIN = "https://orova-nova.onrender.com"
HOLD_STATUS = "Recovery Hold"
MAX_INPUT_BYTES = 64 * 1024 * 1024
EXPECTED_LISTS = {
    "/api/leads?limit=2000&include_invalid=1": "leads",
    "/api/clients": "clients",
    "/api/tasks": "tasks",
    "/api/content": "content",
    "/api/memory": "memories",
    "/api/outreach_outcomes?client_id=0&limit=2000": "outcomes",
    "/api/learned_strategies?client_id=0": "strategies",
    "/api/improvement_log?since_id=0&limit=2000": "entries",
}
MISSING_STATE = [
    "events", "blacklist_and_suppression_state", "approval_state", "state_store",
    "full_chat_history", "unexposed_tables_and_columns", "inactive_strategies",
    "rows_beyond_endpoint_limits",
]


class RecoveryError(ValueError):
    """Sanitized diagnostic: never include a source row or credential."""


def literal_schema(path, constant_name):
    """Read existing trusted DDL without importing or executing app modules."""
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == constant_name
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise RecoveryError("required_schema_unavailable")


def validate_snapshot(snapshot):
    if not isinstance(snapshot, dict) or (
        snapshot.get("source") != SOURCE_ORIGIN
        or snapshot.get("recovery_tier") != "partial_api_projection_only"
        or snapshot.get("full_database_backup") is not False
        or snapshot.get("permits_restart_or_deploy") is not False
        or not isinstance(snapshot.get("captured_at_utc"), str)
        or not set(MISSING_STATE) <= set(snapshot.get("missing_state", []))
    ):
        raise RecoveryError("wrong_snapshot_contract")
    responses = snapshot.get("responses")
    if not isinstance(responses, dict) or set(responses) != {"/health", *EXPECTED_LISTS}:
        raise RecoveryError("incomplete_response_set")
    for endpoint, response in responses.items():
        if not isinstance(response, dict) or response.get("http") != 200:
            raise RecoveryError("source_read_failed")
        payload = response.get("payload")
        if not isinstance(payload, dict):
            raise RecoveryError("invalid_payload")
        if endpoint in EXPECTED_LISTS:
            rows = payload.get(EXPECTED_LISTS[endpoint])
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise RecoveryError("invalid_rows")
            if len(rows) >= 2000:
                raise RecoveryError("endpoint_limit_reached")
    leads = responses["/api/leads?limit=2000&include_invalid=1"]["payload"]["leads"]
    if not leads:
        raise RecoveryError("empty_lead_projection")
    ids = [row.get("id") for row in leads]
    if any(type(value) is not int or value <= 0 for value in ids) or len(set(ids)) != len(ids):
        raise RecoveryError("invalid_or_duplicate_lead_identity")
    for row in leads:
        if any(row.get(key) is not None and not isinstance(row[key], str)
               for key in ("email", "phone", "status")):
            raise RecoveryError("invalid_contact_shape")
    return leads


def _private_output_root(directory):
    directory = Path(directory)
    for parent in (directory, *directory.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise RecoveryError("linked_output_path")
    resolved = directory.resolve()
    # Exported PII must never be placed in the public checkout or owner vault.
    protected = (ROOT, Path("C:/Users/Mike/OneDrive/Desktop/Cosker/OROVA/vault"))
    if any(resolved == item.resolve() or item.resolve() in resolved.parents for item in protected):
        raise RecoveryError("output_must_be_outside_repository_and_vault")
    return resolved


def _schema(connection):
    constants = [
        ("_db_base.py", "CANONICAL_SCHEMA_SQL"),
        ("event_log.py", "_TABLE_SQL"),
        ("self_learning.py", "EXECUTION_TRACES_DDL"),
        ("self_learning.py", "LEARNED_SKILLS_DDL"),
        ("self_learning.py", "USER_PREFERENCES_DDL"),
    ]
    for filename, name in constants:
        connection.executescript(literal_schema(ROOT / "app/core" / filename, name))


def _put_state(connection, key, value):
    connection.execute("INSERT INTO state_store (key, value) VALUES (?, ?)",
                       (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))))


def _insert_lead(connection, row, columns):
    # Identifiers come exclusively from trusted canonical PRAGMA table_info.
    values = {key: row[key] for key in columns if key in row}
    if "evidence" in row:
        values["evidence_json"] = json.dumps(row["evidence"], ensure_ascii=False)
    if isinstance(values.get("ad_signals"), (dict, list)):
        values["ad_signals"] = json.dumps(values["ad_signals"], ensure_ascii=False)
    values.update(status=HOLD_STATUS, phone_verified=0)
    # Missing API columns are unknown, not proof of recent activity/no calls.
    values.setdefault("updated_at", None)
    values.setdefault("created_at", None)
    values.setdefault("call_count", None)
    if not all(value is None or isinstance(value, (str, int, float, bytes)) for value in values.values()):
        raise RecoveryError("non_scalar_lead_field")
    if any(isinstance(value, float) and not math.isfinite(value) for value in values.values()):
        raise RecoveryError("non_finite_lead_field")
    names = ",".join('"' + key + '"' for key in values)
    placeholders = ",".join("?" for _ in values)
    connection.execute(f"INSERT INTO leads ({names}) VALUES ({placeholders})",  # noqa: S608
                       tuple(values.values()))


def verify_candidate(path, expected_ids):
    """Read only: integrity, IDs, held status, no approvals/learning activation."""
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RecoveryError("integrity_failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RecoveryError("foreign_keys_failed")
        rows = connection.execute("SELECT id, status, phone_verified FROM leads").fetchall()
        if {row[0] for row in rows} != set(expected_ids) or any(
            row[1] != HOLD_STATUS or row[2] != 0 for row in rows
        ):
            raise RecoveryError("lead_preservation_or_hold_failed")
        for table in ("learned_strategies", "memories", "events", "drip_campaigns"):
            # Fixed locally trusted table names, never caller input.
            if connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:  # noqa: S608
                raise RecoveryError("unverified_history_activated")
        if connection.execute("SELECT COUNT(*) FROM state_store WHERE key LIKE 'pending%'").fetchone()[0]:
            raise RecoveryError("approval_state_activated")
        source_contacts = connection.execute("SELECT email, phone FROM leads").fetchall()
        states = dict(connection.execute("SELECT key, value FROM state_store").fetchall())
        for key, index in (("email_suppression_list", 0), ("dnc_suppression_list", 1)):
            values = set(json.loads(states.get(key, "[]")))
            if not {row[index] for row in source_contacts if row[index]} <= values:
                raise RecoveryError("contact_hold_failed")
    return {"integrity_ok": True, "foreign_keys_ok": True, "ids_preserved": True,
            "all_recovered_leads_held": True, "unverified_history_inactive": True}


def database_content_sha256(path):
    """Hash SQLite's logical contents privately; never print/export SQL or PII."""
    checksum = hashlib.sha256()
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        for statement in connection.iterdump():
            checksum.update(statement.encode("utf-8"))
            checksum.update(b"\n")
    return checksum.hexdigest()


def prepare(input_path, expected_sha256, output_root):
    input_path = Path(input_path)
    if input_path.is_symlink() or not input_path.is_file() or input_path.stat().st_size > MAX_INPUT_BYTES:
        raise RecoveryError("invalid_input_file")
    raw = input_path.read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if checksum != expected_sha256:
        raise RecoveryError("source_checksum_mismatch")
    snapshot = json.loads(raw)
    leads = validate_snapshot(snapshot)
    root = _private_output_root(output_root)
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="partial-recovery-", dir=root))
    os.chmod(directory, 0o700)
    candidate = directory / "candidate.db"
    restored = directory / "restore-check.db"
    candidate.touch(mode=0o600, exist_ok=False)
    restored.touch(mode=0o600, exist_ok=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_captured_at_utc": snapshot["captured_at_utc"],
        "source_build": snapshot["responses"]["/health"]["payload"].get("build"),
        "source_sha256": checksum, "recovery_tier": "partial_api_projection_only",
        "full_database_backup": False, "permits_restart_or_deploy": False,
        "missing_state": MISSING_STATE, "lead_rows": len(leads),
        "all_recovered_leads_held": True, "production_changed": False,
        "live_restore_transport_verified": False,
    }
    with sqlite3.connect(candidate) as connection:
        _schema(connection)
        columns = [row[1] for row in connection.execute("PRAGMA table_info(leads)").fetchall()]
        for lead in leads:
            _insert_lead(connection, lead, columns)
        _put_state(connection, "dnc_suppression_list", sorted({row["phone"] for row in leads if row.get("phone")}))
        _put_state(connection, "email_suppression_list", sorted({row["email"] for row in leads if row.get("email")}))
        _put_state(connection, "partial_recovery_original_status", {str(row["id"]): row.get("status") for row in leads})
        # Retain exported data privately, without presenting it as measured wins,
        # complete chat history, approvals, or fresh operational knowledge.
        quarantined = {}
        for endpoint, list_name in EXPECTED_LISTS.items():
            if list_name == "leads":
                continue
            values = snapshot["responses"][endpoint]["payload"][list_name]
            quarantined[endpoint] = values
        _put_state(connection, "partial_recovery_quarantined_projections", quarantined)
        manifest["quarantined_projection_rows"] = {key: len(value) for key, value in quarantined.items()}
        _put_state(connection, "partial_recovery_manifest", manifest)
    expected_ids = [row["id"] for row in leads]
    checks = verify_candidate(candidate, expected_ids)
    # Use SQLite hot-copy API, not a WAL-blind file copy; restore into a second
    # unique local file. Neither DB is the application or production DB.
    with sqlite3.connect(candidate.resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(restored) as target:
            source.backup(target)
    checks["isolated_restore_ok"] = verify_candidate(restored, expected_ids) == checks
    if not checks["isolated_restore_ok"]:
        raise RecoveryError("isolated_restore_failed")
    checks["logical_contents_preserved"] = database_content_sha256(candidate) == database_content_sha256(restored)
    if not checks["logical_contents_preserved"]:
        raise RecoveryError("isolated_restore_contents_changed")
    manifest.update(checks)
    manifest["candidate_sha256"] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    manifest["restore_sha256"] = hashlib.sha256(restored.read_bytes()).hexdigest()
    report = directory / "manifest.json"
    with report.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    # chmod is meaningful on POSIX; do not claim it replaces Windows ACLs.
    for path in (candidate, restored, report):
        os.chmod(path, 0o600)
    return {**manifest, "candidate_path": str(candidate), "manifest_path": str(report)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--acknowledge-incomplete", required=True, action="store_true")
    args = parser.parse_args(argv)
    try:
        report = prepare(args.input, args.expected_sha256, args.output_root)
    except (OSError, ValueError, TypeError, sqlite3.Error):
        print(json.dumps({"prepared": False, "error": "offline_recovery_failed",
                          "production_changed": False, "permits_restart_or_deploy": False}))
        return 1
    print(json.dumps({"prepared": True, **report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
