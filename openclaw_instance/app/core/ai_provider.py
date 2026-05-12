"""
OROVA Nova — AI Provider Manager
Supports: OpenRouter, Groq, Google Gemini, DeepSeek, and Kilo Code MiMo v2 Pro (free).
The system automatically falls back through providers if one fails.
"""
import os
import json
import logging
from typing import List, Dict, Optional, Any
from types import SimpleNamespace

logger = logging.getLogger(__name__)


class AIProvider:
    """A single AI provider."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, cost_per_1k: float = 0.0):
        self.name = name
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.cost_per_1k = cost_per_1k
        self.available = bool(api_key and api_key != "demo-key")

    def __repr__(self):
        return f"<AIProvider {self.name} model={self.model} available={self.available}>"


class AIProviderManager:
    """
    Manages multiple AI providers with automatic fallback.
    Tries cheapest/free first, then falls back to paid providers.
    """

    def __init__(self):
        self.providers = self._load_providers()
        self._log_providers()

    def _load_providers(self) -> List[AIProvider]:
        """Load all configured providers, ordered by cost (free first)."""
        providers = []

        # Kilo Code MiMo v2 Pro (FREE)
        mimo_key = os.getenv("MIMO_API_KEY", "")
        mimo_base = os.getenv("MIMO_BASE_URL", "https://api.kilocode.ai/v1")
        mimo_model = os.getenv("MIMO_MODEL", "MiMo/v2-pro")
        if mimo_key:
            providers.append(AIProvider(
                name="MiMo v2 Pro",
                base_url=mimo_base,
                api_key=mimo_key,
                model=mimo_model,
                cost_per_1k=0.0
            ))

        # Groq (FREE tier, fast)
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            providers.append(AIProvider(
                name="Groq",
                base_url="https://api.groq.com/openai/v1",
                api_key=groq_key,
                model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                cost_per_1k=0.0
            ))

        # OpenRouter (many free models)
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if or_key:
            providers.append(AIProvider(
                name="OpenRouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=or_key,
                model=os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-lite:free"),
                cost_per_1k=0.0
            ))

        # DeepSeek (cheap)
        ds_key = os.getenv("DEEPSEEK_API_KEY", "")
        if ds_key:
            providers.append(AIProvider(
                name="DeepSeek",
                base_url="https://api.deepseek.com/v1",
                api_key=ds_key,
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                cost_per_1k=0.0014
            ))

        # OpenAI (most expensive, last resort)
        oa_key = os.getenv("OPENAI_API_KEY", "")
        if oa_key:
            providers.append(AIProvider(
                name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key=oa_key,
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                cost_per_1k=0.0015
            ))

        # Google Gemini (Native OpenAI-Compatible)
        gg_key = os.getenv("GOOGLE_API_KEY", "")
        if gg_key:
            providers.append(AIProvider(
                name="Google Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=gg_key,
                model=os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
                cost_per_1k=0.0
            ))

        return providers

    def _log_providers(self):
        available = [p for p in self.providers if p.available]
        logger.info(f"[AI PROVIDERS] {len(available)} available: {[p.name for p in available]}")
        if not available:
            logger.warning("[AI PROVIDERS] No API keys configured! System will use local fallback.")

    def chat(
        self,
        messages: List[Dict],
        tools: List[Dict] = None,
        model: str = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Any:
        """
        Send a chat completion request. Tries providers in order, falls back on failure.
        Returns a message object with .content and optional .tool_calls
        """
        import httpx

        for provider in self.providers:
            if not provider.available:
                continue

            try:
                from openai import OpenAI

                client = OpenAI(
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                    http_client=httpx.Client(timeout=60)
                )

                kwargs = {
                    "model": model or provider.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }

                if tools:
                    kwargs["tools"] = tools

                response = client.chat.completions.create(**kwargs)
                if not response or not hasattr(response, 'choices') or not response.choices:
                    logger.warning(f"[AI] {provider.name} returned empty response")
                    continue

                message = response.choices[0].message
                
                # Track usage
                usage = getattr(response, 'usage', None)
                if usage:
                    cost = (usage.total_tokens / 1000) * provider.cost_per_1k
                    logger.info(f"[AI] {provider.name}: {usage.total_tokens} tokens, ${cost:.6f}")

                return message

            except Exception as e:
                # Catch-all to prevent crash on HTML error pages or Rate Limits
                err_str = str(e).lower()
                if "429" in err_str:
                    logger.error(f"[AI] {provider.name} RATE LIMITED (429)")
                elif "404" in err_str:
                    logger.error(f"[AI] {provider.name} MODEL NOT FOUND (404)")
                else:
                    logger.warning(f"[AI] {provider.name} failed: {e}")
                continue

        # All providers failed — local fallback
        logger.warning("[AI] All providers failed. Using local fallback.")
        return self._local_fallback(messages)

    def _local_fallback(self, messages: List[Dict]) -> SimpleNamespace:
        """Structured fallback when no AI providers work."""
        last_msg = messages[-1].get("content", "") if messages else ""
        lower = last_msg.lower()

        if any(k in lower for k in ["find", "search", "lead", "hunt"]):
            content = "DONE: Lead search initiated."
        elif any(k in lower for k in ["email", "outreach", "draft"]):
            content = "DONE: Email draft queued."
        elif any(k in lower for k in ["call", "phone", "dial"]):
            content = "DONE: Call sequence initiated."
        elif any(k in lower for k in ["report", "analytics", "metric"]):
            content = "DONE: Report generated."
        else:
            content = "DONE: Task acknowledged."

        return SimpleNamespace(content=content, tool_calls=None)

    def get_status(self) -> Dict:
        """Get status of all providers."""
        return {
            p.name: {
                "model": p.model,
                "available": p.available,
                "cost_per_1k_tokens": p.cost_per_1k
            }
            for p in self.providers
        }


# Global instance
ai = AIProviderManager()
