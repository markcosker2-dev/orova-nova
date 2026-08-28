"""A pattern-guessed email must never be emailable (2026-07-31).

The 2026-07-25 incident: 48 cold emails went out to addresses `_guess_email`
INVENTED from an owner name plus a domain. Microsoft answered `550 5.4.1` —
Directory-Based Edge Blocking, meaning "no such mailbox". Those were never real
addresses; they were plausible-looking strings.

The mechanism was a single constant. `_OUTREACH_MIN_EMAIL_CONF` was 35, and a
guessed email scores exactly 35, so `>= 35` passed. `outreach_ready` returned
`emailable: True` with an EMPTY blocker list for a fabricated address.

Provenance was already recorded correctly — `email_status='guessed'`,
`email_source='pattern_guess'`. Nothing read it. A label no gate acts on is not
a control; that is the same lesson as ADR-0012 living only in a document.
"""
import pytest

from app.skills.lead_validator import contact_confidence, outreach_ready

_BASE = {
    "business": "Cherry Design + Build",
    "owner": "Marc Schock",
    "owner_confidence": 90,
    "email": "marc@cherrydesignbuild.com",
    "phone": "+12065550103",
}


def test_guessed_email_is_not_emailable():
    """The regression this file exists for."""
    lead = dict(_BASE, email_status="guessed", email_source="pattern_guess")
    result = outreach_ready(lead)

    assert contact_confidence(lead)["email"] == 35
    assert result["emailable"] is False, "a fabricated address must never be emailable"
    assert result["has_direct_email"] is False
    assert any("confidence" in b or "unverified" in b for b in result["blockers"]), \
        f"the blocker must say why, got {result['blockers']}"


def test_guessed_email_lead_is_still_callable():
    """The phone lane must not be collateral damage — licence leads have a real
    name and a real phone from a legal record, and those are unaffected."""
    lead = dict(_BASE, email_status="guessed", email_source="pattern_guess")
    result = outreach_ready(lead)

    assert result["callable"] is True
    assert result["ready"] is True, "still reachable by phone, so still outreach-ready"


@pytest.mark.parametrize("status,expected_conf", [("found", 65), ("verified", 90)])
def test_real_emails_remain_emailable(status, expected_conf):
    """A scraped or verified address is a fact about the world, not a guess."""
    lead = dict(_BASE, email_status=status, email_source="website_scrape")

    assert contact_confidence(lead)["email"] == expected_conf
    assert outreach_ready(lead)["emailable"] is True


def test_mx_ok_does_not_rescue_a_guess():
    """The old comment justified 35 as 'guessed-but-MX-ok'. MX proves the DOMAIN
    accepts mail; it says nothing about whether the MAILBOX exists. That gap is
    exactly what Directory-Based Edge Blocking rejected."""
    lead = dict(_BASE, email_status="guessed", email_source="pattern_guess",
                email_mx_ok=True)
    assert outreach_ready(lead)["emailable"] is False


def test_no_email_lead_is_unchanged():
    """Licence-registry leads carry no email at all — behaviour must not shift."""
    lead = dict(_BASE, email="", email_status="", email_source="")
    result = outreach_ready(lead)

    assert result["emailable"] is False
    assert result["callable"] is True
    assert "no email" in result["blockers"]


def test_generic_inbox_still_rejected():
    """info@/sales@ was already rejected; raising the bar must not regress it."""
    lead = dict(_BASE, email="info@cherrydesignbuild.com",
                email_status="found", email_source="website_scrape")
    result = outreach_ready(lead)

    assert result["emailable"] is False
    assert any("generic" in b for b in result["blockers"])
