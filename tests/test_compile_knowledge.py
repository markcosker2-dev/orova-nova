"""Tests for the knowledge compiler (ADR-0005, M1).

The critical one — test_no_drift_between_canonical_and_runtime — is the CI gate:
it fails the build if business_context.json pricing ever diverges from the
canonical facts, which is the whole point of a single source of truth.
"""
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import compile_knowledge as ck  # noqa: E402


def _business_context() -> dict:
    return json.loads(ck.BUSINESS_CONTEXT_PATH.read_text(encoding="utf-8"))


def test_references_resolve_to_one_value():
    """The service-fee node is referenced, not copied: {{ref:...}} -> int."""
    facts = ck.load_facts()
    p1 = next(p for p in facts["packages"] if p["id"] == "package_1")
    assert p1["price_monthly_usd"] == 4000           # resolved from pricing.service_fee_p1_usd
    assert p1["tiers_usd"]["1_month"] == 4000         # same node, referenced again
    p2 = next(p for p in facts["packages"] if p["id"] == "package_2")
    assert p2["price_monthly_usd"] == 5000


def test_canonical_facts_validate():
    assert ck.validate(ck.load_facts()) == []


def test_no_drift_between_canonical_and_runtime():
    """CI GATE: business_context.json must agree with canonical facts."""
    assert ck.lint(ck.load_facts(), _business_context()) == []


def test_lint_catches_price_drift():
    facts = ck.load_facts()
    bc = _business_context()
    for svc in bc["services"]:
        if "Package 1" in svc.get("name", ""):
            svc["price_monthly_usd"] = 4500          # plant a drift
    errors = ck.lint(facts, bc)
    assert any("drift" in e and "Package 1" in e for e in errors)


def test_lint_catches_spam_word_in_outbound_copy():
    facts = ck.load_facts()
    bc = _business_context()
    bc.setdefault("outreach", {}).setdefault("initial_email_framework", {})[
        "example"
    ] = "Hi — act now for a risk-free deal!"          # plant banned terms
    errors = ck.lint(facts, bc)
    assert any("act now" in e for e in errors)


def test_rule_documentation_is_not_flagged():
    """The linter checks OUTBOUND COPY, not the rules that document banned words.
    business_context.email_rules.rules legitimately names spam words to forbid."""
    facts = ck.load_facts()
    bc = _business_context()
    # sanity: the rules array does mention a banned term somewhere, yet lint is clean
    assert ck.lint(facts, bc) == []


def test_facts_md_is_deterministic_and_current():
    facts = ck.load_facts()
    assert ck.emit_facts_md(facts) == ck.emit_facts_md(facts)   # deterministic
    on_disk = ck.FACTS_MD_PATH.read_text(encoding="utf-8")
    assert on_disk == ck.emit_facts_md(facts), "facts.md is stale — run compile_knowledge.py --write"


# ── meeting duration (2026-08-21) ───────────────────────────────────────────
# Four different answers to "how long is this call" were live at once: copy
# said 10, 15 and "10-15" across 24 places, and the cal.com event said 30.
# None of them was checked, so all four could be true forever.

def test_meeting_duration_is_canonical():
    facts = ck.load_facts()
    assert isinstance(facts["meeting"]["duration_minutes"], int)


def test_no_meeting_duration_drift_in_the_tree():
    """The CI gate: prospect-facing copy must not contradict canonical."""
    assert ck.lint_meeting_duration(ck.load_facts()) == []


def test_lint_catches_meeting_duration_drift(tmp_path, monkeypatch):
    """Injecting a wrong duration into real copy must fail the build."""
    target = ck.ROOT / "app" / "skills" / "email_templates.py"
    original = target.read_text(encoding="utf-8")
    facts = ck.load_facts()
    canon = facts["meeting"]["duration_minutes"]
    wrong = 10 if canon != 10 else 20
    try:
        target.write_text(
            original.replace(f"{canon}-minute", f"{wrong}-minute", 1), encoding="utf-8")
        errors = ck.lint_meeting_duration(facts)
        assert errors, "drift in prospect-facing copy was not caught"
        assert "meeting drift" in errors[0]
        assert "email_templates.py" in errors[0]
    finally:
        target.write_text(original, encoding="utf-8")
    assert ck.lint_meeting_duration(facts) == []


def test_speed_to_lead_is_not_a_meeting_duration():
    """'call the homeowner in 5 minutes' is the differentiator, not a length.

    It sits directly beside the word 'call', so a naive proximity rule flags it
    on every run — and a linter that cries wolf gets switched off. The
    preposition is what separates a latency from a duration.
    """
    facts = ck.load_facts()
    bc = ck.BUSINESS_CONTEXT_PATH.read_text(encoding="utf-8")
    assert "in 5 minutes" in bc, "the speed-to-lead claim should still be in the copy"
    assert not any("business_context.json" in e and "5 minute" in e
                   for e in ck.lint_meeting_duration(facts))


def test_timers_are_not_flagged_as_meeting_durations():
    """ceo_brain's 30-minute auto-execute and worker's cron are not asks."""
    facts = ck.load_facts()
    errors = ck.lint_meeting_duration(facts)
    assert not any("ceo_brain" in e or "worker.py" in e for e in errors)



def test_lint_catches_spelled_out_duration_drift(tmp_path, monkeypatch):
    """A CALL SCRIPT writes "ten minutes", never "10 minutes".

    The digit-only pattern this linter shipped with could not see the one form
    the drift actually takes, so "ten minutes" sat in retell_pitch and
    retell_inbound for four months while canonical was 15 — the exact failure
    the linter exists to prevent, invisible to the linter.
    """
    facts = ck.load_facts()
    canon = facts["meeting"]["duration_minutes"]
    words = {5: "five", 10: "ten", 15: "fifteen", 20: "twenty", 30: "thirty"}
    wrong_word = words[10] if canon != 10 else words[20]

    target = ck.ROOT / "app" / "core" / "business_context.json"
    original = target.read_text(encoding="utf-8")
    try:
        # The spoken ask names the PERSON, not the artefact — no "call" in sight.
        target.write_text(
            original.replace(
                f"Would you be open to {words[canon]} minutes with Mark?",
                f"Would you be open to {wrong_word} minutes with Mark?", 1),
            encoding="utf-8")
        errors = ck.lint_meeting_duration(facts)
        assert errors, "spelled-out duration drift was not caught"
        assert any("business_context.json" in e for e in errors)
    finally:
        target.write_text(original, encoding="utf-8")
    assert ck.lint_meeting_duration(facts) == []


def test_spelled_out_canonical_duration_is_not_flagged():
    """"fifteen minutes with Mark" is correct copy and must stay silent."""
    facts = ck.load_facts()
    canon = facts["meeting"]["duration_minutes"]
    bc = ck.BUSINESS_CONTEXT_PATH.read_text(encoding="utf-8")
    assert canon == 15 and "fifteen minutes with Mark" in bc, (
        "the canonical spoken ask should be in the copy")
    assert ck.lint_meeting_duration(facts) == []


def test_speed_to_lead_survives_the_spelled_out_pattern():
    """"within five minutes" is the differentiator and must never be flagged.

    Adding word-numbers to the pattern put the single most repeated phrase in
    the entire pitch in scope for the first time. If this ever fails, the
    linter starts crying wolf on the one line that appears in every script.
    """
    facts = ck.load_facts()
    bc = ck.BUSINESS_CONTEXT_PATH.read_text(encoding="utf-8")
    assert "within five minutes" in bc
    assert not any("five minute" in e for e in ck.lint_meeting_duration(facts))
