"""The call script must open on the RIGHT pain: payroll, or his own calendar.

`business_context.json` treats "No payroll (solo operator) - no urgency" as a
kill signal, which conflates two different things. Measured on the WA registry
2026-08-09: of 300 contractors carrying ABOVE the $1M minimum insurance —
i.e. demonstrably doing big jobs — **126 (42%) are sole operators**. They can
afford the retainer. Their urgency is simply personal rather than institutional:
a thin month is money out of their own pocket, and they are also the estimator,
the marketer and the project manager.

So the script branches instead of disqualifying. A contractor with staff feels
payroll every Friday; a one-man operation feels his own calendar. Opening on
the wrong one wastes the single question a cold call gets.

The count comes free from the named principals on the state licence, so the
call never has to spend its question on "do you have guys working with you".

CRITICAL: every {{variable}} in the prompt must be passed by outbound_dialer,
or it renders LITERALLY on a live call. These tests pin that contract.
"""
import json
import pathlib

import pytest

from app.skills.outbound_dialer import _crew_status

CONTEXT_PATH = pathlib.Path("app/core/business_context.json")


def _pitch():
    return json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))["retell_pitch"]


# ── the derivation ──────────────────────────────────────────────────────────

def test_one_principal_is_solo():
    assert _crew_status(1) == "solo"


def test_several_principals_means_a_crew():
    assert _crew_status(3) == "has_crew"
    assert _crew_status(6) == "has_crew"


def test_unknown_is_never_guessed():
    """58.9% of WA contractors are single-principal, so a default is a coin
    flip that opens the call on the wrong pain."""
    for missing in (0, None, "", "n/a", [], {}):
        assert _crew_status(missing) == "unknown", missing


# ── the prompt/dialer contract ──────────────────────────────────────────────

def test_every_prompt_variable_is_actually_passed():
    """An unset {{variable}} renders literally on a live call.

    This is the contract the prompt's own _warning describes, asserted rather
    than trusted.
    """
    from app.skills import outbound_dialer
    src = pathlib.Path(outbound_dialer.__file__).read_text(encoding="utf-8")
    declared = {k.strip("{}") for k in _pitch()["_AVAILABLE_VARIABLES"] if k.startswith("{{")}
    for var in declared:
        assert f'"{var}"' in src, (
            f"{{{{{var}}}}} is declared in the prompt but never passed by "
            f"outbound_dialer — it would render literally on the call")


def test_crew_status_is_declared_for_the_prompt():
    assert "{{crew_status}}" in _pitch()["_AVAILABLE_VARIABLES"]


def test_the_pain_step_branches_on_crew_status():
    step2 = _pitch()["step_2_find_the_pain"]
    blob = json.dumps(step2).lower()
    assert "crew_status" in blob, "step 2 does not branch on crew status"
    assert "payroll" in blob, "the has_crew branch lost its payroll hook"
    assert "solo" in blob, "the solo branch is missing"


def test_the_solo_branch_does_not_reach_for_payroll():
    """A one-man operation has no payroll. Naming it there is instantly wrong
    to the listener and burns the call."""
    gap = _pitch()["step_2_find_the_pain"]["listen_for"]["pain_a_the_gap"]
    solo_half = gap.lower().split("if solo:", 1)
    assert len(solo_half) == 2, "no explicit solo branch in pain_a"
    assert "no payroll" in solo_half[1] or "do not reach for it" in solo_half[1]


# ── the rails that must not move ────────────────────────────────────────────

def test_no_offer_rule_survives():
    """commercial_terms is UNRESOLVED — the script may never imply a price."""
    never = json.dumps(_pitch()["never_say"]).lower()
    for banned in ("no price", "no trial", "no pilot"):
        assert banned in never, f"lost the {banned!r} guard"


def test_compliance_rails_survive():
    comp = _pitch()["compliance"]
    blob = json.dumps(comp).lower()
    assert "business lines only" in blob
    assert "dnc" in blob or "opt" in blob
    assert "9am-5pm" in blob
