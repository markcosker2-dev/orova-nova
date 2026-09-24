"""Read-only gate for the prospect-initiated Retell demo."""
from scripts.retell_inbound_readiness import (
    EXPECTED_AGENT_ID,
    EXPECTED_EVENT_TYPE_ID,
    EXPECTED_LLM_ID,
    _cal_duration,
    _event_type_id,
    evaluate_snapshot,
)
from unittest.mock import patch


def _healthy_snapshot():
    phone = {
        "inbound_agents": [{"agent_id": EXPECTED_AGENT_ID,
                            "agent_version": "prod", "weight": 1}],
    }
    agent = {
        "agent_id": EXPECTED_AGENT_ID,
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
            {"type": "integration", "name": "check_availability_cal",
             "event_type_id": EXPECTED_EVENT_TYPE_ID},
            {"type": "integration", "name": "book_appointment_cal",
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
