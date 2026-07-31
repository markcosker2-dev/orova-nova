"""Health-alert Telegram debounce (2026-07-30).

Owner report: "the telegram part keeps spamming the same thing again and again."

Cause: `pipeline_health_check` runs every 2 hours (Lane 7) and its alert
conditions are STRUCTURAL — "lead inventory is low (<10 leads)", "no outreach
emails sent in the last 24 hours". Those stay true for days, so the lane sent a
byte-identical Telegram message 12x a day indefinitely, and re-proposed the same
corrective tasks on every pass.

Production state that triggered it: leads_found = 1 (< 10, -30) and
yesterday_sends = 0 (-20) => score 50 < 70 => alert, every single run, forever.

The second alert was doubly wrong: cold email is deliberately deferred and
fails closed without BUSINESS_POSTAL_ADDRESS, so it warned that the intended
configuration was in effect — an alert no action could ever clear.
"""
import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.core.ceo_brain import CEOBrain

# Unhealthy on grounds UNRELATED to the email deferral, so these tests exercise
# the debounce itself rather than the suppression fix:
#   leads_found 1 (<10)                    -> -30
#   emails_sent 48 with 0 replies (>20, 0) -> -15   == 55, under the 70 gate
# (48/0 is the real post-incident production state.)
SPAMMY_METRICS = {"leads_found": 1, "emails_sent": 48, "replies_received": 0}

# The exact live metrics on 2026-07-30, after the Drive-restore failure left one
# row in the DB.
LIVE_PROD_METRICS = {"leads_found": 1, "emails_sent": 1, "replies_received": 0}


def _run(metrics=None, state=None, postal="", telegram=None, propose=None):
    """Run pipeline_health_check with the state_store faked in memory.

    Returns (health, telegram_mock, writes) where `writes` maps state key ->
    last value written. Keyed by name rather than read off `await_args` so the
    assertions can't be broken by call ordering or by any other writer.
    """
    import os

    store = dict(state or {})
    telegram = telegram or AsyncMock()
    writes = {}

    async def fake_get_state(key, default=None):
        return store.get(key, default)

    async def fake_set_state(key, value):
        writes[key] = value

    env = dict(os.environ)
    if postal:
        env["BUSINESS_POSTAL_ADDRESS"] = postal
    else:
        env.pop("BUSINESS_POSTAL_ADDRESS", None)

    with patch("app.core.ceo_brain.DatabaseManager.aget_metrics",
               AsyncMock(return_value=metrics or SPAMMY_METRICS)), \
         patch("app.core.ceo_brain.DatabaseManager.fetchone",
               AsyncMock(return_value={"cnt": 0})), \
         patch("app.core.ceo_brain.DatabaseManager.get_state",
               AsyncMock(side_effect=fake_get_state)), \
         patch("app.core.ceo_brain.DatabaseManager.set_state",
               AsyncMock(side_effect=fake_set_state)), \
         patch("app.core.ceo_brain._send_telegram_alert", telegram), \
         patch.object(CEOBrain, "propose_tasks",
                      propose or AsyncMock(return_value=[])), \
         patch.object(CEOBrain, "_schedule_auto_execute", AsyncMock()), \
         patch.dict("os.environ", env, clear=True):
        health = asyncio.run(CEOBrain().pipeline_health_check())
    return health, telegram, writes


