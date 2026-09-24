"""Encrypted Retell backup schema and DPAPI round-trip."""
import json
import os

import pytest

from scripts.retell_private_backup import _protect, _unprotect, _validate


def _snapshot():
    from scripts.retell_inbound_readiness import EXPECTED_AGENT_ID, EXPECTED_LLM_ID

    return {
        "schema": "orova-retell-rollback-v1",
        "created_at": "2026-09-23T00:00:00+00:00",
        "agent_id": EXPECTED_AGENT_ID,
        "llm_id": EXPECTED_LLM_ID,
        "resources": {
            "phone_number": {"phone_number": "+10000000000"},
            "agent_prod": {"version": 0},
            "agent_v0": {"version": 0},
            "retell_llm": {"version": 0},
        },
    }


def test_snapshot_schema_requires_every_rollback_resource():
    snapshot = _snapshot()
    _validate(snapshot)
    del snapshot["resources"]["retell_llm"]
    with pytest.raises(RuntimeError, match="missing"):
        _validate(snapshot)


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI only")
def test_dpapi_round_trip_does_not_leave_plaintext():
    raw = json.dumps(_snapshot()).encode()
    encrypted = _protect(raw)
    assert encrypted != raw
    assert b"phone_number" not in encrypted
    assert _unprotect(encrypted) == raw
