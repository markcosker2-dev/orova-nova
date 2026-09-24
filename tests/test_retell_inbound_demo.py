"""Pin the consent-first inbound demo path used by manually invited prospects.

The prospect calls OROVA; OROVA never auto-dials them.  This file does not
prove legal compliance or deploy the Retell prompt.  It keeps the reviewed
source of truth from silently losing the disclosure, consent, simulation, and
meeting-handoff boundaries before an owner manually updates Retell.
"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INBOUND = json.loads(
    (ROOT / "app" / "core" / "business_context.json").read_text(encoding="utf-8")
)["retell_inbound"]


def test_inbound_opens_with_ai_disclosure_and_recording_permission():
    opening = INBOUND["begin_message"].lower()
    assert "ai assistant" in opening
    assert "record" in opening
    assert "okay to continue" in opening
    assert "affirmative permission" in INBOUND["compliance"]["recording_consent"].lower()


def test_invited_demo_is_labelled_and_returns_to_diagnosis():
    branch = INBOUND["branches"]["demo_request"].lower()
    assert "simulation" in branch
    assert "explicitly end the simulation" in branch
    assert "too few leads" in branch
    assert "15-minute" in branch


def test_demo_cannot_turn_into_an_unapproved_offer_or_claim():
    branch = INBOUND["branches"]["demo_request"].lower()
    for boundary in ("do not claim", "make no offer", "no price", "no trial", "no pilot"):
        assert boundary in branch


def test_inbound_source_marks_live_demo_prompt_as_unverified():
    drift = INBOUND["_deployed_drift"].lower()
    assert "no invited-demo branch" in drift
    assert "exact dpapi-encrypted rollback snapshot" in drift


def test_booking_remains_truthful_until_migrated_tools_pass_end_to_end():
    goal = INBOUND["goal"].lower()
    branch = INBOUND["branches"]["interested"].lower()
    post_call = INBOUND["_post_call_fields"].lower()
    assert "live-verified at 15 minutes" in goal
    assert "legacy" in goal and "end-to-end" in goal
    assert "do not use" in goal
    assert "only after the tool succeeds" in branch
    assert "preferred times alone are not a booking" in post_call