class TestHealthAlertDebounce:
    def test_first_unhealthy_run_alerts(self):
        health, telegram, writes = _run()
        assert health["health_score"] < 70
        telegram.assert_awaited_once()
        assert CEOBrain.HEALTH_ALERT_STATE_KEY in writes   # persisted for next run

    def test_identical_alert_set_is_suppressed(self):
        """THE BUG. Second run, same conditions, inside cooldown -> silence."""
        _, _, writes = _run()
        persisted = writes[CEOBrain.HEALTH_ALERT_STATE_KEY]
        assert "fingerprint" in persisted and "sent_at" in persisted

        _, telegram2, _ = _run(
            state={CEOBrain.HEALTH_ALERT_STATE_KEY: persisted})
        telegram2.assert_not_awaited()

    def test_changed_alert_set_pages_immediately(self):
        """A NEW problem must never be swallowed by the cooldown."""
        stale = {"fingerprint": "0000deadbeef0000", "sent_at": time.time()}
        _, telegram, _ = _run(state={CEOBrain.HEALTH_ALERT_STATE_KEY: stale})
        telegram.assert_awaited_once()

    def test_cooldown_expiry_repages(self):
        """A persisting problem is re-surfaced once a day, not forgotten."""
        _, _, writes = _run()
        persisted = dict(writes[CEOBrain.HEALTH_ALERT_STATE_KEY])
        persisted["sent_at"] = time.time() - (CEOBrain.HEALTH_ALERT_COOLDOWN_S + 60)
        _, telegram2, _ = _run(
            state={CEOBrain.HEALTH_ALERT_STATE_KEY: persisted})
        telegram2.assert_awaited_once()

    def test_corrective_tasks_ride_the_same_gate(self):
        """Duplicate suppression must cover auto-scheduled work too, or the
        queue fills with 12 copies a day of the same corrective batch."""
        propose = AsyncMock(return_value=[{"goal": "hunt more leads"}])
        _, _, writes = _run(propose=propose)
        assert propose.await_count == 1

        persisted = writes[CEOBrain.HEALTH_ALERT_STATE_KEY]
        propose2 = AsyncMock(return_value=[{"goal": "hunt more leads"}])
        _run(state={CEOBrain.HEALTH_ALERT_STATE_KEY: persisted}, propose=propose2)
        propose2.assert_not_awaited()

    def test_debounce_fails_open_on_state_error(self):
        """A state_store failure must send the alert, never swallow it."""
        telegram = AsyncMock()
        with patch("app.core.ceo_brain.DatabaseManager.aget_metrics",
                   AsyncMock(return_value=SPAMMY_METRICS)), \
             patch("app.core.ceo_brain.DatabaseManager.fetchone",
                   AsyncMock(return_value={"cnt": 0})), \
             patch("app.core.ceo_brain.DatabaseManager.get_state",
                   AsyncMock(side_effect=RuntimeError("state_store is down"))), \
             patch("app.core.ceo_brain.DatabaseManager.set_state", AsyncMock()), \
             patch("app.core.ceo_brain._send_telegram_alert", telegram), \
             patch.object(CEOBrain, "propose_tasks", AsyncMock(return_value=[])), \
             patch.object(CEOBrain, "_schedule_auto_execute", AsyncMock()):
            health = asyncio.run(CEOBrain().pipeline_health_check())
        assert "health_score" in health
        telegram.assert_awaited_once()

    def test_malformed_persisted_state_does_not_crash(self):
        """A non-dict under the key (older format, manual edit) must not throw."""
        _, telegram, _ = _run(state={CEOBrain.HEALTH_ALERT_STATE_KEY: "garbage"})
        telegram.assert_awaited_once()


class TestNoEmailAlertRespectsDeferral:
    def test_no_email_alert_suppressed_when_sending_is_impossible(self):
        """Cold email fails closed without BUSINESS_POSTAL_ADDRESS (CAN-SPAM
        §7704), so "no emails sent" is the intended state, not a fault."""
        health, _, _ = _run(postal="")
        assert not any("No outreach emails" in a for a in health["alerts"])

    def test_no_email_alert_fires_once_sending_is_configured(self):
        """When sending IS possible, zero sends in 24h is a real problem."""
        health, _, _ = _run(postal="123 Main St, Springfield, IL 62701")
        assert any("No outreach emails" in a for a in health["alerts"])

    def test_deferral_alone_no_longer_drags_score_under_threshold(self):
        """With 10+ leads and email deliberately off, the pipeline is healthy
        and must not page at all — previously it scored 80 but a 1-lead DB plus
        the phantom email alert guaranteed a permanent sub-70 score."""
        health, telegram, _ = _run(
            metrics={"leads_found": 25, "emails_sent": 0, "replies_received": 0},
            postal="")
        assert health["health_score"] >= 70
        telegram.assert_not_awaited()

    def test_live_production_metrics_go_quiet(self):
        """Regression for the reported spam, using the EXACT live numbers.

        Before: leads_found 1 (-30) + "no emails sent" (-20) = 50 < 70, so Lane 7
        paged an identical message every 2 hours indefinitely.
        After: the phantom email alert is gone, so the score is 70 — not under
        the gate — and the lane is silent without needing the debounce at all.
        The debounce remains the backstop for genuinely unhealthy states.
        """
        health, telegram, _ = _run(metrics=LIVE_PROD_METRICS, postal="")
        assert health["health_score"] == 70
        assert not any("No outreach emails" in a for a in health["alerts"])
        telegram.assert_not_awaited()
