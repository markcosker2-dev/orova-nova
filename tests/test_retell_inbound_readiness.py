"""Read-only gate for the prospect-initiated Retell demo."""
from copy import deepcopy
import sys
from unittest.mock import patch

import pytest

from scripts import retell_inbound_readiness as readiness
from scripts.retell_inbound_readiness import (
    EXPECTED_AGENT_ID,
    EXPECTED_EVENT_TYPE_ID,
    EXPECTED_LLM_ID,
    EXPECTED_PHONE_NUMBER,
    _cal_duration,
    _event_type_id,
    evaluate_snapshot,
)


def _healthy_snapshot():
    phone = {
        "phone_number": EXPECTED_PHONE_NUMBER,
        "inbound_agents": [{"agent_id": EXPECTED_AGENT_ID,
                            "agent_version": "prod", "weight": 1}],
    }
    agent = {
        "agent_id": EXPECTED_AGENT_ID,
        "version": 1,
        "is_published": True,
        "assigned_tags": ["prod"],
        "response_engine": {"type": "retell-llm", "llm_id": EXPECTED_LLM_ID,
                            "version": 1},
        "data_storage_setting": "everything_except_pii",
        "handbook_config": {"ai_disclosure": True},
        "post_call_analysis_data": [
            {
                "type": "string",
                "name": "appointment date and time",
                "description": (
                    "The confirmed date and time for Mark's 15-minute call only "
                    "after the booking tool succeeds."
                ),
                "required": False,
            },
            {
                "type": "boolean",
                "name": "appointment booked",
                "description": (
                    "True only after book_calcom_appointment succeeds; preferred "
                    "times alone are not a booking."
                ),
                "required": False,
            },
        ],
    }
    llm = {
        "llm_id": EXPECTED_LLM_ID,
        "version": 1,
        "is_published": True,
        "begin_message": (
            "OROVA, this is Nova, an AI assistant. This call may be recorded. "
            "Is it okay to continue?"
        ),
        "general_prompt": (
            "This is a simulation. Explicitly end it, then ask whether the real "
            "constraint is too few leads or time spent chasing and screening them. "
            "Ask for a 15-minute handoff. No price, no trial, no pilot."
        ),
        "general_tools": [
            {"type": "integration_app", "name": "check_calcom_availability",
             "event_type_id": EXPECTED_EVENT_TYPE_ID},
            {"type": "integration_app", "name": "book_calcom_appointment",
             "event_type_id": EXPECTED_EVENT_TYPE_ID},
        ],
    }
    return phone, agent, llm


def test_healthy_snapshot_clears_blocking_gates():
    phone, agent, llm = _healthy_snapshot()
    llm["general_tools"] = [
        {
            "type": "integration_app",
            "name": "check_calcom_availability",
            "parameters": [{
                "properties": {"event_type_id": {"const": "2804866"}},
            }],
        },
        {
            "type": "integration_app",
            "name": "book_calcom_appointment",
            "parameters": [{
                "properties": {"event_type_id": {"const": "2804866"}},
            }],
        },
    ]
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    assert result["ready"] is True
    assert result["blocker_count"] == 0
    assert result["warning_count"] == 0


def test_known_live_drift_holds_demo_traffic():
    phone, agent, llm = _healthy_snapshot()
    llm["begin_message"] = "OROVA, this is Nova, an AI assistant."
    llm["general_prompt"] = "I can discuss Meta ads and ask for ten minutes."
    result = evaluate_snapshot(phone, agent, llm, cal_duration=30)
    assert result["ready"] is False
    failed = {c["label"] for c in result["checks"] if not c["passed"]}
    assert {"recording consent", "demo simulation", "post-demo diagnosis",
            "15-minute handoff", "no-offer boundary", "Cal duration"} <= failed


def test_wrong_number_binding_is_a_hard_hold():
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["agent_id"] = "agent_wrong"
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    assert result["ready"] is False
    binding = next(c for c in result["checks"] if c["label"] == "number binding")
    assert binding["severity"] == "BLOCK" and not binding["passed"]


