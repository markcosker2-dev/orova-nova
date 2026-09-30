"""Local verification must fail visibly and honor current configuration."""
import argparse
import json
import subprocess

from scripts import nova


def test_runtime_environment_overrides_old_local_value(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ZERO_BUDGET_MODE=0\n", encoding="utf-8")
    monkeypatch.setattr(nova, "_env_path", lambda: env_file)
    monkeypatch.setenv("ZERO_BUDGET_MODE", "1")

    assert nova.load_env()["ZERO_BUDGET_MODE"] == "1"


def test_required_missing_check_fails_release_gate(monkeypatch, capsys):
    def run_check(argv, **kwargs):
        if "ruff" in argv:
            raise FileNotFoundError("missing required verifier")
        return subprocess.CompletedProcess(argv, 0, stdout="checked", stderr="")

    monkeypatch.setattr(nova.subprocess, "run", run_check)
    assert nova.cmd_gates(argparse.Namespace()) == 1
    assert "not installed" in capsys.readouterr().out


def test_benchmark_failure_cannot_be_hidden_by_success_text(monkeypatch, capsys):
    seen = []

    def run_check(argv, **kwargs):
        seen.append(argv)
        rc = 1 if "pytest" in argv else 0
        return subprocess.CompletedProcess(argv, rc, stdout="1 failed, 10 passed", stderr="")

    monkeypatch.setattr(nova.subprocess, "run", run_check)
    monkeypatch.setattr(nova, "http", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert nova.cmd_benchmark(argparse.Namespace(focused=False)) == 1
    assert any("tests/" in argv for argv in seen)
    assert "LOCAL BENCHMARKS PASS" not in capsys.readouterr().out


def test_focused_benchmarks_keep_permission_and_durability_scenarios(monkeypatch, capsys):
    seen = []

    def run_check(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="checks complete", stderr="")

    monkeypatch.setattr(nova.subprocess, "run", run_check)
    monkeypatch.setattr(nova, "http", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert nova.cmd_benchmark(argparse.Namespace(focused=True)) == 0
    pytest_argv = next(argv for argv in seen if "pytest" in argv)
    assert "tests/test_zero_budget_repair.py" in pytest_argv
    assert "tests/test_outreach_approval_chokepoint.py" in pytest_argv
    assert "tests/test_lead_storage_gate.py" in pytest_argv
    assert "tests/test_sheets_restore.py" in pytest_argv
    assert "tests/test_retell_inbound_readiness.py" in pytest_argv
    assert "LOCAL BENCHMARKS PASS" in capsys.readouterr().out


def test_benchmark_report_keeps_measurements_not_raw_output(tmp_path, monkeypatch):
    def run_check(argv, **kwargs):
        output = "diagnostic detail must not be copied\n7 passed in 0.1s\n"
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="private diagnostic")

    monkeypatch.setattr(nova.subprocess, "run", run_check)
    report = tmp_path / "measurements.json"
    assert nova.cmd_benchmark(argparse.Namespace(focused=True, report=report)) == 0
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert saved["passed"] and saved["profile"] == "focused"
    assert all(check["passed"] and check["elapsed_seconds"] >= 0 for check in saved["checks"])
    assert next(check for check in saved["checks"] if check["check"] == "tests")["pytest_summary"] == "7 passed in 0.1s"
    assert "diagnostic" not in report.read_text(encoding="utf-8")


def test_missing_benchmark_verifier_is_recorded_as_failure(tmp_path, monkeypatch):
    def run_check(argv, **kwargs):
        if argv[0] == "node":
            raise FileNotFoundError("controlled missing Node")
        return subprocess.CompletedProcess(argv, 0, stdout="checks complete", stderr="")

    monkeypatch.setattr(nova.subprocess, "run", run_check)
    report = tmp_path / "measurements.json"
    assert nova.cmd_benchmark(argparse.Namespace(focused=True, report=report)) == 1
    saved = json.loads(report.read_text(encoding="utf-8"))
    assert not saved["passed"]
    assert not next(check for check in saved["checks"] if check["check"] == "dashboard")["passed"]
