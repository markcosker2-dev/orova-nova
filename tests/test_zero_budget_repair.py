import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.database import DatabaseManager
from app.core.router import Router
from app.skills import email_sequence_skill as sequences


@pytest.fixture(autouse=True)
def zero_budget_defaults(monkeypatch, funded_workflow_test_mode):
    monkeypatch.delenv("ZERO_BUDGET_MODE", raising=False)
    monkeypatch.delenv("CEO_AUTO_EXECUTE", raising=False)


@pytest.mark.parametrize("result", [
    {"status": "error", "skipped": True}, {"status": "pending"},
    {"status": "error"}, {},
])
def test_drip_does_not_advance_without_success(result):
    row = dict(campaign_id=7, lead_id=9, sequence_type="cold_intro_drip",
               current_step=1, client_id=0, email="owner@example.com",
               business="Example Custom Homes", owner="Alex", vertical="Builder")
    with patch.object(DatabaseManager, "fetchall", AsyncMock(return_value=[row])), \
         patch.object(DatabaseManager, "fetchone", AsyncMock(return_value=None)), \
         patch.object(DatabaseManager, "query", AsyncMock()) as write, \
         patch("app.skills.agentmail_skill.send_outreach", AsyncMock(return_value=result)), \
         patch.object(sequences, "update_sheets_lead_status", AsyncMock()) as sheet:
        asyncio.run(sequences.send_pending_drip_emails())
    # Logging may persist unrelated events. The invariant is that a failed or
    # pending send never advances the campaign or marks the prospect contacted.
    for call in write.await_args_list:
        sql = " ".join(call.args[0].lower().split())
        assert not sql.startswith("update drip_campaigns")
        assert not sql.startswith("update leads")
    sheet.assert_not_awaited()


def test_chat_remembers_previous_turn_without_sharing_chats(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "1")
    monkeypatch.setenv("PERSONAL_CHAT_ID", "2")
    states = {}

    async def get(key, default=None):
        return states.get(key, default)

    async def save(key, value):
        states[key] = value

    reply = AsyncMock(return_value="Understood.")
    async def conversation():
        with patch.object(DatabaseManager, "get_state", get), \
             patch.object(DatabaseManager, "set_state", save), \
             patch("app.core.nova_chat.nova_reply", reply):
            router = Router()
            await router.handle_message("Focus on remodelers", 1)
            await router.handle_message("What did I ask?", 1)
            remembered = reply.call_args.kwargs["history"]
            assert any(h["content"] == "Focus on remodelers" for h in remembered)
            await router.handle_message("Hello", 2)
            assert not reply.call_args.kwargs["history"]
    asyncio.run(conversation())


def test_status_does_not_relabel_totals_as_today():
    with patch.object(DatabaseManager, "aget_metrics", AsyncMock(return_value={"leads_found": 310})), \
         patch.object(DatabaseManager, "fetchone", AsyncMock(return_value=None)):
        text = asyncio.run(Router()._status_handler())
    assert "today" not in text.lower()
    assert "310" in text
    assert "learned" not in text.lower()


def test_rate_limit_is_not_reported_as_done():
    router = Router()
    with patch.object(router, "route", AsyncMock(return_value={"error": "Rate limit exceeded"})), \
         patch.object(DatabaseManager, "get_state", AsyncMock(return_value=[])), \
         patch.object(DatabaseManager, "set_state", AsyncMock()):
        assert "Rate limit" in asyncio.run(router.handle_message("hello", 0))


def test_zero_budget_blocks_paid_dial_before_any_provider_access():
    from app.skills.outbound_dialer import trigger_retell_call
    with patch("httpx.AsyncClient") as network:
        result = asyncio.run(trigger_retell_call("+12025550123", {}))
    assert result["skipped"] and "$0" in result["error"]
    network.assert_not_called()


def test_zero_budget_blocks_cold_email_even_with_old_approval():
    from app.skills.agentmail_skill import send_outreach
    with patch("app.skills.agentmail_skill._get_client") as client:
        result = asyncio.run(send_outreach("owner@example.com", "Hello", "Hello", _approval_checked=True))
    assert result["status"] == "blocked"
    client.assert_not_called()


def test_unknown_chat_cannot_read_pipeline_or_consume_approvals(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "1")
    monkeypatch.delenv("PERSONAL_CHAT_ID", raising=False)
    with patch.object(DatabaseManager, "get_state", AsyncMock()) as read:
        result = asyncio.run(Router().handle_message("/leads", 999))
    assert "access required" in result
    read.assert_not_awaited()


def test_contact_card_is_draft_only_and_does_not_invent_name_or_email():
    from app.core.nova_chat import lead_contact_cards
    row = dict(id=9, business="Example Custom Homes", owner="Guessed Person", owner_confidence=35,
               vertical="custom home builder", state="WA", status="New", score=70,
               phone="", website="https://example.com", url="https://example.com/about",
               email="guessed@example.com", email_status="guessed")
    with patch.object(DatabaseManager, "fetchall", AsyncMock(return_value=[row])), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=False)), \
         patch.object(DatabaseManager, "query", AsyncMock()) as write:
        card = asyncio.run(lead_contact_cards(9))
    assert "not sent" in card
    assert "Hi there" in card
    assert "Guessed" not in card and "guessed@example.com" not in card
    assert "https://example.com" in card
    write.assert_not_awaited()


def test_contact_cards_exclude_suppressed_leads():
    from app.core.nova_chat import lead_contact_cards
    row = dict(id=9, business="Example Custom Homes", vertical="custom home builder", email="owner@example.com")
    with patch.object(DatabaseManager, "fetchall", AsyncMock(return_value=[row])), \
         patch("app.core.dnc.is_email_suppressed", AsyncMock(return_value=True)):
        card = asyncio.run(lead_contact_cards())
    assert "No eligible" in card
    assert "Example Custom Homes" not in card


def test_telegram_webhook_has_secret_without_manual_configuration(monkeypatch):
    from app.core.hardening import telegram_webhook_secret
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token-not-a-credential")
    secret = telegram_webhook_secret()
    assert len(secret) == 64 and secret != "test-bot-token-not-a-credential"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
    assert telegram_webhook_secret() == ""


def test_zero_budget_does_not_restore_speculative_auto_tasks():
    from app.core.ceo_brain import _reload_pending_proposals
    with patch.object(DatabaseManager, "fetchall", AsyncMock()) as read:
        assert asyncio.run(_reload_pending_proposals()) == 0
    read.assert_not_awaited()
