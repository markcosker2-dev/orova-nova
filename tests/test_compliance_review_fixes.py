"""Three holes the compliance review found that the engineering missed.

All three were live in the repo and none was caught by 1169 passing tests,
because each sits in the gap between what a test asserts and what actually
executes:

1. `_approval_checked` was "unreachable by the LLM" only in the DECLARED tool
   schema. `planner._call_tool` dispatches raw model output with `fn(**args)`
   and no allowlist, `semantic_firewall` has no entry for `send_outreach`, and
   `ai_client._extract_tool_calls_from_text` regex-parses tool calls out of free
   text with no validation at all. The original test asserted the schema omitted
   the key — it encoded the assumption instead of verifying the behaviour.

2. `outreach_orchestrator` called `send_outreach(...)` WITHOUT `await`, so every
   gate in it — opt-out, CAN-SPAM, ICP, MX, approval — never ran, while the
   caller reported success. Unreachable today, which is why an incident-driven
   audit missed it; it reads as a finished pipeline.

3. `email_proofreader` was handed the real retainer figures in its prompt AND
   authorised to rewrite the body. An LLM holding the numbers and told to
   improve the copy is the likeliest source of a quote, not a control against
   one — while the owner mandate is that Nova states no price at all.
"""
import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.core.planner import _strip_internal_kwargs
from app.skills import agentmail_skill
from app.skills.agentmail_skill import _contains_price


# ── 1. a model cannot smuggle an internal kwarg through tool dispatch ───────

def test_model_supplied_internal_kwargs_are_stripped():
    out = _strip_internal_kwargs(
        {"to": "a@b.com", "subject": "s", "body": "b", "_approval_checked": True})
    assert "_approval_checked" not in out
    assert out == {"to": "a@b.com", "subject": "s", "body": "b"}


def test_stripping_protects_tools_nobody_audited():
    """The whole underscore class goes, not one hand-listed parameter."""
    out = _strip_internal_kwargs({"x": 1, "_internal": True, "_skip_gate": True, "__dunder": 1})
    assert out == {"x": 1}


def test_ordinary_args_are_untouched():
    args = {"phone": "+12065551234", "context": {"owner_name": "Dana"}}
    assert _strip_internal_kwargs(args) == args


def test_non_dict_args_do_not_explode():
    assert _strip_internal_kwargs(None) is None


@pytest.mark.asyncio
async def test_call_tool_actually_drops_it_at_dispatch():
    """The property that matters: what reaches the function, not what the schema says."""
    from app.core.planner import _call_tool
    seen = {}

    async def fake_send(to, subject, body, **kw):
        seen.update(kw)
        return {"status": "success"}

    await _call_tool(fake_send, {"to": "a@b.com", "subject": "s", "body": "b",
                                 "_approval_checked": True})
    assert "_approval_checked" not in seen, "a model bypassed the approval gate"


# ── 2. the missing await ────────────────────────────────────────────────────

def test_orchestrator_awaits_send_outreach():
    """Without `await`, every gate inside send_outreach is skipped silently."""
    src = inspect.getsource(agentmail_skill).__class__  # placeholder to keep import used
    from app.skills import outreach_orchestrator
    body = inspect.getsource(outreach_orchestrator.send_throttled_email)
    assert "await send_outreach(" in body, (
        "send_outreach is called without await — it returns a coroutine that "
        "never executes, so opt-out/CAN-SPAM/ICP/MX/approval all silently no-op "
        "while the caller reports success"
    )


# ── 3. no price may leave the mailer ────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "We charge $4,000/mo",
    "Our retainer is 4k/mo",
    "Pricing starts at 5000",
    "a free two weeks to prove it",
    "you don't pay anything",
    "30-day money-back guarantee",
    "It's 4500 USD per month",
    "no cost to you",
])
def test_price_language_is_caught(text):
    assert _contains_price("", text), f"price language leaked: {text!r}"


@pytest.mark.parametrize("text", [
    "This frees up your Saturdays",
    "Happy to walk you through how it works",
    "You'd stop driving out to tire-kickers",
    "Mark can give you a straight answer on the call",
    "Worth ten minutes of your time?",
    "We build custom homes across the region",
])
def test_ordinary_sales_prose_is_not_flagged(text):
    """A filter that cries wolf gets disabled, and a disabled filter protects nothing."""
    assert not _contains_price("", text), f"false positive on: {text!r}"


def test_the_subject_line_is_checked_too():
    assert _contains_price("Save $500 this month", "clean body")


def test_the_proofreader_prompt_no_longer_carries_prices():
    """An LLM holding the real numbers and told to improve copy is not a control."""
    from app.skills import email_proofreader
    src = inspect.getsource(email_proofreader)
    assert "$4K-$5K" not in src
    assert "price_monthly_usd" not in src
    assert "NEVER state or imply a price" in src