def test_unverified_cal_duration_is_a_hard_hold():
    phone, agent, llm = _healthy_snapshot()
    result = evaluate_snapshot(phone, agent, llm, cal_duration=None)
    assert result["ready"] is False
    duration = next(c for c in result["checks"] if c["label"] == "Cal duration")
    assert "independently verified" in duration["detail"]


def test_public_cal_page_can_independently_verify_duration_without_api_key():
    page = (
        '<script>eventTypeId=2804866;data={\\"length\\":15,'
        '\\"title\\":\\"OROVA Calls\\"}</script>'
    ).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return page

    with patch("scripts.retell_inbound_readiness.urllib.request.urlopen",
               return_value=Response()):
        assert _cal_duration({}) == 15


def test_current_cal_integration_reads_nested_constant_event_type():
    tool = {
        "type": "integration_app",
        "name": "check_calcom_availability",
        "parameters": [{
            "properties": {"event_type_id": {"const": "2804866"}},
        }],
    }
    assert _event_type_id(tool) == EXPECTED_EVENT_TYPE_ID


def test_current_cal_tools_clear_tool_and_migration_checks():
    phone, agent, llm = _healthy_snapshot()
    llm["general_tools"] = [
        {
            "type": "integration_app",
            "name": "check_calcom_availability",
            "parameters": [{
                "properties": {"event_type_id": {"const": "2804866"}},
            }],
        },
        {
            "type": "integration_app",
            "name": "book_calcom_appointment",
            "parameters": [{
                "properties": {"event_type_id": {"const": "2804866"}},
            }],
        },
    ]
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    failed = {check["label"] for check in result["checks"] if not check["passed"]}
    assert "Cal availability tool" not in failed
    assert "Cal booking tool" not in failed
    assert "Cal migration" not in failed


def test_legacy_cal_tools_are_a_hard_hold_before_launch():
    phone, agent, llm = _healthy_snapshot()
    llm["general_tools"][0]["name"] = "check_availability_cal"
    llm["general_tools"][1]["name"] = "book_appointment_cal"
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    migration = next(
        check for check in result["checks"] if check["label"] == "Cal migration"
    )
    assert result["ready"] is False
    assert migration["severity"] == "BLOCK"
    assert migration["passed"] is False


def test_unsafe_booking_extraction_is_a_hard_hold():
    phone, agent, llm = _healthy_snapshot()
    agent["post_call_analysis_data"][1]["description"] = (
        "True when the caller agrees and gives a preferred time."
    )
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    check = next(
        item for item in result["checks"]
        if item["label"] == "appointment booked field"
    )
    assert check["severity"] == "BLOCK"
    assert check["passed"] is False


@pytest.mark.parametrize("bound_version", [0, "0", "latest", "latest_published", "staging", None])
def test_stale_or_unresolved_phone_version_holds_traffic(bound_version):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["agent_version"] = bound_version
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("bound_version", [1, "1", "prod"])
def test_exact_published_production_version_clears_binding(bound_version):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["agent_version"] = bound_version
    result = evaluate_snapshot(phone, agent, llm, 15)
    assert result["ready"] is True
    assert result["traffic_ready"] is True
    assert result["inspection_ready"] is True


def test_nonzero_mixed_agent_routing_holds_traffic():
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["weight"] = 0.5
    phone["inbound_agents"].append({
        "agent_id": "agent_unreviewed", "agent_version": 0, "weight": 0.5,
    })
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


def test_valid_zero_weight_unreviewed_route_cannot_receive_traffic():
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"].append({
        "agent_id": "agent_unreviewed", "agent_version": 0, "weight": 0,
    })
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is True


