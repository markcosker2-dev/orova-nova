"""Name-engine foundation (2026-07-22): persist `state` so the SoS registry can
fire in the waterfall/reenrich, and stop generic role mailboxes (leads@, hi@…)
from counting as a direct email in the outreach bar.

Root cause captured in vault/20-ops/sessions/2026-07-22-improvement-research.md
(Appendix 2): leads carried state=None, so contact_waterfall._source_registry —
the authoritative, zero-fabrication name source — never had a state to query.
"""
from app.skills.lead_gen_v3 import _state_from_address
from app.skills.lead_validator import outreach_ready


# ── _state_from_address: parse the RIGHT state, never guess ──────────────────

def test_state_from_standard_mailing_address():
    assert _state_from_address("123 Main St, Los Gatos, CA 95030") == "CA"
    assert _state_from_address("456 Oak Ave, Portland, OR 97201") == "OR"
    assert _state_from_address("1 Grand Blvd, Reno, NV 89501") == "NV"
    assert _state_from_address("789 1st St, Seattle, WA") == "WA"          # no ZIP
    assert _state_from_address("500 Ln, Phoenix, AZ 85001-1234") == "AZ"   # ZIP+4


def test_state_from_full_state_name():
    assert _state_from_address("Beverly Hills, California") == "CA"


def test_state_never_guesses_when_absent():
    # A wrong state sends the registry to the wrong Secretary of State — worse
    # than none. So anything not confidently a state must return "".
    assert _state_from_address("") == ""
    assert _state_from_address("no state here") == ""
    assert _state_from_address("123 Main St") == ""
    assert _state_from_address("Some City, ZZ 00000") == ""   # ZZ is not a real code


# ── outreach bar: generic role mailboxes are not a "direct" email ────────────

def test_leads_at_is_generic_not_direct():
    lead = {"owner": "Eric Curran", "email": "leads@drivesfexoticcars.com",
            "email_status": "found", "phone": "+14047334400"}
    r = outreach_ready(lead)
    assert not r["has_direct_email"]          # leads@ no longer leaks through
    assert r["callable"] and not r["emailable"]
    assert any("generic" in b for b in r["blockers"])


def test_personal_email_still_counts_as_direct():
    lead = {"owner": "Eric Curran", "email": "eric@drivesfexoticcars.com",
            "email_status": "found", "phone": "+14047334400"}
    r = outreach_ready(lead)
    assert r["has_direct_email"] and r["emailable"] and r["ready"]
