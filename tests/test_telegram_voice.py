"""Nova's proactive Telegram messages should read like a colleague's.

Before this, every notification was a form:

    📞 **Call Initiated**

    I am now calling **LEWCO CONTRACTING** (Patrick Lewis).
    Call ID: `abc123`

Bold header, emoji field labels, an internal `[Client 0]`, a call ID no human
uses, and "I am now calling" — a sentence nobody says out loud. It reported the
EVENT and left Mark to derive the meaning.

These tests pin the properties that make the difference, not the wording:
no internal identifiers, an explicit ask (or an explicit "nothing needed"),
and silence when there is genuinely nothing to say.
"""
import re

import pytest

from app.core import telegram_voice as tv

# Things Mark can neither read nor act on.
INTERNAL = re.compile(r"\[Client \d+\]|Call ID|`[a-f0-9]{8,}`|Traceback|"
                      r"\*\*[A-Z][A-Z ]+\*\*", re.IGNORECASE)

ALL_MESSAGES = [
    tv.hunt_complete(5, "custom home builder", "LEWCO CONTRACTING", 83, 3),
    tv.hunt_failed("HTTPSConnectionPool(host='data.wa.gov'): timeout"),
    tv.new_reply("pat@example-contracting.com", "Re: your schedule",
                 "yeah give me a call", "HOT", True),
    tv.call_starting("LEWCO CONTRACTING", "Dana Whitfield"),
    tv.call_failed("LEWCO CONTRACTING", "no answer"),
    tv.call_outcome("Dana", "+12065551234", "Tuesday morning", "Went well.", True),
    tv.appointment_booked("Dana", "dana@example-contracting.com", "Tue 9am", "Intro"),
    tv.booking_link_sent("Dana", "LEWCO", "https://cal.com/x"),
    tv.booking_link_failed("dana@example-contracting.com", 3),
    tv.cold_lead_call("LEWCO CONTRACTING", "Dana", "+12065551234", 7),
    tv.cold_escalation_done(3, 7),
    tv.first_touch_call("LEWCO CONTRACTING", "Dana", "+12065551234"),
]


@pytest.mark.parametrize("msg", [m for m in ALL_MESSAGES if m])
def test_no_internal_identifiers_reach_mark(msg):
    """client_id, call IDs and tracebacks belong in the log, not his phone."""
    found = INTERNAL.search(msg)
    assert not found, f"internal detail leaked into a notification: {found.group(0)!r}"


@pytest.mark.parametrize("msg", [m for m in ALL_MESSAGES if m])
def test_at_most_one_emoji(msg):
    """One emoji helps him scan a busy phone. Four is a form."""
    emoji = re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", msg)
    assert len(emoji) <= 1, f"{len(emoji)} emoji in one message: {emoji}"


@pytest.mark.parametrize("msg", [m for m in ALL_MESSAGES if m])
def test_nothing_shouts_in_bold_headers(msg):
    assert "**" not in msg, "a bold header is a template, not a colleague"


def test_a_hunt_that_found_nothing_stays_quiet():
    """Re-finding the same businesses is normal since #171 and is not news."""
    assert tv.hunt_complete(0, "custom home builder") is None


def test_an_empty_escalation_stays_quiet():
    assert tv.cold_escalation_done(0, 7) is None


def test_a_real_escalation_speaks_up():
    assert tv.cold_escalation_done(2, 7) is not None


def test_a_hunt_names_its_best_lead_not_just_a_count():
    """A bare count says nothing about whether the hunt was any good."""
    msg = tv.hunt_complete(5, "custom home builder", "LEWCO CONTRACTING", 83, 3)
    assert "LEWCO CONTRACTING" in msg
    assert "83" in msg
    assert "sole operators" in msg


def test_a_hot_reply_says_what_was_done_about_it():
    msg = tv.new_reply("pat@x.com", "Re: schedule", "call me", "HOT", True)
    assert "interested" in msg.lower()
    assert "approve" in msg.lower(), "he needs to know it is waiting on him"


def test_a_cold_reply_does_not_ask_him_to_do_anything():
    msg = tv.new_reply("pat@x.com", "Re: schedule", "not interested", "COLD", False)
    assert "no" in msg.lower()
    assert "nothing needed" in msg.lower()


def test_only_a_real_yes_celebrates():
    yes = tv.call_outcome("Dana", "+12065551234", "Tuesday", "Good call.", True)
    no = tv.call_outcome("Dana", "+12065551234", "", "Was busy.", False)
    assert "🎉" in yes
    assert "🎉" not in no, "manufactured cheer is worse than no message"


def test_a_booked_call_says_it_is_not_actually_booked():
    """Nova cannot book. Saying 'booked' would be a lie he acts on."""
    msg = tv.call_outcome("Dana", "+1206", "Tuesday", "", True)
    assert "confirm" in msg.lower()
    assert "nothing's locked in" in msg.lower()


def test_a_missing_booking_link_says_how_to_fix_it():
    msg = tv.booking_link_sent("Dana", "LEWCO", "")
    assert "CAL_COM_EVENT_SLUG" in msg, "name the fix, do not just report the gap"


def test_a_failure_says_whether_it_self_heals():
    """The difference between an alarm and a report is whether he must act."""
    assert "retry" in tv.hunt_failed("timeout").lower()
    assert "another try" in tv.call_failed("LEWCO", "busy").lower()


def test_long_free_text_is_trimmed_not_dumped():
    msg = tv.new_reply("a@b.com", "S" * 400, "x" * 900, "WARM", False)
    assert len(msg) < 700, "a wall of text on a phone is unreadable"
    assert "…" in msg


def test_whitespace_in_scraped_text_is_collapsed():
    msg = tv.new_reply("a@b.com", "Re:\n\n  spaced   out", "a\n\nb", "WARM", False)
    assert "\n\n  spaced" not in msg


def test_a_reply_subject_does_not_double_up_the_re():
    """Mail clients already prefix 'Re:'; 'Re: Re:' is the tell of a template."""
    msg = tv.new_reply("a@b.com", "Re: your schedule", "sure", "WARM", False)
    assert "Re: Re:" not in msg
    assert "Re: your schedule" in msg
