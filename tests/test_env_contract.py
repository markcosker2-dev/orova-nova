"""Boot-time config contract (audit B3, Option C, 2026-07-26).

Replaces app/config.py, which crashed on import (`secret_key Field required` —
for a var nothing reads), covered 39 of the 62 env vars actually used, and would
have needed a 106-call-site migration through the revenue-pipeline core to adopt.

Option C was chosen because typing would not have caught the config failures that
actually happened. All three were config that SILENTLY DID NOTHING:
  · BUSINESS_POSTAL_ADDRESS unset -> cold email shipped without the postal
    address 15 U.S.C. §7704 requires;
  · enable_voicemail_detection -> a field Retell had retired;
  · WA_SOS_ENABLED -> gated an endpoint that was anti-bot-walled.
Naming the capability each var gates catches all three.
"""
import pytest

from app.core.hardening import (ENV_ANY_OF, ENV_CAPABILITIES, ENV_REQUIRED,
                                check_env_contract, log_env_contract_once)


@pytest.fixture
def clean_env(monkeypatch):
    """Unset every var the contract knows about, so tests are hermetic."""
    for v in ENV_REQUIRED:
        monkeypatch.delenv(v, raising=False)
    for keys in ENV_CAPABILITIES.values():
        for k in keys:
            monkeypatch.delenv(k, raising=False)
    return monkeypatch


# ─── Required config ─────────────────────────────────────────────

def test_missing_required_config_is_reported_degraded(clean_env):
    r = check_env_contract()
    assert r["status"] == "degraded"
    assert any("DASHBOARD_API_KEY" in m for m in r["missing_required"])


def test_required_config_present_is_ok(clean_env):
    clean_env.setenv("DASHBOARD_API_KEY", "x")
    assert check_env_contract()["status"] == "ok"


def test_absent_optional_config_never_degrades_the_system(clean_env):
    """A deliberately unconfigured feature is not a fault. If optional config
    flipped the status, /health would read unhealthy forever on a $0 stack and
    the signal would be worthless."""
    clean_env.setenv("DASHBOARD_API_KEY", "x")
    r = check_env_contract()
    assert r["status"] == "ok"
    assert r["disabled_capabilities"], "expected optional capabilities to be off"


# ─── Capability reporting ────────────────────────────────────────

def test_a_disabled_capability_names_itself_and_its_vars(clean_env):
    r = check_env_contract()
    assert "cold calling (Retell)" in r["disabled_capabilities"]
    assert "RETELL_API_KEY" in r["disabled_capabilities"]["cold calling (Retell)"]


def test_all_of_capability_needs_every_var(clean_env):
    # Retell needs all three; one present is still disabled.
    clean_env.setenv("RETELL_API_KEY", "k")
    d = check_env_contract()["disabled_capabilities"]
    assert "cold calling (Retell)" in d
    assert "RETELL_API_KEY" not in d["cold calling (Retell)"]   # it IS set
    assert "RETELL_AGENT_ID" in d["cold calling (Retell)"]


def test_any_of_capability_is_satisfied_by_one_provider(clean_env):
    clean_env.setenv("CALENDLY_LINK", "https://cal.example/x")
    assert "meeting booking link" not in check_env_contract()["disabled_capabilities"]


def test_fully_configured_capability_disappears_from_the_report(clean_env):
    for k in ENV_CAPABILITIES["cold calling (Retell)"]:
        clean_env.setenv(k, "v")
    assert "cold calling (Retell)" not in check_env_contract()["disabled_capabilities"]


def test_counts_are_consistent(clean_env):
    r = check_env_contract()
    assert r["capabilities_total"] == len(ENV_CAPABILITIES)
    assert r["capabilities_live"] == r["capabilities_total"] - len(r["disabled_capabilities"])


def test_whitespace_only_value_counts_as_unset(clean_env):
    clean_env.setenv("BUSINESS_POSTAL_ADDRESS", "   ")
    assert "CAN-SPAM postal address" in check_env_contract()["disabled_capabilities"]


# ─── The specific incidents this exists to catch ─────────────────

def test_the_can_spam_postal_gap_is_surfaced(clean_env):
    """The real 2026-07-26 finding: the footer ships an opt-out but no postal
    address because this var is unset, which 15 U.S.C. §7704 requires. It took
    manual code reading to find; the contract reports it at boot."""
    assert "CAN-SPAM postal address" in check_env_contract()["disabled_capabilities"]


def test_the_missing_booking_link_is_surfaced(clean_env):
    """Audit B5 — a Retell 'yes' has nowhere to land."""
    assert "meeting booking link" in check_env_contract()["disabled_capabilities"]


# ─── Contract integrity ──────────────────────────────────────────

def test_any_of_names_reference_real_capabilities():
    unknown = ENV_ANY_OF - set(ENV_CAPABILITIES)
    assert not unknown, f"ENV_ANY_OF names capabilities that do not exist: {unknown}"


def test_no_var_is_both_required_and_capability_gated():
    for capability, keys in ENV_CAPABILITIES.items():
        overlap = set(keys) & set(ENV_REQUIRED)
        assert not overlap, f"{capability} duplicates required var(s) {overlap}"


def test_logging_never_raises(clean_env):
    """Runs inside the FastAPI lifespan — it must never be able to block boot."""
    assert log_env_contract_once()["status"] == "degraded"


def test_the_deleted_config_module_stays_deleted():
    import pathlib
    repo = pathlib.Path(__file__).resolve().parent.parent
    assert not (repo / "app" / "config.py").exists(), (
        "app/config.py was removed (audit B3); it crashed on import and covered "
        "39 of 62 env vars. The contract above replaced it."
    )
