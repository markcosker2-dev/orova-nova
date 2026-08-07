"""The §227(b) consent gate must live in the DIALER, not in one lane.

## Why this file exists

`app/core/call_consent.py` shipped with 18 tests and a careful legal docstring,
and was wired into exactly ONE caller — `run_phone_first_lane` (worker.py:1204).
Four other paths reach `trigger_retell_call` without it:

  * `_execute_approved_call`      (worker.py, Lane 1 — fires on Mark's own
                                   "Approved" click in the Sheet)
  * `run_cold_lead_escalation`    (worker.py, Lane 4)
  * `outreach_orchestrator.execute_call`
  * `app/core/planner.py`         — registers `trigger_retell_call` as an
                                    LLM-callable TOOL

The last one is the reason a per-call-site convention can never be sufficient:
an LLM chooses whether to invoke a tool, so there is no call site to add a
check to. The gate has to be somewhere the model cannot route around.

The existing suite could not catch this. Every consent test called
`ai_call_allowed` directly, and `test_phone_first_lane` tested the one lane that
already had it. A test that only exercises the correct integration cannot fail
when a different integration is missing — which is precisely how the hole stayed
open through 18 passing tests.

So these tests assert the property that actually matters: **no path reaches the
Retell API without passing the consent gate**, because the gate sits at the
chokepoint every path converges on.

Damages if this regresses: $500/call, trebled to $1,500 if wilful (47 U.S.C.
§227). The gate fails CLOSED for that reason.
"""
import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.core import call_consent as cc
from app.core.database import DatabaseManager
from app.skills import outbound_dialer


@pytest.fixture
def dialable(monkeypatch):
    """Retell env present + DNC explicitly CLEAN.

    Both DNC gates are forced open so the ONLY thing that can block a call in
    these tests is the §227(b) consent gate. Otherwise a passing test could be
    passing for the wrong reason — DNC fail-closed on an uninitialised DB looks
    identical to a working consent gate from the outside.
    """
    monkeypatch.setenv("RETELL_API_KEY", "dummy-not-real")
    monkeypatch.setenv("RETELL_FROM_NUMBER", "+17166703920")
    monkeypatch.setenv("RETELL_AGENT_ID", "agent_dummy")

    store = {}

    async def _get(key, default=None):
        return store.get(key, default)

    async def _set(key, value):
        store[key] = value
        return True

    with patch.object(DatabaseManager, "get_state", _get), \
         patch.object(DatabaseManager, "set_state", _set), \
         patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)), \
         patch("app.core.dnc.is_dnc_registered", AsyncMock(return_value=False)):
        yield store


def _blocked_by_consent(res) -> bool:
    return bool(res.get("skipped")) and "consent gate" in str(res.get("error", ""))


@pytest.mark.parametrize("phone,why", [
    ("+12065551234", "geographic number — portability makes landline-vs-cell undeterminable"),
    ("+18005551234", "toll-free 800 — called party is charged, (A)(iii) applies"),
    ("+18445551234", "toll-free 844"),
    ("+18885551234", "toll-free 888"),
])
def test_dialer_blocks_without_consent(dialable, phone, why):
    """No consent + not a verified landline -> the DIALER itself refuses."""
    res = asyncio.run(outbound_dialer.trigger_retell_call(phone, {"owner_name": "Test"}))
    assert res["success"] is False, why
    assert _blocked_by_consent(res), f"expected the consent gate to block: {res}"


def test_dialer_allows_a_verified_business_landline(dialable):
    """A verified landline is outside BOTH artificial-voice provisions.

    This is the case the whole gate exists to permit — if it blocked here it
    would be a wall, not a gate, and the phone channel would be dead.
    """
    async def _run():
        await cc.record_line_type("+15035551234", "landline", source="carrier_lookup")
        allowed, why = await cc.ai_call_allowed("+15035551234")
        assert allowed is True, why
        res = await outbound_dialer.trigger_retell_call("+15035551234", {"owner_name": "Test"})
        # It must get PAST the gate. It then fails on the dummy API key, which
        # is proof it reached the Retell request and was not gate-blocked.
        assert not _blocked_by_consent(res), f"landline was wrongly gate-blocked: {res}"

    asyncio.run(_run())


def test_dialer_allows_recorded_consent(dialable):
    """Recorded consent from a VALID source opens the gate on an unknown line."""
    async def _run():
        ok = await cc.record_call_consent(
            "+12065551234", source="ig_dm_reply", detail="agreed to a call on IG")
        assert ok is True
        res = await outbound_dialer.trigger_retell_call("+12065551234", {"owner_name": "Test"})
        assert not _blocked_by_consent(res), f"consented number was gate-blocked: {res}"

    asyncio.run(_run())


def test_consent_from_an_unrecognised_source_does_not_open_the_gate(dialable):
    """Consent we cannot attribute to a known channel is not consent.

    Undocumented consent is worthless in exactly the dispute where it matters,
    so an unknown source must be refused rather than silently trusted.
    """
    async def _run():
        ok = await cc.record_call_consent(
            "+12065551234", source="someone_said_so", detail="trust me")
        assert ok is False
        res = await outbound_dialer.trigger_retell_call("+12065551234", {"owner_name": "Test"})
        assert _blocked_by_consent(res), f"bogus consent source opened the gate: {res}"

    asyncio.run(_run())


def test_gate_fails_closed_when_it_errors(dialable):
    """A gate that opens when it throws is not a gate."""
    async def _run():
        with patch("app.core.call_consent.ai_call_allowed",
                   AsyncMock(side_effect=RuntimeError("boom"))):
            res = await outbound_dialer.trigger_retell_call("+15035551234", {"owner_name": "Test"})
        assert res["success"] is False
        assert res.get("skipped") is True
        assert "fail-closed" in str(res.get("error", "")).lower(), res

    asyncio.run(_run())


def test_every_dialer_caller_is_covered_by_the_chokepoint():
    """Regression pin: the gate must be in the dialer, not only in a lane.

    If someone later "refactors" the check back out of `outbound_dialer` and
    into individual lanes, this fails — which is the whole point, because the
    LLM tool path in planner.py has no call site to put a check into.
    """
    src = (outbound_dialer.__file__)
    with open(src, "r", encoding="utf-8") as fh:
        body = fh.read()
    assert "ai_call_allowed" in body, (
        "The §227(b) consent gate is no longer in outbound_dialer.py. Per-call-site "
        "gating cannot cover planner.py's LLM tool exposure — put it back."
    )
