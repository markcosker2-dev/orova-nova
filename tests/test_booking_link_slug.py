"""CAL_COM_EVENT_SLUG normalisation (2026-08-21).

Written after a real production incident. The variable wants a bare
`user/event` slug, but what a human has in their clipboard is the full booking
URL. Pasting it produced:

    https://cal.com/https://cal.com/mark-b.-cosker-j4zcat/discovery-call   -> 404

and **nothing caught it**. The variable was set, `get_booking_link()` returned
a non-empty string, the health check was green, and the only signal would have
been the one prospect who clicked the link and hit a dead page — at the exact
moment he had said yes.

That is the failure mode this repo keeps meeting in different clothes: a value
that is present, plausible, and wrong, with every check passing. The fix is not
to be right about which form was asked for — it is to accept both.
"""
import importlib

import pytest

import app.skills.cal_booking as cb


@pytest.fixture(autouse=True)
def _isolate():
    """Each test drives the module-level config directly and restores it."""
    saved = (cb.CALENDLY_LINK, cb.CAL_COM_EVENT_SLUG, cb.GOOGLE_CALENDAR_BOOKING_LINK)
    cb.CALENDLY_LINK = ""
    cb.CAL_COM_EVENT_SLUG = ""
    cb.GOOGLE_CALENDAR_BOOKING_LINK = ""
    yield
    (cb.CALENDLY_LINK, cb.CAL_COM_EVENT_SLUG, cb.GOOGLE_CALENDAR_BOOKING_LINK) = saved


EXPECTED = "https://cal.com/mark-b.-cosker-j4zcat/discovery-call"


@pytest.mark.parametrize("raw", [
    "mark-b.-cosker-j4zcat/discovery-call",              # the documented form
    "https://cal.com/mark-b.-cosker-j4zcat/discovery-call",  # what actually got pasted
    "http://cal.com/mark-b.-cosker-j4zcat/discovery-call",
    "https://www.cal.com/mark-b.-cosker-j4zcat/discovery-call",
    "cal.com/mark-b.-cosker-j4zcat/discovery-call",
    "  mark-b.-cosker-j4zcat/discovery-call  ",
    "/mark-b.-cosker-j4zcat/discovery-call/",
])
def test_every_plausible_form_yields_one_working_url(raw):
    cb.CAL_COM_EVENT_SLUG = raw
    assert cb.get_booking_link() == EXPECTED


def test_the_production_bug_never_returns():
    """The exact string that reached production, asserted on directly."""
    cb.CAL_COM_EVENT_SLUG = "https://cal.com/mark-b.-cosker-j4zcat/discovery-call"
    link = cb.get_booking_link()
    assert link.count("cal.com") == 1, f"doubled host: {link}"
    assert "cal.com/https" not in link


def test_unset_still_returns_empty_not_a_bare_host():
    """Empty must stay empty — 'https://cal.com/' is worse than no link.

    generate_meeting_intro_email branches on truthiness: empty gives the
    prospect a working 'send me some times' ask, while a bare host gives them
    a confident link to nowhere.
    """
    cb.CAL_COM_EVENT_SLUG = ""
    assert cb.get_booking_link() == ""
    cb.CAL_COM_EVENT_SLUG = "   "
    assert cb.get_booking_link() == ""
    cb.CAL_COM_EVENT_SLUG = "https://cal.com/"
    assert cb.get_booking_link() == ""


def test_priority_order_is_unchanged():
    """Calendly > Cal.com > Google Calendar."""
    cb.CALENDLY_LINK = "https://calendly.com/mark/15min"
    cb.CAL_COM_EVENT_SLUG = "orova/15min"
    cb.GOOGLE_CALENDAR_BOOKING_LINK = "https://calendar.google.com/x"
    assert cb.get_booking_link() == "https://calendly.com/mark/15min"

    cb.CALENDLY_LINK = ""
    assert cb.get_booking_link() == "https://cal.com/orova/15min"

    cb.CAL_COM_EVENT_SLUG = ""
    assert cb.get_booking_link() == "https://calendar.google.com/x"


def test_the_email_carries_the_normalised_link():
    """The link is only worth normalising if the outbound copy uses it."""
    cb.CAL_COM_EVENT_SLUG = "https://cal.com/mark-b.-cosker-j4zcat/discovery-call"
    body = cb.generate_meeting_intro_email("Todd", "LEWCO CONTRACTING")
    assert EXPECTED in body
    assert "cal.com/https" not in body


def test_module_import_does_not_crash_without_env(monkeypatch):
    monkeypatch.delenv("CAL_COM_EVENT_SLUG", raising=False)
    monkeypatch.delenv("CALENDLY_LINK", raising=False)
    monkeypatch.delenv("GOOGLE_CALENDAR_BOOKING_LINK", raising=False)
    reloaded = importlib.reload(cb)
    assert reloaded.get_booking_link() == ""
