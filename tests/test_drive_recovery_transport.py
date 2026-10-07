import hashlib
import json
from unittest.mock import Mock

import pytest

from scripts import drive_recovery_transport as transport


DATA = b"SQLite format 3\x00" + b"quarantined-synthetic-fixture"
NAME = "OROVA_PARTIAL_RECOVERY_STAGING_SYNTHETIC_TEST.db"
PRIVATE = {"shared": False, "permissions": [{"type": "user", "role": "owner"}]}


def service_fixture(matches=None, remote_changes=None, folder_changes=None):
    parent = {
        "id": transport.FOLDER_ID, "name": "OROVA_BACKUPS",
        "mimeType": "application/vnd.google-apps.folder",
        "capabilities": {"canAddChildren": True}, **PRIVATE, **(folder_changes or {}),
    }
    remote = {
        "id": "synthetic_file_id", "name": NAME, "size": str(len(DATA)),
        "mimeType": "application/octet-stream", "parents": [transport.FOLDER_ID],
        "trashed": False, **PRIVATE, **(remote_changes or {}),
    }
    files = Mock()
    files.get.side_effect = lambda **kw: Mock(
        execute=Mock(return_value=parent if kw["fileId"] == transport.FOLDER_ID else remote)
    )
    files.list.return_value.execute.return_value = {"files": matches or []}
    files.create.return_value.execute.return_value = {"id": "synthetic_file_id"}
    service = Mock()
    service.files.return_value = files
    return service, files


def run(service, download=None):
    return transport.stage_and_verify(
        service, DATA, NAME, lambda source: source.read(),
        download or (lambda _request, _size: DATA),
    )


def test_upload_and_actual_download_are_verified_without_promotion():
    service, files = service_fixture()
    receipt = run(service)
    assert receipt["sha256"] == hashlib.sha256(DATA).hexdigest()
    assert receipt["nova_oauth_download_verified"] is True
    assert receipt["automatic_restore_eligible"] is False
    assert receipt["full_database_backup"] is False
    assert receipt["permits_restart_or_deploy"] is False
    assert files.create.call_args.kwargs["body"]["parents"] == [transport.FOLDER_ID]
    assert files.create.call_args.kwargs["media_body"] == DATA
    files.create.return_value.execute.assert_called_once_with(num_retries=0)
    files.get_media.assert_called_once_with(fileId="synthetic_file_id")
    files.update.assert_not_called()
    files.delete.assert_not_called()


def test_exact_existing_staging_file_is_verified_not_reuploaded():
    service, files = service_fixture(matches=[{"id": "synthetic_file_id"}])
    assert run(service)["reused"] is True
    files.create.assert_not_called()


@pytest.mark.parametrize("name", [
    "nova_backup_today.db", "OROVA_PARTIAL_RECOVERY_STAGING_nova_backup_test.db",
    "OROVA_PARTIAL_RECOVERY_STAGING_../unsafe.db", "unexpected.db",
])
def test_unsafe_names_never_reach_google(name):
    service = Mock()
    with pytest.raises(transport.TransportHold):
        transport.stage_and_verify(service, DATA, name, None, None)
    service.files.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"shared": True}, {"permissions": []},
    {"permissions": [{"type": "anyone", "role": "reader"}]},
    {"capabilities": {"canAddChildren": False}}, {"name": "another folder"},
])
def test_folder_gate_fails_closed_before_creation(changes):
    service, files = service_fixture(folder_changes=changes)
    with pytest.raises(transport.TransportHold, match="backup_folder"):
        run(service)
    files.create.assert_not_called()
    files.list.assert_not_called()


def test_ambiguous_existing_names_do_not_create_another_copy():
    service, files = service_fixture(matches=[{"id": "one"}, {"id": "two"}])
    with pytest.raises(transport.TransportHold, match="ambiguous"):
        run(service)
    files.create.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"shared": True}, {"parents": ["another_folder"]}, {"trashed": True},
    {"size": "0"}, {"name": "nova_backup_bad.db"},
])
def test_remote_metadata_and_privacy_must_match(changes):
    service, files = service_fixture(remote_changes=changes)
    with pytest.raises(transport.TransportHold, match="metadata_or_privacy"):
        run(service)
    files.get_media.assert_not_called()


