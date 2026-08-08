"""Every cold send must pass the approval gate — at the chokepoint, not the lane.

## What was actually true before this

"Nova never sends cold email without Mark's approval" was true of the FIRST
email only. Five paths reach `send_outreach`; exactly one gated:

    worker.py:515                 day-0 cold email                    GATED
    worker.py:952                 cold-escalation re-engagement       ungated
    email_sequence_skill.py:359   drip touches 2, 3 and 4             ungated
    outreach_orchestrator.py:502                                      ungated
    planner.py:245                exposed to the LLM as a TOOL        ungated

`email_sequence_skill.py` contains no reference to `gate_allows`,
`approval_gate` or `AUTOPILOT` anywhere — so three of every four touches in a
drip were unsupervised by construction. And the drip enrolled leads whose day-0
email Mark had explicitly NOT approved (observed live 2026-08-07: an "awaiting
approval" log line immediately followed by an enrolment for the same lead).

Only `BUSINESS_POSTAL_ADDRESS` being unset stopped it. The moment that is set to
enable *approved* email, the unapproved follow-ups start going out.

This is the same shape as the §227(b) hole in `outbound_dialer.py`: a gate
applied per-call-site while other paths reach the same sink, including one
exposed to an LLM where there is no call site to edit. Hence the same fix — the
gate moves to where every path converges.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.skills import agentmail_skill

ADDR = "OROVA, 1 Example St, Manila, PH"


def _call(**kw):
    """Invoke send_outreach with every OTHER gate forced open.

    Each gate is neutralised explicitly so a pass can only mean the approval
    gate behaved — never that some unrelated check happened to block first.
    """
    gate = kw.pop("gate", AsyncMock(return_value=True))
    with patch.dict("os.environ", {"BUSINESS_POSTAL_ADDRESS": ADDR}), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=False)), \
         patch("app.core.database.DatabaseManager.query", AsyncMock(return_value=None)), \
         patch.object(agentmail_skill, "_verify_email_deliverable",
                      AsyncMock(return_value={"valid": True, "reason": "OK"})), \
         patch.object(agentmail_skill, "_send_via_agentmail",
                      AsyncMock(return_value={"status": "success"})) as sender, \
         patch("app.core.approval_gate.gate_allows", gate):
        res = asyncio.run(agentmail_skill.send_outreach(
            to=kw.pop("to", "owner@sierraridgebuilders.com"),
            subject=kw.pop("subject", "Quick question"),
            body=kw.pop("body", "Hello there."),
            lead_id=kw.pop("lead_id", 7),
            **kw))
    return res, sender, gate


def test_an_ungated_caller_is_now_gated():
    """The drip / orchestrator / LLM-tool path. Nothing passes _approval_checked."""
    res, sender, gate = _call(gate=AsyncMock(return_value=False))
    assert res["skipped"] is True
    assert "approval" in res["error"].lower()
    sender.assert_not_awaited(), "an unapproved email reached the mail API"
    gate.assert_awaited()


def test_an_approved_send_goes_out():
    res, sender, _ = _call(gate=AsyncMock(return_value=True))
    assert res["status"] == "success"
    sender.assert_awaited()


def test_the_pre_gated_caller_is_not_gated_twice():
    """worker.py:515 already called gate_allows.

    Approvals are SINGLE-USE. Gating again here would consume a second one that
    was never granted, so the email Mark just approved would never send — the
    fix would silently break the one path that already worked.
    """
    res, sender, gate = _call(_approval_checked=True, gate=AsyncMock(return_value=False))
    assert res["status"] == "success", "a pre-approved send was blocked by a second gate"
    sender.assert_awaited()
    gate.assert_not_awaited(), "the approval was consumed twice"


def test_a_failing_gate_blocks_the_send():
    """A gate that opens when it errors is not a gate."""
    res, sender, _ = _call(gate=AsyncMock(side_effect=RuntimeError("approval store down")))
    assert res["skipped"] is True
    assert "fail-closed" in res["error"].lower()
    sender.assert_not_awaited()


def test_the_gate_is_not_reached_when_can_spam_blocks():
    """Ordering. Never page a human to approve a send another gate rejects.

    Asking Mark to approve sends that were going to be blocked anyway trains him
    to approve without reading, which turns the gate into a rubber stamp.
    """
    gate = AsyncMock(return_value=True)
    with patch.dict("os.environ", {"BUSINESS_POSTAL_ADDRESS": ""}), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=False)), \
         patch("app.core.approval_gate.gate_allows", gate), \
         patch.object(agentmail_skill, "_send_via_agentmail",
                      AsyncMock(return_value={"status": "success"})):
        res = asyncio.run(agentmail_skill.send_outreach(
            to="owner@example.com", subject="s", body="b", lead_id=1))
    assert res["skipped"] is True
    assert "CAN-SPAM" in res["error"]
    gate.assert_not_awaited(), "Mark was asked to approve a send CAN-SPAM already blocked"


def test_the_gate_is_not_reached_when_the_recipient_opted_out():
    gate = AsyncMock(return_value=True)
    with patch.dict("os.environ", {"BUSINESS_POSTAL_ADDRESS": ADDR}), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=True)), \
         patch("app.core.approval_gate.gate_allows", gate), \
         patch.object(agentmail_skill, "_send_via_agentmail",
                      AsyncMock(return_value={"status": "success"})):
        res = asyncio.run(agentmail_skill.send_outreach(
            to="optedout@example.com", subject="s", body="b", lead_id=1))
    assert res["skipped"] is True
    gate.assert_not_awaited(), "Mark was asked to approve a send to someone who opted out"


def test_the_llm_tool_schema_cannot_set_the_bypass():
    """`_approval_checked` must stay invisible to the model.

    planner.py exposes send_outreach as a callable tool. If the bypass were in
    the tool schema, the model could set it and gate itself out — which is
    precisely the failure this whole change exists to close.
    """
    from app.skills import definitions
    tools = [t for t in definitions.TOOLS
             if t.get("function", {}).get("name") == "send_outreach"]
    assert tools, "send_outreach is no longer a registered tool — update this test"
    props = tools[0]["function"]["parameters"]["properties"]
    assert "_approval_checked" not in props
    assert set(props) <= {"to", "subject", "body"}
