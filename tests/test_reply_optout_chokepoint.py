"""The opt-out gate must live in `reply_to_email`, not in its callers.

`send_outreach` has checked suppression, CAN-SPAM address, ICP and approval
for months. `reply_to_email` checked nothing — and it is not a lesser path:

  * `worker.py:910` uses it for the HOT-reply booking funnel, i.e. the mail
    sent at the exact moment a prospect says yes;
  * `planner.py:281` registers it as an LLM-CALLABLE TOOL, listed in both
    OUTREACH_TOOLS and TERMINAL_TOOLS.

The second one is why a convention cannot fix this. A model chooses whether to
invoke a tool, so there is no call site to add a check to — the same reasoning
`outbound_dialer` records for the Retell dialler.

Damages framing is the same as the phone gate: the cost of a skipped reply is
one Telegram nudge; the cost of mailing someone who opted out is a breach.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import dnc
from app.skills import agentmail_skill


# ── the normaliser ──────────────────────────────────────────────────────────
# `_normalize` (phones) was rewritten on 2026-08-03 because one number produced
# several non-matching keys. `_normalize_email` kept the identical defect.

@pytest.mark.parametrize("written", [
    "dave@example.com",
    "Dave <dave@example.com>",
    "  DAVE@EXAMPLE.COM  ",
    '"Reed, Dave" <dave@example.com>',
    "<dave@example.com>",
])
def test_every_real_world_address_form_canonicalises_to_one_key(written):
    assert dnc._normalize_email(written) == "dave@example.com"


def test_display_name_form_is_the_one_an_inbox_actually_hands_you():
    """The regression that mattered: check_replies stores the raw `from_`."""
    assert dnc._normalize_email("Dave <dave@example.com>") == "dave@example.com"


def test_normaliser_never_invents_an_address():
    for junk in ("", "   ", "not-an-address"):
        assert "@" not in dnc._normalize_email(junk)


# ── the gate ────────────────────────────────────────────────────────────────
# Since the 2026-09 $0 repair the reply gate is the fuller one in
# reply_to_email (it also checks reply_to targets, refuses replies to our own
# sent mail and inbound opt-out text). These tests pin the opt-out contract
# against it: a refusal never reaches `messages.reply`, whatever status word
# the gate uses ("blocked" or "error").

_REFUSED = ("blocked", "error")


def _inbound(sender: str):
    return MagicMock(from_=sender, reply_to=None, to=["inbox_1"],
                     subject="Re: hello", extracted_text="Sounds good", text="")


def _client_returning(sender: str):
    client = MagicMock()
    client.inboxes.messages.get.return_value = _inbound(sender)
    client.inboxes.messages.reply.return_value = MagicMock()
    return client


def _run(sender, suppressed):
    client = _client_returning(sender)
    with patch.object(agentmail_skill, "_get_client", lambda: (client, None)), \
         patch.object(agentmail_skill, "_get_nova_inbox", lambda: "inbox_1"), \
         patch("app.core.dnc.is_email_suppressed",
               AsyncMock(return_value=suppressed)):
        res = asyncio.run(agentmail_skill.reply_to_email(
            "msg_1", "hello", _approval_checked=True))
    return res, client


def test_reply_is_blocked_when_the_recipient_opted_out():
    res, client = _run("Dave <dave@example.com>", suppressed=True)
    assert res["status"] in _REFUSED
    client.inboxes.messages.reply.assert_not_called()


def test_reply_is_sent_when_the_recipient_has_not_opted_out():
    res, client = _run("Dave <dave@example.com>", suppressed=False)
    assert res["status"] == "success", res
    client.inboxes.messages.reply.assert_called_once()


def test_the_gate_receives_the_bare_address_not_the_raw_header():
    """A gate handed 'Dave <dave@…>' would look up a key that never matches."""
    seen = []

    async def _spy(email):
        seen.append(email)
        return dnc._normalize_email(email) in {"dave@example.com"}

    client = _client_returning("Dave <dave@example.com>")
    with patch.object(agentmail_skill, "_get_client", lambda: (client, None)), \
         patch.object(agentmail_skill, "_get_nova_inbox", lambda: "inbox_1"), \
         patch("app.core.dnc.is_email_suppressed", _spy):
        res = asyncio.run(agentmail_skill.reply_to_email(
            "msg_1", "hello", _approval_checked=True))

    assert seen and all(dnc._normalize_email(a) == "dave@example.com" for a in seen)
    assert res["status"] in _REFUSED, "a suppressed address must not be mailed"
    client.inboxes.messages.reply.assert_not_called()


def test_unresolvable_recipient_fails_closed():
    """The inbox API failing must refuse the reply, never send it blind."""
    client = MagicMock()
    client.inboxes.messages.get.side_effect = RuntimeError("inbox API down")
    with patch.object(agentmail_skill, "_get_client", lambda: (client, None)), \
         patch.object(agentmail_skill, "_get_nova_inbox", lambda: "inbox_1"):
        res = asyncio.run(agentmail_skill.reply_to_email(
            "msg_1", "hello", _approval_checked=True))
    assert res["status"] in _REFUSED
    client.inboxes.messages.reply.assert_not_called()


def test_the_llm_invokable_path_is_the_reason_this_gate_is_here():
    """planner registers reply_to_email as a tool — no call site to guard."""
    from app.core import planner
    src = __import__("pathlib").Path(planner.__file__).read_text(encoding="utf-8")
    assert '"reply_to_email"' in src
    assert "reply_to_email" in src.split("OUTREACH_TOOLS")[1][:400]
