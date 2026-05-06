import os
import logging
import asyncio
import json
from typing import List, Dict, Optional, Any
from types import SimpleNamespace

logger = logging.getLogger(__name__)


class UnifiedAIClient:
    """
    Unified AI Client — OpenRouter + Groq fallback.
    Smart Tool Scoping Edition (May 2026).
    """

    # ── Model Flavors (User-Switchable via /mode) ──────────────────
    FLAVORS = {
        "fast":   "google/gemini-2.0-flash-lite-preview-02-05:free",
        "smart":  "openai/gpt-oss-120b:free",
        "genius": "qwen/qwen3-coder-480b-instruct:free",
    }

    FLAVOR_FILE = "app/data/model_flavor.json"

    def _get_flavor(self) -> str:
        try:
            if os.path.exists(self.FLAVOR_FILE):
                with open(self.FLAVOR_FILE, 'r') as f:
                    return json.load(f).get("flavor", "fast")
        except: pass
        return "fast"

    def _set_flavor(self, flavor: str):
        try:
            os.makedirs(os.path.dirname(self.FLAVOR_FILE), exist_ok=True)
            with open(self.FLAVOR_FILE, 'w') as f:
                json.dump({"flavor": flavor}, f)
        except: pass

    # ── Role-Based Model Map (ALL use free, stable models) ─────────
    ROLE_MODELS = {
        "reasoner":  "google/gemini-2.0-flash-lite-preview-02-05:free",
        "writer":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "extractor": "google/gemini-2.0-flash-lite-preview-02-05:free",
        "fast":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "default":   "google/gemini-2.0-flash-lite-preview-02-05:free",
        # All agents use Gemini for stability. Tool calling works reliably.
        "nova":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "hawk":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "closer":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "pixel":     "google/gemini-2.0-flash-lite-preview-02-05:free",
        "atlas":     "google/gemini-2.0-flash-lite-preview-02-05:free",
        "oracle":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "sentinel":  "google/gemini-2.0-flash-lite-preview-02-05:free",
        "echo":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "viper":     "google/gemini-2.0-flash-lite-preview-02-05:free",
        "quill":     "google/gemini-2.0-flash-lite-preview-02-05:free",
    }

    FALLBACK_CHAIN = [
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "openai/gpt-oss-120b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]

    GROQ_MODEL = "llama-3.3-70b-versatile"

    def __init__(self):
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")

        # ── Primary: OpenRouter ────────────────────────────────────
        self.primary_client = None
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        if api_key:
            try:
                from openai import AsyncOpenAI
                self.primary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                logger.info(f"[+] Primary AI Client (OpenRouter) — READY")
            except Exception as e:
                logger.warning(f"[-] Primary AI init failed: {e}")
        else:
            logger.warning("[-] OPENAI_API_KEY not set")

        # ── Fallback: Groq ─────────────────────────────────────────
        self.groq_client = None
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                logger.info("[+] Fallback AI Client (Groq) — READY")
            except Exception as e:
                logger.warning(f"[-] Groq init failed: {e}")

        for role, model in self.ROLE_MODELS.items():
            logger.info(f"    [{role}] → {model}")

    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                   tool_choice: Optional[str] = None,
                   temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        if not self.primary_client and not self.groq_client:
            return SimpleNamespace(content="[!!] No AI providers available.", tool_calls=None)

        # Select model: flavor override OR role-based
        flavor = self._get_flavor()
        if flavor in self.FLAVORS:
            primary_model = self.FLAVORS[flavor]
        else:
            primary_model = self.ROLE_MODELS.get(role, self.ROLE_MODELS["default"])

        # Build fallback chain (deduplicated)
        chain = [primary_model]
        for model in self.FALLBACK_CHAIN:
            if model not in chain:
                chain.append(model)

        # ── Phase 1: OpenRouter ────────────────────────────────────
        last_error = None
        if self.primary_client:
            for model_name in chain:
                try:
                    logger.info(f"[*] AI ({role}): Trying {model_name}")
                    kwargs = {
                        "model": model_name,
                        "messages": messages,
                        "tools": tools,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "timeout": 60.0
                    }
                    if tool_choice:
                        kwargs["tool_choice"] = tool_choice

                    response = await self.primary_client.chat.completions.create(**kwargs)
                    if response.choices:
                        logger.info(f"[+] AI ({role}): {model_name} OK")
                        return response.choices[0].message
                except Exception as e:
                    last_error = str(e)
                    err_lower = last_error.lower()
                    if any(kw in err_lower for kw in ("credit", "quota", "balance", "429", "rate")):
                        logger.warning(f"[!] Rate limit on {model_name}. Next...")
                    else:
                        logger.warning(f"[!] {model_name} failed: {e}")
                    continue

        # ── Phase 2: Groq (no tools — Groq doesn't support them well) ──
        if self.groq_client:
            try:
                logger.info(f"[*] AI ({role}): FAILOVER to Groq")
                # Strip tools for Groq — it doesn't handle them reliably
                response = await self.groq_client.chat.completions.create(
                    model=self.GROQ_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30.0
                )
                if response.choices:
                    logger.info(f"[+] AI ({role}): Groq OK")
                    return response.choices[0].message
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[!] Groq failed: {e}")

        return SimpleNamespace(
            content=f"[!!] All AI providers failed for role '{role}'. Last error: {last_error[:100] if last_error else 'Unknown'}",
            tool_calls=None
        )

    # ── Convenience Methods ────────────────────────────────────────
    async def reason(self, messages, tools=None, **kwargs):
        return await self.chat(messages, tools=tools, role="reasoner", **kwargs)

    async def write(self, prompt: str, **kwargs):
        result = await self.chat(prompt, role="writer", **kwargs)
        return result.content or ""

    async def extract(self, prompt: str, **kwargs):
        result = await self.chat(prompt, role="extractor", temperature=0.2, **kwargs)
        return result.content or ""

    async def quick(self, prompt: str, **kwargs):
        result = await self.chat(prompt, role="fast", **kwargs)
        return result.content or ""

    def _send_alert(self, msg: str):
        if not self.tg_token or not self.admin_chat_id:
            return
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            httpx.post(url, json={"chat_id": self.admin_chat_id, "text": msg}, timeout=5.0)
        except: pass