@pytest.mark.parametrize("bad_weight", [
    None, True, False, "0", "0.5", -0.5, 1.5, float("nan"), float("inf"),
    pytest.param(10**1000, id="oversized-int"),
])
def test_malformed_weight_is_not_silently_treated_as_disabled(bad_weight):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"].append({
        "agent_id": "agent_unreviewed", "agent_version": 0, "weight": bad_weight,
    })
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("routes", [
    None, {}, [], "prod", [None], [{"weight": 0}],
    [{"agent_id": EXPECTED_AGENT_ID, "agent_version": "prod"}],
])
def test_malformed_or_empty_routes_hold_traffic(routes):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"] = routes
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("bad_version", [
    True, -1, 1.5, "", " PROD ", pytest.param("1" * 5000, id="oversized-reference"),
])
def test_malformed_disabled_route_also_holds_traffic(bad_version):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"].append({
        "agent_id": "agent_unreviewed", "agent_version": bad_version, "weight": 0,
    })
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("weight", [0, 0.5])
def test_zero_total_or_incomplete_weights_hold_traffic(weight):
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["weight"] = weight
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


def test_duplicate_routes_with_excess_total_weight_hold_traffic():
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"].append(deepcopy(phone["inbound_agents"][0]))
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("field,value", [
    ("phone_number", "+10000000000"),
    ("inbound_webhook_url", "https://example.invalid/override"),
    ("fallback_number", "+10000000000"),
])
def test_unreviewed_number_or_routing_override_holds_traffic(field, value):
    phone, agent, llm = _healthy_snapshot()
    phone[field] = value
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("field,value", [
    ("assigned_tags", []), ("assigned_tags", "prod"), ("is_published", False),
    ("is_published", "true"), ("version", None), ("version", True),
])
def test_unassigned_prod_or_unpublished_agent_holds_traffic(field, value):
    phone, agent, llm = _healthy_snapshot()
    agent[field] = value
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


@pytest.mark.parametrize("engine_version,llm_version", [
    (None, 1), (1, 2), (True, 1), (1, None), (1, True),
])
def test_latest_or_mismatched_llm_cannot_prove_production_ready(engine_version, llm_version):
    phone, agent, llm = _healthy_snapshot()
    agent["response_engine"]["version"] = engine_version
    llm["version"] = llm_version
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


def test_unpublished_llm_holds_traffic():
    phone, agent, llm = _healthy_snapshot()
    llm["is_published"] = False
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is False


def test_numeric_draft_inspection_passes_without_claiming_phone_ready():
    phone, agent, llm = _healthy_snapshot()
    phone["inbound_agents"][0]["agent_version"] = 0
    agent.update(is_published=False, assigned_tags=[])
    llm["is_published"] = False
    result = evaluate_snapshot(phone, agent, llm, 15, inspection_version="1")
    assert result["inspection_ready"] is True
    assert result["inspection_blocker_count"] == 0
    assert result["ready"] is False
    assert result["traffic_ready"] is False


def test_numeric_inspection_requires_exact_returned_version():
    phone, agent, llm = _healthy_snapshot()
    result = evaluate_snapshot(phone, agent, llm, 15, inspection_version="2")
    assert result["inspection_ready"] is False
    assert result["ready"] is False


def test_version_zero_is_a_valid_published_production_version():
    phone, agent, llm = _healthy_snapshot()
    agent["version"] = 0
    agent["response_engine"]["version"] = 0
    llm["version"] = 0
    phone["inbound_agents"][0]["agent_version"] = 0
    assert evaluate_snapshot(phone, agent, llm, 15)["ready"] is True


def test_unassigned_staging_tag_does_not_pass_version_inspection():
    phone, agent, llm = _healthy_snapshot()
    result = evaluate_snapshot(phone, agent, llm, 15, inspection_version="staging")
    assert result["inspection_ready"] is False
    assert result["ready"] is False


@pytest.mark.parametrize("version", ["1", "staging"])
def test_nonprod_cli_reports_inspection_and_holds_traffic(version, monkeypatch, capsys):
    phone, agent, llm = _healthy_snapshot()
    agent.update(is_published=False, assigned_tags=["staging"])
    llm["is_published"] = False
    phone["inbound_agents"][0]["agent_version"] = 0
    monkeypatch.setattr(sys, "argv", ["readiness", "--version", version])
    monkeypatch.setattr(readiness, "load_env", lambda: {"RETELL_API_KEY": "test-only"})
    monkeypatch.setattr(readiness, "_cal_duration", lambda _env: 15)
    reads = []

    def get_json(url, **_kwargs):
        reads.append(url)
        if "/get-phone-number/" in url:
            return 200, phone
        if "/get-agent/" in url:
            return 200, agent
        return 200, llm

    monkeypatch.setattr(readiness, "_get_json", get_json)
    assert readiness.main() == 2
    output = capsys.readouterr().out
    assert "INSPECTION PASSED" in output
    assert "HOLD demo traffic" in output
    assert "READY by machine checks" not in output
    assert any("get-retell-llm/" in url and "?version=1" in url for url in reads)


