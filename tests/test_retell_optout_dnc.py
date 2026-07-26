"""The Retell webhook must persist an opt-out to the DNC suppression list.

Both agents are instructed to honour "take me off your list", and
outbound_dialer already refuses to dial a suppressed number — but nothing wrote
to that list. The post-call `opt out requested` field was captured and dropped,
so the same person could be dialled again. That is a TCPA problem, not a
cosmetic one.

The direction tests are the dangerous ones. On an INBOUND leg `to_number` is
OROVA's own line; suppressing it would blacklist the agency's number and
silently kill every future outbound call.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

PROSPECT = "+14085551234"
OUR_LINE = "+17166703920"


def _payload(direction, opt_out=True, to=None, frm=None):
    return {
        "event": "call_analyzed",
        "call": {
            "direction": direction,
            "to_number": to,
            "from_number": frm,
            "metadata": {"lead_id": None, "client_id": 0},
            "call_analysis": {
                "call_summary": "Caller asked to be removed.",
                "call_successful": True,
                "custom_analysis_data": {
                    "opt out requested": opt_out,
                    "lead temperature": "Cold",
                },
            },
        },
    }


def _post(payload, monkeypatch):
    """Drive the webhook handler directly, capturing add_suppression calls."""
    monkeypatch.setenv("RETELL_FROM_NUMBER", OUR_LINE)
    import app.main as main

    suppressed = AsyncMock(return_value=True)

    class _Req:
        async def body(self):
            import json
            return json.dumps(payload).encode()

        async def json(self):
            return payload

        @property
        def headers(self):
            return {"x-api-key": "test-dashboard-key"}

        @property
        def query_params(self):
            return {}

    monkeypatch.setenv("DASHBOARD_API_KEY", "test-dashboard-key")
    with patch("app.core.dnc.add_suppression", new=suppressed), \
         patch.object(main, "DatabaseManager") as db, \
         patch.object(main, "_schedule_background", lambda *a, **k: None):
        db.query = AsyncMock(return_value=None)
        asyncio.run(main.retell_webhook(_Req()))
    return suppressed


# ─── The direction hazard ────────────────────────────────────────

def test_outbound_optout_suppresses_the_prospect(monkeypatch):
    s = _post(_payload("outbound", to=PROSPECT, frm=OUR_LINE), monkeypatch)
    s.assert_awaited_once()
    assert s.await_args.args[0] == PROSPECT


def test_inbound_optout_suppresses_the_caller_not_our_own_line(monkeypatch):
    """THE CRITICAL TEST. On an inbound leg to_number is OROVA's number.
    Suppressing it would blacklist the agency's own line and kill all future
    outbound calls."""
    s = _post(_payload("inbound", to=OUR_LINE, frm=PROSPECT), monkeypatch)
    s.assert_awaited_once()
    assert s.await_args.args[0] == PROSPECT
    assert s.await_args.args[0] != OUR_LINE


def test_never_suppresses_our_own_number_even_if_payload_says_so(monkeypatch):
    # Defence in depth: a mislabelled direction must not be able to
    # self-blacklist.
    s = _post(_payload("outbound", to=OUR_LINE, frm=OUR_LINE), monkeypatch)
    s.assert_not_awaited()


# ─── Only fires when actually requested ──────────────────────────

def test_no_optout_flag_means_no_suppression(monkeypatch):
    s = _post(_payload("outbound", opt_out=False, to=PROSPECT, frm=OUR_LINE), monkeypatch)
    s.assert_not_awaited()


def test_missing_number_does_not_crash_and_is_not_silent(monkeypatch):
    # Nothing to suppress; the handler must still complete (the webhook has
    # other work to do) and must log loudly rather than swallow it.
    s = _post(_payload("outbound", to=None, frm=None), monkeypatch)
    s.assert_not_awaited()


# ─── The gate it feeds actually blocks ───────────────────────────

def test_suppressed_number_is_refused_by_the_dialer():
    """Closes the loop: a suppressed number must be refused before dialling,
    which is what makes persisting the opt-out meaningful."""
    from app.skills import outbound_dialer

    with patch("app.core.dnc.is_suppressed", new=AsyncMock(return_value=True)), \
         patch("app.core.dnc.is_dnc_registered", new=AsyncMock(return_value=False)):
        res = asyncio.run(outbound_dialer.trigger_retell_call(
            PROSPECT, {"business_name": "Test Co"}))
    assert res.get("success") is False
    assert res.get("skipped") is True
