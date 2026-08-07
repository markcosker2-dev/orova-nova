"""Nova's chat persona must not carry a stale ICP (2026-08-02).

Owner report:
    MC:   "whats our ICP"
    NOVA: "Our Ideal Customer Profile (ICP) is luxury/exotic car dealers."

That string was hardcoded in nova_chat.NOVA_PERSONA, written before ADR-0012
re-ranked the ICP on 2026-07-23. Nova was confidently telling Mark the wrong
ICP — the same root cause as the hunt rotation still searching for exotic car
dealers (#126): a business fact copied into a module that does not own it.

Per CLAUDE.md's single-source-of-truth rule the persona now DERIVES the ICP
from business_context.json. These tests pin that it stays derived, so a future
ICP change cannot leave the chat layer behind again.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.nova_chat import NOVA_PERSONA, _canonical_icp_line, _FALLBACK_ICP

ROOT = Path(__file__).resolve().parents[1]


def _canonical_icp() -> dict:
    return json.loads(
        (ROOT / "app" / "core" / "business_context.json").read_text(encoding="utf-8")
    )["icp"]


def test_persona_does_not_call_exotic_auto_the_icp():
    """The exact regression. 'exotic car dealers' must not be what Nova
    answers with when asked what the ICP is."""
    lowered = NOVA_PERSONA.lower()
    icp_claim = lowered.split("orova's icp is:")[1].split("\n")[0]
    for banned in ("exotic", "car dealer", "automotive"):
        assert banned not in icp_claim, (
            f"{banned!r} is being presented as the ICP: {icp_claim!r}"
        )


def test_persona_states_the_adr_0012_lead_vertical():
    lowered = NOVA_PERSONA.lower()
    assert "custom home builder" in lowered or "high-end remodel" in lowered


def test_icp_line_is_derived_from_business_context_not_hardcoded():
    """Every primary vertical in the canonical file must appear in the line —
    proving it is read, not restated."""
    line = _canonical_icp_line().lower()
    for vertical in _canonical_icp()["primary_verticals"]:
        head = vertical.split("(")[0].strip().rstrip(" —-").lower()
        assert head in line, f"canonical vertical missing from persona: {head!r}"


def test_icp_line_drops_the_economic_parentheticals():
    """The justification text belongs in the ADR, not in every system prompt."""
    line = _canonical_icp_line()
    assert "$100K+" not in line
    assert "retainer" not in line.lower()


def test_exotic_auto_is_explicitly_marked_opportunistic():
    """ADR-0012 keeps it opportunistic rather than excluded, so the persona has
    to say which it is — silence is what produced the wrong answer before."""
    lowered = NOVA_PERSONA.lower()
    assert "opportunistic" in lowered
    assert "exotic" in lowered  # named, but as the exclusion


def test_persona_forbids_implying_clients_exist():
    assert "no clients" in NOVA_PERSONA.lower()


def test_unreadable_context_falls_back_vague_not_confidently_wrong():
    """A missing file must not resurrect a specific stale claim."""
    with patch("builtins.open", side_effect=OSError("gone")):
        line = _canonical_icp_line()
    assert line == _FALLBACK_ICP
    assert "exotic" not in line.lower()


@pytest.mark.parametrize("subject", ["clients", "case studies", "past results"])
def test_persona_names_each_thing_that_does_not_exist(subject):
    """Assert the PROHIBITION is present, not that the word is absent.

    (An earlier version of this test banned the substring 'case stud' — which
    matched the prohibition itself, "no clients, no case studies and no past
    results". Banning a word is the wrong shape of assertion for a rule that
    has to name the thing it forbids.)
    """
    lowered = NOVA_PERSONA.lower()
    assert subject in lowered
    assert "never imply otherwise" in lowered
