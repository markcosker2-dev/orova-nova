"""Unit tests for lead-enrichment helpers in app/skills/lead_gen_v3.py."""
from app.skills.lead_gen_v3 import _is_noise_email, _prioritize_email


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


def test_noise_email_exact_domain():
    assert _is_noise_email("hi@wixpress.com")
    assert _is_noise_email("errors@sentry.io")
    assert _is_noise_email("HI@EXAMPLE.COM")


def test_noise_email_subdomain():
    # The live leak: subdomain of a blocklisted domain (lead #6, 2026-07-13)
    assert _is_noise_email("605a7baede844d278b89dc95ae0a9123@sentry-next.wixpress.com")
    assert _is_noise_email("x@ingest.sentry.io")


def test_noise_email_no_false_positives():
    # A real business domain that merely *contains* a noise domain must pass
    assert not _is_noise_email("todd@ilusso.com")
    assert not _is_noise_email("owner@notwixpress.company.com")
    assert not _is_noise_email("info@mywix.com.au")
