"""OpenRouter free-models-only guard (owner mandate 2026-07-21).

OpenRouter (tier 3) must never bill. The guard filters the model chain to
':free' variants unless OPENROUTER_ALLOW_PAID=1 — so a paid model added to
ROLE_MODELS / FALLBACK_CHAIN by a future edit can never spend.
"""
import os
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.core.ai_client import UnifiedAIClient
from tests.test_provider_chain_resilience import _bare_client, _completions


def test_all_configured_openrouter_models_are_free():
    # The shipped config must already be free-only.
    for m in UnifiedAIClient.ROLE_MODELS.values():
        assert m.endswith(":free"), m
    for m in UnifiedAIClient.FALLBACK_CHAIN:
        assert m.endswith(":free"), m


def test_paid_model_is_dropped_from_openrouter_chain():
    called = []

    async def capture(**kw):
        called.append(kw["model"])
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None))])

    client = _bare_client(primary=_completions(capture))
    # Inject a paid model at the head of the chain.
    with patch.object(UnifiedAIClient, "ROLE_MODELS",
                      {"default": "openai/gpt-4o", "nova": "openai/gpt-4o"}), \
         patch.object(UnifiedAIClient, "FALLBACK_CHAIN",
                      ["openai/gpt-4o", "meta-llama/llama-3.3-70b-instruct:free"]), \
         patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENROUTER_ALLOW_PAID", None)
        asyncio.run(client.chat("hi"))
    # gpt-4o must never have been called; only the :free model was tried.
    assert "openai/gpt-4o" not in called
    assert called == ["meta-llama/llama-3.3-70b-instruct:free"]


def test_allow_paid_env_opts_in():
    called = []

    async def capture(**kw):
        called.append(kw["model"])
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="ok", tool_calls=None))])

    client = _bare_client(primary=_completions(capture))
    with patch.object(UnifiedAIClient, "ROLE_MODELS",
                      {"default": "openai/gpt-4o", "nova": "openai/gpt-4o"}), \
         patch.object(UnifiedAIClient, "FALLBACK_CHAIN", ["openai/gpt-4o"]), \
         patch.dict(os.environ, {"OPENROUTER_ALLOW_PAID": "1"}):
        asyncio.run(client.chat("hi"))
    assert called == ["openai/gpt-4o"]  # explicit opt-in honored
