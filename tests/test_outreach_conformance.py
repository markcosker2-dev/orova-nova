"""Owner-playbook conformance tests (interview 2026-07-11).

Mark's positioning rules: NEVER cite past clients/results in outreach
(forward-looking + system promise only), cadence capped at 1 initial +
3 follow-ups (break-up email last, nothing after it), no fake urgency.
These tests pin every template surface an email can be generated from, so
a future copy edit that reintroduces "our clients saw…" fails CI.

Sources: vault/hermesclaw-orova/playbook/{outreach-voice,red-lines}.md and
the machine twin business_context.json (case_studies + outreach.cadence_policy).
"""
import json
import re
from pathlib import Path

from app.skills.email_sequence_skill import SEQUENCES

ROOT = Path(__file__).resolve().parents[1]

# Phrases that always indicate a past-client claim in outreach copy.
_PAST_CLAIM_RE = re.compile(
    r"(one of our .{0,20}clients|client of ours|our clients (see|saw)|"
    r"we've been getting (great )?results|most of our clients|"
    r"clients just had|we helped a \{?industry\}? business)",
    re.IGNORECASE,
)


def _all_sequence_text():
    for seq_name, seq in SEQUENCES.items():
        for i, email in enumerate(seq["emails"]):
            yield f"{seq_name}[{i}]", email["subject_template"] + " " + email["body_template"]


def test_no_past_client_claims_in_any_sequence():
    violations = [where for where, text in _all_sequence_text() if _PAST_CLAIM_RE.search(text)]
    assert violations == [], f"past-client claims found in: {violations}"


def test_cold_intro_is_initial_plus_three_followups():
    emails = SEQUENCES["cold_intro_drip"]["emails"]
    # Step 0 is the initial (worker sends its own and starts the drip at step 1),
    # steps 1-3 are the three follow-ups. Owner cap: nothing beyond that.
    assert len(emails) == 4, f"cold_intro_drip must be 1 initial + 3 follow-ups, has {len(emails)}"


def test_breakup_email_is_last_and_final():
    emails = SEQUENCES["cold_intro_drip"]["emails"]
    assert "last note" in emails[-1]["body_template"].lower()  # honest break-up closes the sequence


def test_business_context_outreach_has_no_past_claims():
    ctx = json.loads((ROOT / "app" / "core" / "business_context.json").read_text(encoding="utf-8"))
    outreach_text = json.dumps(ctx["outreach"]) + json.dumps(ctx["case_studies"])
    assert not _PAST_CLAIM_RE.search(outreach_text)


def test_business_context_carries_cadence_policy_and_scripts():
    ctx = json.loads((ROOT / "app" / "core" / "business_context.json").read_text(encoding="utf-8"))
    cadence = ctx["outreach"]["cadence_policy"]
    assert "3 follow-up" in cadence["rule"]
    assert any("urgency" in n.lower() for n in cadence["never"])
    scripts = ctx["case_studies"]
    assert "privacy" in scripts["when_asked_for_proof"].lower()
    assert scripts["when_asked_am_i_your_first"].startswith("No")


def test_no_fake_urgency_phrases_in_sequences():
    urgency = re.compile(r"(only \d+ (slots?|spots?)|act now|expires|last chance)", re.IGNORECASE)
    violations = [where for where, text in _all_sequence_text() if urgency.search(text)]
    assert violations == []
