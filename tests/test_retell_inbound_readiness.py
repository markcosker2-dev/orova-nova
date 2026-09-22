"""Read-only gate for the prospect-initiated Retell demo."""
from scripts.retell_inbound_readiness import (
    EXPECTED_AGENT_ID,
    EXPECTED_EVENT_TYPE_ID,
    EXPECTED_LLM_ID,
    evaluate_snapshot,
)


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
    result = evaluate_snapshot(phone, agent, llm, cal_duration=15)
    assert result["ready"] is True
    assert result["blocker_count"] == 0
    # The synthetic fixture intentionally uses the legacy tool names, so the
    # time-bound migration reminder remains a warning rather than pretending
    # that prompt/booking correctness and vendor migration are the same gate.
    assert result["warning_count"] == 1


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
