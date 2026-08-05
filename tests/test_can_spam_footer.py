"""Every commercial email carries all seven CAN-SPAM elements (15 U.S.C. §7704).

CAN-SPAM does NOT require prior consent, so cold B2B email to a work address is
lawful in the US. What it does require is the seven rules below — and each
non-compliant message is its own violation at up to **$53,088** (FTC 2026
inflation adjustment). One bad send to 48 recipients, which this project has
already done once, is not a rounding error.

These tests pin the elements that live in the footer. The others are enforced
elsewhere and are asserted where they live:

  1. accurate headers            AgentMail, real inbox
  2. non-deceptive subject       proofreader gate
  3. advertisement disclosure    HERE  <- was missing before 2026-08-06
  4. physical postal address     HERE + fail-closed in send_outreach
  5. working opt-out             HERE
  6. honoured within 10 days     reply monitor -> dnc.add_email_suppression
  7. monitoring affiliates       n/a
"""
import importlib

import pytest

from app.skills import agentmail_skill as am


@pytest.fixture(autouse=True)
def _reset_warn_flag():
    am._warned_no_postal = False
    yield


# ── element 3: advertisement disclosure ────────────────────────────────────

def test_footer_discloses_that_the_message_is_an_advertisement(monkeypatch):
    """The FTC mandates no particular wording, only that the disclosure be
    clear and conspicuous. It must be PRESENT — this was missing entirely."""
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    out = am._apply_compliance_footer("Hi Dave, quick question about your schedule.")
    assert "advertisement" in out.lower()


def test_disclosure_ships_even_without_a_postal_address(monkeypatch):
    """The postal address is a separate element with its own gate; a missing
    address must not silently drop the ad disclosure too."""
    monkeypatch.delenv("BUSINESS_POSTAL_ADDRESS", raising=False)
    out = am._apply_compliance_footer("Hi Dave.")
    assert "advertisement" in out.lower()


# ── element 4: physical postal address ─────────────────────────────────────

def test_postal_address_is_included_when_set(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    out = am._apply_compliance_footer("Hi Dave.")
    assert "PO Box 1, Portland OR 97201" in out


@pytest.mark.asyncio
async def test_send_fails_closed_without_a_postal_address(monkeypatch):
    """The 48-email incident: this path used to warn-and-send. Any real address
    unblocks it — a PO box counts."""
    monkeypatch.delenv("BUSINESS_POSTAL_ADDRESS", raising=False)

    async def _not_suppressed(_):
        return False
    monkeypatch.setattr("app.core.dnc.is_email_suppressed", _not_suppressed)

    result = await am.send_outreach(to="dave@example.com", subject="Hi",
                                    body="Hello", skip_proofread=True)
    assert result["status"] == "error"
    assert result.get("skipped") is True
    assert "BUSINESS_POSTAL_ADDRESS" in result["error"]


# ── element 5: working opt-out ─────────────────────────────────────────────

def test_footer_carries_an_opt_out(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    out = am._apply_compliance_footer("Hi Dave.")
    assert am._OPT_OUT_LINE in out


def test_footer_is_idempotent(monkeypatch):
    """A drip lane that re-footers a body must not stack disclosures."""
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    once = am._apply_compliance_footer("Hi Dave.")
    twice = am._apply_compliance_footer(once)
    assert once == twice
    assert once.lower().count("advertisement") == 1


# ── element 6: opt-outs are honoured, not merely detected ──────────────────

@pytest.mark.parametrize("reply", [
    "please remove me from your list",
    "Not interested, thanks",
    "unsubscribe",
    "stop emailing me",
    "do not contact me again",
    "leave me alone",
    # Adversarial: opt-out language mixed with buying language. The obligation
    # is unconditional, so these must still register as an opt-out.
    "take me off this list but send me pricing first",
    "wrong person - but I am interested in a demo, call me",
])
def test_optout_language_is_detected_and_classified_cold(reply):
    """The reply lane only records a suppression when the intent resolves COLD.
    That gate is safe ONLY because the keyword classifier reads the same
    opt-out list and short-circuits before the LLM. If either list drifts, a
    legal obligation starts depending on a probabilistic classifier — so both
    halves are asserted together, deliberately."""
    assert am.is_optout_reply("Re: quick question", reply) is True
    assert am._keyword_classify_reply("Re: quick question", reply) == "COLD"


@pytest.mark.parametrize("reply", ["Sounds good, call me", "Can you send pricing?"])
def test_ordinary_interest_is_not_an_opt_out(reply):
    assert am.is_optout_reply("Re: hi", reply) is False


def test_optout_detection_and_classification_share_one_keyword_list():
    """Two copies of this list would drift, and the drift would be silent."""
    src = importlib.import_module("app.skills.agentmail_skill")
    assert src._OPTOUT_REPLY_SIGNALS, "opt-out signal list is empty"
    for sig in src._OPTOUT_REPLY_SIGNALS:
        assert src.is_optout_reply("", sig) is True, sig
        assert src._keyword_classify_reply("", sig) == "COLD", sig


# ── the whole footer, once ─────────────────────────────────────────────────

def test_all_footer_elements_present_together(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "PO Box 1, Portland OR 97201")
    out = am._apply_compliance_footer("Hi Dave, quick question.")
    assert "Hi Dave, quick question." in out          # body preserved
    assert "OROVA" in out                             # sender identified
    assert "PO Box 1, Portland OR 97201" in out       # element 4
    assert "advertisement" in out.lower()             # element 3
    assert am._OPT_OUT_LINE in out                    # element 5
