"""Lane 4b — phone-first dialling (2026-07-30).

Why this lane exists: Lane 4 (`run_cold_lead_escalation`) selects via
`get_cold_leads`, which requires `status IN ('Email Sent','Contacted')`. It only
ever sees leads that were ALREADY emailed, which makes it structurally
downstream of email. Cold email is deliberately deferred and fails closed
(ADR-0014), so Lane 4's input set is permanently empty — and the ~4,280 on-ICP
WA licence leads from seam 1, which carry a published business phone at 100%
fill, could never be dialled by any scheduled lane.

These tests pin the guardrails, because the failure mode here is not a crash —
it is calling someone we should not have called, or double-spending the daily
cap.
"""
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.worker as worker

# A licence-sourced lead exactly as _source_wa_lni_licences emits it:
# owner + E.164 phone, no email, no website, status 'New'.
LICENCE_LEAD = {
    "id": 7, "business": "MAPLE RIDGE REMODELING LLC", "owner": "Dmitrii Rychagov",
    "owner_title": "Licence Principal", "owner_confidence": 90,
    "phone": "+12535550102", "phone_verified": 1, "email": "", "website": "",
    "url": "", "vertical": "", "status": "New", "score": 45, "state": "WA",
    "icebreaker": "",
}


def _run_lane(leads, *, dialer=None, gate=True, counter=0, enabled="1",
              hour=11, client_id=0, consent=True):
    """Drive run_phone_first_lane with everything external faked.

    `consent` fakes the TCPA prior-express-consent gate. It defaults True so
    these tests keep exercising the DIALLING behaviour they were written for —
    the consent gate itself is covered in tests/test_call_consent.py, and one
    test below pins that the lane actually consults it.
    """
    dialer = dialer or AsyncMock(return_value={"success": True, "call_id": "call_abc"})
    gate_mock = AsyncMock(return_value=gate)
    consent_mock = AsyncMock(return_value=(
        (True, "consent via ig_dm_reply on 2026-08-06T00:00:00Z") if consent
        else (False, "no prior express consent on record")))
    telegram = AsyncMock()
    updates = []

    async def fake_query(sql, params=(), **kw):
        updates.append((sql, params))
        return None

    fake_now = MagicMock()
    fake_now.hour = hour
    fake_now.strftime = MagicMock(return_value="11:00 AM")
    # worker does `from datetime import datetime`, so worker.datetime is the
    # CLASS — .now cannot be patched on a built-in type. Replace the whole name.
    fake_datetime = MagicMock(now=MagicMock(return_value=fake_now))

    worker.daily_call_counter = counter
    env = dict(os.environ)
    env["PHONE_FIRST_ENABLED"] = enabled

    with patch.object(worker, "trigger_retell_call", dialer), \
         patch.object(worker.DatabaseManager, "aget_uncontacted_callable_leads",
                      AsyncMock(return_value=leads)), \
         patch.object(worker.DatabaseManager, "query", AsyncMock(side_effect=fake_query)), \
         patch.object(worker, "send_telegram_report", telegram), \
         patch("app.core.approval_gate.gate_allows", gate_mock), \
         patch("app.core.call_consent.ai_call_allowed", consent_mock), \
         patch.object(worker, "datetime", fake_datetime), \
         patch.object(worker.asyncio, "sleep", AsyncMock()), \
         patch.dict(os.environ, env, clear=True):
        asyncio.run(worker.run_phone_first_lane(client_id=client_id))

    return {"dialer": dialer, "gate": gate_mock, "telegram": telegram,
            "consent": consent_mock, "updates": updates,
            "counter": worker.daily_call_counter}


class TestPhoneFirstDials:
    def test_licence_lead_gets_called(self):
        """The whole point: a never-emailed licence lead is dialable."""
        r = _run_lane([LICENCE_LEAD])
        r["dialer"].assert_awaited_once()
        phone = r["dialer"].await_args.args[0]
        assert phone == "+12535550102"

    def test_call_context_does_not_claim_a_prior_email(self):
        """Lane 4's icebreaker fallback says "we emailed about..." — for a
        first-touch call that would be a lie spoken to a real prospect."""
        r = _run_lane([LICENCE_LEAD])
        context = r["dialer"].await_args.args[1]
        assert context["call_type"] == "phone_first"
        blob = " ".join(str(v).lower() for v in context.values())
        assert "emailed" not in blob
        assert context["owner_name"] == "Dmitrii Rychagov"

    def test_success_marks_the_lead_so_it_is_not_redialled(self):
        r = _run_lane([LICENCE_LEAD])
        assert any("Cold Call Initiated" in sql for sql, _ in r["updates"])

    def test_failed_call_falls_back_to_ready_for_call(self):
        dialer = AsyncMock(return_value={"success": False, "error": "retell 500"})
        r = _run_lane([LICENCE_LEAD], dialer=dialer)
        assert any("Ready for Call" in sql for sql, _ in r["updates"])


