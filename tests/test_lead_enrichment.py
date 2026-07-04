"""Unit tests for lead-enrichment helpers in app/skills/lead_gen_v3.py."""
from app.skills.lead_gen_v3 import _prioritize_email


def test_personal_email_beats_generic_inbox():
    # The owner's personal address must win over info@/contact@ — the whole
    # point of cold outreach is reaching a person, not a shared inbox.
    emails = ["info@acme.com", "john.smith@acme.com", "contact@acme.com"]
    assert _prioritize_email(emails) == "john.smith@acme.com"


def test_owner_inbox_beats_info_inbox():
    # Among generic inboxes, decision-maker ones rank above support/info.
    assert _prioritize_email(["info@acme.com", "owner@acme.com"]) == "owner@acme.com"


def test_junk_addresses_are_dropped():
    # noreply-style addresses are never a valid outreach target.
    assert _prioritize_email(["noreply@acme.com", "info@acme.com"]) == "info@acme.com"
    assert _prioritize_email(["noreply@acme.com"]) == ""


def test_empty_and_single():
    assert _prioritize_email([]) == ""
    assert _prioritize_email(["jane@acme.com"]) == "jane@acme.com"
