"""Synthetic-only offline recovery tests. No app, credentials or live network."""
import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import prepare_partial_recovery as recovery


def snapshot():
    result = {"source": recovery.SOURCE_ORIGIN,
              "captured_at_utc": "2026-10-03T00:00:00+00:00",
              "recovery_tier": "partial_api_projection_only",
              "full_database_backup": False, "permits_restart_or_deploy": False,
              "missing_state": recovery.MISSING_STATE.copy(),
              "responses": {"/health": {"http": 200, "payload": {"build": "synthetic"}}}}
    for endpoint, key in recovery.EXPECTED_LISTS.items():
        result["responses"][endpoint] = {"http": 200, "payload": {key: []}}
    result["responses"]["/api/leads?limit=2000&include_invalid=1"]["payload"]["leads"] = [
        {"id": 7, "business": "Synthetic Builder", "email": "test@example.invalid",
         "phone": "+12025550123", "status": "Awaiting Approval", "phone_verified": 1,
         "evidence": {"source": "synthetic"}, "ad_signals": ["synthetic"],
         "outreach_ready": True},
        {"id": 12, "business": "Other Synthetic Builder", "status": "Archived"},
    ]
    result["responses"]["/api/memory"]["payload"]["memories"] = [{"id": "old", "content": "Unverified old summary"}]
    result["responses"]["/api/learned_strategies?client_id=0"]["payload"]["strategies"] = [
        {"id": "legacy", "active": 1, "win_rate": 0.99, "sample_size": 200}]
    return result


def save_input(tmp_path, data=None):
    path = tmp_path / "source.json"
    raw = json.dumps(data or snapshot()).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def test_private_candidate_preserves_ids_and_enforces_holds(tmp_path):
    path, digest = save_input(tmp_path)
    original = path.read_bytes()
    report = recovery.prepare(path, digest, tmp_path / "private")
    assert report["lead_rows"] == 2
    assert report["isolated_restore_ok"] is True
    assert report["logical_contents_preserved"] is True
    assert report["full_database_backup"] is False
    assert report["permits_restart_or_deploy"] is False
    assert report["live_restore_transport_verified"] is False
    assert path.read_bytes() == original
    with sqlite3.connect(report["candidate_path"]) as conn:
        assert conn.execute("SELECT id, status, phone_verified FROM leads ORDER BY id").fetchall() == [
            (7, "Recovery Hold", 0), (12, "Recovery Hold", 0)]
        assert conn.execute("SELECT updated_at FROM leads").fetchall() == [(None,), (None,)]
        assert conn.execute("SELECT created_at, call_count FROM leads").fetchall() == [(None, None), (None, None)]
        assert json.loads(conn.execute("SELECT evidence_json FROM leads WHERE id=7").fetchone()[0]) == {"source": "synthetic"}
        values = dict(conn.execute("SELECT key, value FROM state_store").fetchall())
        assert json.loads(values["email_suppression_list"]) == ["test@example.invalid"]
        assert json.loads(values["dnc_suppression_list"]) == ["+12025550123"]
        assert json.loads(values["partial_recovery_original_status"]) == {"7": "Awaiting Approval", "12": "Archived"}
        quarantine = json.loads(values["partial_recovery_quarantined_projections"])
        assert len(quarantine["/api/memory"]) == 1
        assert len(quarantine["/api/learned_strategies?client_id=0"]) == 1
        assert conn.execute("SELECT COUNT(*) FROM learned_strategies").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 0


def test_each_run_is_unique_and_does_not_overwrite(tmp_path):
    path, digest = save_input(tmp_path)
    first = recovery.prepare(path, digest, tmp_path / "private")
    second = recovery.prepare(path, digest, tmp_path / "private")
    assert first["candidate_path"] != second["candidate_path"]


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(source="https://example.invalid"),
    lambda data: data.update(full_database_backup=True),
    lambda data: data.update(permits_restart_or_deploy=True),
    lambda data: data.update(missing_state=[]),
    lambda data: data["responses"].pop("/api/memory"),
    lambda data: data["responses"]["/api/memory"].update(http=403),
    lambda data: data["responses"]["/api/memory"].update(payload={}),
    lambda data: data["responses"]["/api/leads?limit=2000&include_invalid=1"]["payload"].update(leads=[]),
])
def test_bad_contracts_rejected_before_output(tmp_path, mutation):
    data = snapshot()
    mutation(data)
    path, digest = save_input(tmp_path, data)
    output = tmp_path / "private"
    with pytest.raises(recovery.RecoveryError):
        recovery.prepare(path, digest, output)
    assert not output.exists()


@pytest.mark.parametrize("value", [0, -1, True, "7", None])
def test_invalid_ids_fail_closed(value):
    data = snapshot()
    data["responses"]["/api/leads?limit=2000&include_invalid=1"]["payload"]["leads"][0]["id"] = value
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_snapshot(data)


def test_duplicate_ids_rejected():
    data = snapshot()
    rows = data["responses"]["/api/leads?limit=2000&include_invalid=1"]["payload"]["leads"]
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_snapshot(data)


def test_hash_mismatch_never_writes(tmp_path):
    path, _ = save_input(tmp_path)
    output = tmp_path / "private"
    with pytest.raises(recovery.RecoveryError, match="checksum"):
        recovery.prepare(path, "0" * 64, output)
    assert not output.exists()


def test_refuses_repository_output(tmp_path):
    path, digest = save_input(tmp_path)
    with pytest.raises(recovery.RecoveryError, match="outside"):
        recovery.prepare(path, digest, recovery.ROOT / ".unlazy/private-recovery")


def test_verifier_catches_removed_suppression(tmp_path):
    path, digest = save_input(tmp_path)
    report = recovery.prepare(path, digest, tmp_path / "private")
    with sqlite3.connect(report["candidate_path"]) as conn:
        conn.execute("DELETE FROM state_store WHERE key = 'email_suppression_list'")
    with pytest.raises(recovery.RecoveryError, match="contact_hold"):
        recovery.verify_candidate(Path(report["candidate_path"]), [7, 12])


def test_cli_sanitizes_errors(tmp_path, capsys):
    path, _ = save_input(tmp_path)
    assert recovery.main(["--input", str(path), "--expected-sha256", "bad",
                          "--output-root", str(tmp_path / "private"),
                          "--acknowledge-incomplete"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"] == "offline_recovery_failed"
    assert "test@example.invalid" not in json.dumps(result)


def test_restore_contents_hash_detects_other_field_changes(tmp_path):
    path, digest = save_input(tmp_path)
    report = recovery.prepare(path, digest, tmp_path / "private")
    candidate = Path(report["candidate_path"])
    prior = recovery.database_content_sha256(candidate)
    with sqlite3.connect(candidate) as conn:
        conn.execute("UPDATE leads SET business = 'Changed Synthetic' WHERE id=7")
    assert recovery.database_content_sha256(candidate) != prior


def test_endpoint_limit_fails_closed():
    data = snapshot()
    data["responses"]["/api/memory"]["payload"]["memories"] = [{} for _ in range(2000)]
    with pytest.raises(recovery.RecoveryError, match="limit"):
        recovery.validate_snapshot(data)


def test_bad_contact_shape_rejected_before_output(tmp_path):
    data = snapshot()
    data["responses"]["/api/leads?limit=2000&include_invalid=1"]["payload"]["leads"][0]["email"] = {"unsafe": "shape"}
    path, digest = save_input(tmp_path, data)
    with pytest.raises(recovery.RecoveryError, match="contact_shape"):
        recovery.prepare(path, digest, tmp_path / "private")
    assert not (tmp_path / "private").exists()