def test_cli_missing_pinned_llm_version_does_not_read_latest(monkeypatch, capsys):
    phone, agent, _llm = _healthy_snapshot()
    agent["response_engine"].pop("version")
    monkeypatch.setattr(sys, "argv", ["readiness"])
    monkeypatch.setattr(readiness, "load_env", lambda: {"RETELL_API_KEY": "test-only"})
    reads = []

    def get_json(url, **_kwargs):
        reads.append(url)
        if "/get-phone-number/" in url:
            return 200, phone
        if "/get-agent/" in url:
            return 200, agent
        pytest.fail("an unpinned/latest LLM must not be requested")

    monkeypatch.setattr(readiness, "_get_json", get_json)
    assert readiness.main() == 2
    assert "HOLD" in capsys.readouterr().out
    assert len(reads) == 2


@pytest.mark.parametrize("phone_read_ok,prod_published", [(True, True), (False, True), (True, False)])
def test_prod_cli_requires_resolved_published_route(phone_read_ok, prod_published, monkeypatch, capsys):
    phone, agent, llm = _healthy_snapshot()
    if not prod_published:
        # An unassigned prod tag may silently resolve to latest. Publication
        # and assignment must both be proved even if all prompt gates pass.
        agent.update(is_published=False, assigned_tags=[])
    monkeypatch.setattr(sys, "argv", ["readiness"])
    monkeypatch.setattr(readiness, "load_env", lambda: {"RETELL_API_KEY": "test-only"})
    monkeypatch.setattr(readiness, "_cal_duration", lambda _env: 15)

    def get_json(url, **_kwargs):
        if "/get-phone-number/" in url:
            return (200, phone) if phone_read_ok else (503, None)
        if "/get-agent/" in url:
            assert url.endswith("?version=prod")
            return 200, agent
        assert url.endswith("?version=1")
        return 200, llm

    monkeypatch.setattr(readiness, "_get_json", get_json)
    passed = phone_read_ok and prod_published
    assert readiness.main() == (0 if passed else 2)
    output = capsys.readouterr().out
    assert ("READY by machine checks" in output) is passed
    assert "test-only" not in output
    if passed:
        assert "owner-approved phone test before DMs" in output


def test_draft_cli_can_inspect_when_number_read_fails(monkeypatch, capsys):
    _phone, agent, llm = _healthy_snapshot()
    agent.update(is_published=False, assigned_tags=[])
    llm["is_published"] = False
    monkeypatch.setattr(sys, "argv", ["readiness", "--version", "1"])
    monkeypatch.setattr(readiness, "load_env", lambda: {"RETELL_API_KEY": "test-only"})
    monkeypatch.setattr(readiness, "_cal_duration", lambda _env: 15)

    def get_json(url, **_kwargs):
        if "/get-phone-number/" in url:
            return 503, None
        if "/get-agent/" in url:
            return 200, agent
        return 200, llm

    monkeypatch.setattr(readiness, "_get_json", get_json)
    assert readiness.main() == 2
    output = capsys.readouterr().out
    assert "INSPECTION PASSED" in output
    assert "HOLD demo traffic" in output
    assert "READY by machine checks" not in output


def test_cli_rejects_latest_without_reading_credentials_or_providers(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["readiness", "--version", "latest"])
    monkeypatch.setattr(readiness, "load_env", lambda: pytest.fail("latest is not a launch oracle"))
    with pytest.raises(SystemExit) as exc:
        readiness.main()
    assert exc.value.code == 2
