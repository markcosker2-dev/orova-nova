"""Email opt-outs must be HONOURED, not merely detected (audit B2, 2026-07-26).

The reply classifier already resolved opt-out language to COLD, which stops an
auto-reply on that message. It did not stop the next drip cycle: nothing
persisted the address and send_outreach had no pre-send check, so someone who
asked to be left alone could be emailed again. CAN-SPAM requires honouring an
opt-out (15 U.S.C. §7704), and the footer this system ships explicitly promises
it — "Reply 'no thanks' and I won't write again."

This is the same defect already fixed for the phone channel; both halves are
needed: record it, then check it before sending.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core import dnc
from app.skills.agentmail_skill import is_optout_reply

TARGET = "owner@sierraridgebuilders.com"


# ─── Detection reads ONE keyword list ────────────────────────────

@pytest.mark.parametrize("text", [
    "unsubscribe me", "not interested", "no thanks", "remove me from your list",
    "stop emailing me", "take me off", "opt out", "do not contact", "please stop",
])
def test_optout_language_is_detected(text):
    assert is_optout_reply("", text) is True


@pytest.mark.parametrize("text", [
    "sounds interesting, what's the pricing?",
    "can you send me more info",
    "yes let's set up a call",
])
def test_ordinary_replies_are_not_optouts(text):
    assert is_optout_reply("", text) is False


def test_detection_uses_the_existing_signal_list_not_a_copy():
    from app.skills import agentmail_skill
    import inspect
    src = inspect.getsource(agentmail_skill.is_optout_reply)
    assert "_OPTOUT_REPLY_SIGNALS" in src, "must read the shared list, not a second copy"


# ─── Recording ───────────────────────────────────────────────────

def _state_backed():
    """A DatabaseManager stub with a real in-memory state store."""
    store = {}

    async def get_state(key, default=None):
        return store.get(key, default)

    async def set_state(key, value):
        store[key] = value

    db = AsyncMock()
    db.get_state = AsyncMock(side_effect=get_state)
    db.set_state = AsyncMock(side_effect=set_state)
    return db, store


def test_recording_then_checking_round_trips():
    db, store = _state_backed()
    with patch.object(dnc, "DatabaseManager", db):
        assert asyncio.run(dnc.is_email_suppressed(TARGET)) is False
        assert asyncio.run(dnc.add_email_suppression(TARGET, reason="reply opt-out")) is True
        assert asyncio.run(dnc.is_email_suppressed(TARGET)) is True


def test_recording_is_idempotent():
    db, store = _state_backed()
    with patch.object(dnc, "DatabaseManager", db):
        for _ in range(3):
            asyncio.run(dnc.add_email_suppression(TARGET))
        assert store["email_suppression_list"].count(TARGET) == 1


def test_case_and_whitespace_cannot_slip_past():
    db, _ = _state_backed()
    with patch.object(dnc, "DatabaseManager", db):
        asyncio.run(dnc.add_email_suppression("  Owner@SierraRidgeBuilders.COM  "))
        assert asyncio.run(dnc.is_email_suppressed(TARGET)) is True


def test_garbage_address_is_not_recorded():
    db, store = _state_backed()
    with patch.object(dnc, "DatabaseManager", db):
        assert asyncio.run(dnc.add_email_suppression("not-an-email")) is False
        assert store.get("email_suppression_list") is None


# ─── Fail-closed ─────────────────────────────────────────────────

def test_lookup_failure_blocks_the_send():
    """Skipping one send costs nothing; mailing someone who opted out is a
    compliance breach. The error path must resolve to suppressed."""
    db = AsyncMock()
    db.get_state = AsyncMock(side_effect=RuntimeError("db down"))
    with patch.object(dnc, "DatabaseManager", db):
        assert asyncio.run(dnc.is_email_suppressed(TARGET)) is True


def test_empty_address_is_suppressed():
    assert asyncio.run(dnc.is_email_suppressed("")) is True


# ─── The pre-send gate actually blocks ───────────────────────────

def test_send_outreach_refuses_a_suppressed_recipient():
    """Closing the loop — recording an opt-out is only meaningful if the send
    path consults it."""
    from app.skills import agentmail_skill

    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=True)):
        res = asyncio.run(agentmail_skill.send_outreach(
            to=TARGET, subject="Hi", body="Body", skip_proofread=True))
    assert res.get("status") == "error"
    assert res.get("skipped") is True
    assert "opted out" in (res.get("error") or "").lower()


def test_send_outreach_proceeds_past_the_gate_when_not_suppressed(monkeypatch):
    """Guards against the gate blocking everyone — it must only stop opt-outs.

    BUSINESS_POSTAL_ADDRESS is set here to isolate THIS gate: a later CAN-SPAM
    gate also blocks sends when it is unset, and without this the test would
    pass for the wrong reason.
    """
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "OROVA, 1 Example St, Manila, PH")
    from app.skills import agentmail_skill

    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=False)):
        res = asyncio.run(agentmail_skill.send_outreach(
            to=TARGET, subject="Hi", body="Body", skip_proofread=True))
    assert "opted out" not in (res.get("error") or "").lower()
