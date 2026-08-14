"""A sole operator is a discount, not a disqualification.

Measured 2026-08-09: of 300 WA contractors carrying above the $1M insurance
minimum, 126 (42%) are sole operators, and 58.9% of licensed contractors have
exactly one named principal. They can afford us. What changes is *which pain
the call opens on*, not whether the call is worth making — `retell_pitch`
already branches on `{{crew_status}}` for exactly this reason, and
`outbound_dialer` sends `solo` as a first-class value rather than a fallback.

`discovery_questions.kill_signals` disagreed. It carried
"No payroll (solo operator) - no urgency", which instructed the call to
disqualify the single largest segment of the target list — including
LEWCO CONTRACTING, a 25-year sole operator carrying $2M of cover.

The bug underneath the bug: that entry killed on a **demographic attribute**
while every other kill signal kills on **evidence of no pain**. "Booked into
next spring", "all referral and happy", and "cannot recall a wasted estimate"
already catch a solo owner who genuinely has no pain — and they catch a
six-employee firm with no pain too. Crew size was never the signal.

These tests pin that kill signals stay evidence-based.

The kill signal was not the only place that wrote solo off — it was the one
that did it in a list. Three siblings said the same thing in prose and are
pinned here too (fixed 2026-08-12):

- `icp.early_adopter_qualifiers.w2_crew_on_payroll` claimed "a solo operator
  can coast"
- `competition.real_enemy_1_inertia` said "ONLY a deadline he already feels
  beats it: crew on payroll", excluding solo from the winnable set
- `retell_pitch.objection_handling.too_expensive_price_anchor` scripted "an
  idle week with the crew on payroll" unconditionally — incoherent said to a
  man with no crew

Note these assert on the *claims* rather than sweeping for words like "no
payroll": the corrected text legitimately contains "absence of payroll is NOT
absence of urgency", and a regex that cannot tell a correction from the error
would fail on the fix.
"""
import json
import re
from pathlib import Path

import pytest

BUSINESS_CONTEXT = (
    Path(__file__).resolve().parent.parent / "app" / "core" / "business_context.json"
)

# Terms that describe WHO the prospect is rather than WHAT he told us.
DEMOGRAPHIC = re.compile(
    r"solo|sole[ _-]?(?:owner|operator|proprietor)|one[ -]man|no payroll",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def context() -> dict:
    return json.loads(BUSINESS_CONTEXT.read_text(encoding="utf-8"))


def test_no_kill_signal_disqualifies_on_crew_size(context):
    """Kill on what he said, never on how many principals are on his licence."""
    offenders = [
        s
        for s in context["discovery_questions"]["kill_signals"]
        if DEMOGRAPHIC.search(s)
    ]
    assert not offenders, (
        "kill_signals must not disqualify on crew size — 42% of contractors "
        f"who can afford us are sole operators. Offending entries: {offenders}"
    )


def test_kill_signals_survive_and_stay_behavioural(context):
    """Deleting the bad entry must not empty the list."""
    signals = context["discovery_questions"]["kill_signals"]
    assert len(signals) >= 3, "the evidence-based kill signals are still required"


def test_the_icp_qualifier_treats_crew_as_amplifier_not_gate(context):
    """Payroll raises urgency; its absence does not remove it."""
    q = context["icp"]["early_adopter_qualifiers"]["w2_crew_on_payroll"]
    assert "can coast" not in q.lower(), (
        "a sole operator does not coast — his deadline is his own calendar"
    )
    assert "amplifier" in q.lower() or "not as a gate" in q.lower(), (
        "the qualifier must say crew size scales urgency rather than gating it"
    )


def test_inertia_does_not_exclude_sole_operators(context):
    """Only a felt deadline beats inertia — payroll is the loudest, not the only."""
    inertia = context["competition"]["real_enemy_1_inertia"].lower()
    assert "solo" in inertia, (
        "the inertia analysis must name the solo deadline, not just payroll"
    )
    assert "only a deadline he already feels beats it: crew on payroll" not in inertia


def test_price_objection_branches_on_crew_status(context):
    """'An idle week with the crew on payroll' is incoherent to a sole operator."""
    handler = context["retell_pitch"]["objection_handling"][
        "too_expensive_price_anchor"
    ]
    assert "{{crew_status}}" in handler, "the unit must be matched to crew status"
    assert "if solo" in handler.lower(), "a solo variant of the unit is required"
    assert "if has_crew" in handler.lower(), "the crew variant must stay explicit"


def test_the_call_still_branches_on_crew_status(context):
    """The fix is 'stop disqualifying', not 'stop noticing'.

    Crew status must remain a live variable that selects which pain to open
    on — otherwise removing the kill signal would flatten a real distinction.
    """
    pitch = json.dumps(context["retell_pitch"])
    assert "{{crew_status}}" in pitch, "crew_status must stay a Retell variable"
    assert "solo" in pitch.lower(), "the solo pain branch must survive"