class TestGuardrails:
    def test_approval_gate_blocks_the_call(self):
        """Calls QUEUE for Mark unless CALLS_AUTOPILOT=1. This lane must not
        widen who gets dialled without approval."""
        r = _run_lane([LICENCE_LEAD], gate=False)
        r["dialer"].assert_not_awaited()
        r["gate"].assert_awaited_once()

    def test_no_consent_blocks_the_call_before_the_approval_gate(self):
        """TCPA: an AI/artificial voice needs PRIOR EXPRESS CONSENT regardless
        of the B2B exemption (FCC 24-17). $500/call, trebled to $1,500 wilful.

        A licence-registry number is a PUBLISHED business line, not permission —
        so this lead is fully `callable` and still must not be dialled. Consent
        is checked BEFORE the approval gate, so Mark is never asked to approve
        a call that would be unlawful to place.
        """
        r = _run_lane([LICENCE_LEAD], consent=False)
        r["dialer"].assert_not_awaited()
        r["consent"].assert_awaited()
        r["gate"].assert_not_awaited()

    def test_the_lane_actually_consults_the_consent_gate(self):
        """The harness fakes the gate, so without this the gate could be
        deleted from the lane and every test here would still pass."""
        r = _run_lane([LICENCE_LEAD])
        r["consent"].assert_awaited()
        assert r["consent"].await_args.args[0] == LICENCE_LEAD["phone"]

    def test_daily_cap_is_respected(self):
        r = _run_lane([LICENCE_LEAD], counter=worker.MAX_CALLS_PER_DAY)
        r["dialer"].assert_not_awaited()

    def test_cap_is_shared_with_lane_4_not_a_second_counter(self):
        """Routing through outreach_orchestrator.make_throttled_call would use its own
        _daily_call_count and silently double MAX_CALLS_PER_DAY across lanes.
        This asserts the lane increments the SHARED worker counter."""
        r = _run_lane([LICENCE_LEAD], counter=0)
        assert r["counter"] == 1

    def test_outside_calling_hours_does_nothing(self):
        r = _run_lane([LICENCE_LEAD], hour=3)
        r["dialer"].assert_not_awaited()

    def test_kill_switch_disables_the_lane(self):
        r = _run_lane([LICENCE_LEAD], enabled="0")
        r["dialer"].assert_not_awaited()

    def test_dnc_skip_releases_the_reserved_slot(self):
        """trigger_retell_call returns skipped=True for a DNC/suppressed number.
        The reserved cap slot must be returned or the budget leaks."""
        dialer = AsyncMock(return_value={
            "success": False, "skipped": True,
            "error": "Number on DNC/suppression list — call blocked."})
        r = _run_lane([LICENCE_LEAD], dialer=dialer, counter=0)
        assert r["counter"] == 0

    def test_lead_without_a_name_is_not_called(self):
        """outreach_ready requires a decision-maker name so Retell can ask for
        the person. A bare number is not callable."""
        nameless = dict(LICENCE_LEAD, owner="", owner_confidence=0)
        r = _run_lane([nameless])
        r["dialer"].assert_not_awaited()

    def test_empty_lead_set_is_a_clean_no_op(self):
        r = _run_lane([])
        r["dialer"].assert_not_awaited()

    def test_dialer_exception_does_not_kill_the_lane(self):
        dialer = AsyncMock(side_effect=RuntimeError("retell exploded"))
        r = _run_lane([LICENCE_LEAD], dialer=dialer)   # must not raise
        assert r["counter"] == 0                        # slot released


class TestSelectionQuery:
    def test_selects_only_new_leads_with_a_phone(self):
        """The query is the fix. If it drifts back to requiring 'Email Sent'
        this lane silently stops working, exactly like Lane 4."""
        import inspect
        from app.core._lead_repo import _LeadRepo
        src = inspect.getsource(_LeadRepo.get_uncontacted_callable_leads)
        # Strip the docstring — it *describes* Lane 4's 'Email Sent' filter, so
        # matching against it would pass vacuously.
        # (rejoin the tail — the SQL is itself triple-quoted)
        parts = src.split('"""')
        code = '"""'.join(parts[2:]) if len(parts) >= 3 else src
        assert "'New'" in code
        assert "phone" in code
        assert "Email Sent" not in code     # must NOT be downstream of email
        assert "score" in code.lower()      # best leads get the call budget
