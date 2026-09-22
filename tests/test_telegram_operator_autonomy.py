"""Nova takes safe initiative in Telegram without bypassing external gates."""
import asyncio
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
    assert "Next move:" in result


def test_operator_focus_does_not_fake_progress_when_queue_is_empty():
    async def candidates():
        if False:
            yield None

    with patch.object(nova_chat, "_contact_candidates", candidates):
        result = asyncio.run(nova_chat.operator_focus())
    assert "do not manufacture activity" in result
    assert "did not send or call anyone" in result