@pytest.mark.parametrize("downloaded", [b"", DATA[:-1] + b"x"])
def test_independent_download_checks_bytes_not_provider_checksum(downloaded):
    service, _files = service_fixture()
    with pytest.raises(transport.TransportHold, match="download"):
        run(service, lambda _request, _size: downloaded)


def test_private_source_hash_and_sqlite_header_are_required(tmp_path):
    source = tmp_path / "candidate.db"
    source.write_bytes(DATA)
    assert transport.candidate_bytes(source, hashlib.sha256(DATA).hexdigest()) == DATA
    with pytest.raises(transport.TransportHold, match="checksum"):
        transport.candidate_bytes(source, "0" * 64)
    source.write_bytes(b"not-a-sqlite-db-at-all")
    with pytest.raises(transport.TransportHold, match="sqlite"):
        transport.candidate_bytes(source, hashlib.sha256(source.read_bytes()).hexdigest())


def test_credentials_or_source_inside_git_are_rejected(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").mkdir()
    with pytest.raises(transport.TransportHold, match="inside_git"):
        transport.private_path(root / "credentials.json")


def test_source_link_is_rejected(tmp_path):
    source = tmp_path / "real.db"
    source.write_bytes(DATA)
    linked = tmp_path / "linked.db"
    try:
        linked.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")
    with pytest.raises(transport.TransportHold, match="linked_private_path"):
        transport.private_path(linked)


def test_download_is_bounded():
    with transport.BoundedDownload(3) as target:
        target.write(b"123")
        with pytest.raises(transport.TransportHold, match="exceeds"):
            target.write(b"4")


def test_cli_without_explicit_approval_never_authenticates(monkeypatch, capsys):
    network = Mock()
    monkeypatch.setattr(transport, "google_transport", network)
    assert transport.main([
        "--candidate", "unused.db", "--expected-sha256", "0" * 64,
        "--credentials-json", "unused.json", "--name", NAME,
    ]) == 2
    network.assert_not_called()
    assert "explicit_upload_approval_required" in capsys.readouterr().out


def test_provider_exception_text_is_never_printed(monkeypatch, capsys, tmp_path):
    source = tmp_path / "candidate.db"
    source.write_bytes(DATA)
    network = Mock(side_effect=RuntimeError("synthetic-private-provider-detail"))
    monkeypatch.setattr(transport, "google_transport", network)
    assert transport.main([
        "--candidate", str(source), "--expected-sha256", hashlib.sha256(DATA).hexdigest(),
        "--credentials-json", str(tmp_path / "private.json"), "--name", NAME,
        "--upload-approved",
    ]) == 2
    output = capsys.readouterr()
    assert "synthetic-private-provider-detail" not in output.out + output.err
    assert "google_transport_failed" in output.out


def test_google_adapter_uses_narrow_scope_and_closes_http(monkeypatch, tmp_path):
    from google.auth.transport import requests as google_requests
    from google.oauth2 import credentials as google_credentials
    import google_auth_httplib2
    from googleapiclient import discovery

    private = tmp_path / "owner-approved.json"
    private.write_text(json.dumps({
        "client_id": "synthetic-client", "client_secret": "synthetic-secret",
        "refresh_token": "synthetic-refresh",
    }), encoding="utf-8")
    credentials = Mock()
    credential_factory = Mock(return_value=credentials)
    monkeypatch.setattr(google_credentials, "Credentials", credential_factory)
    request = Mock()
    monkeypatch.setattr(google_requests, "Request", Mock(return_value=request))
    authorized_http = Mock()
    monkeypatch.setattr(google_auth_httplib2, "AuthorizedHttp", Mock(return_value=authorized_http))
    builder = Mock()
    monkeypatch.setattr(discovery, "build", builder)
    operation = Mock(return_value={"verified": True})
    monkeypatch.setattr(transport, "stage_and_verify", operation)
    assert transport.google_transport(private, DATA, NAME) == {"verified": True}
    assert credential_factory.call_args.kwargs["scopes"] == [transport.SCOPE]
    assert credential_factory.call_args.kwargs["token_uri"] == "https://oauth2.googleapis.com/token"
    credentials.refresh.assert_called_once_with(request)
    assert builder.call_args.kwargs["cache_discovery"] is False
    assert builder.call_args.kwargs["static_discovery"] is True
    authorized_http.close.assert_called_once_with()
