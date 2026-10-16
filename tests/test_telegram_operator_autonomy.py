"""Nova takes safe initiative in Telegram without bypassing external gates."""
import asyncio
import sqlite3
from unittest.mock import AsyncMock, patch

from app.core import nova_chat
from app.core.nova_chat import NOVA_PERSONA
from app.core.router import Router


def test_persona_is_decisive_but_truthful_about_external_actions():
    assert "OPERATING PARTNER" in NOVA_PERSONA
    assert "Make the decision" in NOVA_PERSONA
    assert "Ask at most one question" in NOVA_PERSONA
    assert "I stopped at the [name] gate" in NOVA_PERSONA
    assert "unless the system returned direct evidence" in NOVA_PERSONA
    assert "two workflows distinct" in NOVA_PERSONA
    assert "Retell executes an authorized call" in NOVA_PERSONA


def test_natural_next_move_request_uses_deterministic_focus_route():
    with patch("app.core.nova_chat.operator_focus", AsyncMock(return_value="prepared")) as focus:
        result = asyncio.run(Router().route("what should i do", chat_id=0))
    assert result == "prepared"
    focus.assert_awaited_once()


def test_find_next_prospect_is_preparation_not_action_block():
    with patch("app.core.nova_chat.operator_focus", AsyncMock(return_value="lead ready")):
        result = asyncio.run(Router().route("find our next prospect", chat_id=0))
    assert result == "lead ready"


def test_operator_focus_selects_one_lead_and_states_nothing_was_sent():
    async def candidates():
        yield {"id": 42, "business": "Example Builder"}

    with patch.object(nova_chat, "_contact_candidates", candidates), \
         patch.object(nova_chat, "lead_contact_cards", AsyncMock(return_value="contact card")):
        result = asyncio.run(nova_chat.operator_focus())
    assert "lead #42" in result
    assert "nothing was sent or called" in result
    assert "contact card" in result
    assert "Next:" in result


def test_operator_focus_does_not_fake_progress_when_queue_is_empty():
    async def candidates():
        if False:
            yield None

    with patch.object(nova_chat, "_contact_candidates", candidates), \
         patch("app.core.database.DatabaseManager.fetchone", AsyncMock(return_value={"held": 0})):
        result = asyncio.run(nova_chat.operator_focus())
    assert "do not manufacture activity" in result
    assert "did not send or call anyone" in result


def test_focus_reviews_existing_recovery_holds_instead_of_requesting_more_leads():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE leads (id INTEGER, business TEXT, owner TEXT, owner_confidence INTEGER, "
               "email TEXT, email_status TEXT, phone TEXT, website TEXT, url TEXT, vertical TEXT, "
               "status TEXT, state TEXT, score INTEGER, client_id INTEGER)")
    db.executemany("INSERT INTO leads (id, business, status, score, client_id) VALUES (?, ?, ?, ?, ?)", [
        (1, "First Custom Homes", "Recovery Hold", 90, 0),
        (2, "Second Custom Homes", "Recovery Hold", 80, 0),
        (3, "Client Private Record", "Recovery Hold", 99, 1),
    ])

    async def fetchall(sql, params=()):
        return db.execute(sql, params).fetchall()

    async def fetchone(sql, params=()):
        return db.execute(sql, params).fetchone()

    try:
        with patch("app.core.database.DatabaseManager.fetchall", fetchall), \
             patch("app.core.database.DatabaseManager.fetchone", fetchone):
            result = asyncio.run(nova_chat.operator_focus())
        assert "2" in result and "Recovery Hold" in result
        assert "review" in result.lower()
        assert "hunt" not in result.lower()
        assert "did not send or call anyone" in result
        assert [r[0] for r in db.execute("SELECT status FROM leads")] == ["Recovery Hold"] * 3
    finally:
        db.close()


def test_focus_does_not_treat_a_failed_hold_read_as_an_empty_pipeline():
    async def candidates():
        if False:
            yield None

    with patch.object(nova_chat, "_contact_candidates", candidates), \
         patch("app.core.database.DatabaseManager.fetchone", AsyncMock(side_effect=RuntimeError("offline"))):
        result = asyncio.run(nova_chat.operator_focus())
    assert "unable to verify" in result.lower()
    assert "hunt" not in result.lower()
    assert "did not send or call anyone" in result


def test_status_never_equates_contact_label_with_verified_send():
    metrics = {"leads_found": 312, "emails_sent": 48,
               "replies_received": 0, "meetings_booked": 0}
    with patch("app.core.database.DatabaseManager.aget_metrics",
               AsyncMock(return_value=metrics)):
        result = asyncio.run(nova_chat.pipeline_status())
    assert "48 marked Contacted/Email Sent" in result
    assert "do not prove a message was delivered" in result
    assert "/focus" in result
