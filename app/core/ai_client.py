import os
import logging
import asyncio
import json
import time
from typing import List, Dict, Optional, Any
from types import SimpleNamespace
from collections import defaultdict
from dataclasses import dataclass
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

@dataclass
class GroqLimpResponse:
    """[P0] Sentinel type so the planner knows tool calls are unavailable."""
    content: str
    tools_available: bool = False
    tool_calls: Optional[List] = None

# --- [P0] Circuit Breaker State ---
_BREAKER: dict[str, dict] = defaultdict(lambda: {
    "failures": 0, "open_until": 0.0
})
_BREAKER_THRESHOLD = 3      # failures before opening
_BREAKER_COOLDOWN  = 60.0   # seconds before half-open retry

# ── [P6] ECONOMICS (Cost per 1M tokens) ──
MODEL_COSTS = {
    "google/gemini-2.0-flash-lite-preview-02-05:free": (0.0, 0.0), # Free tier
    "openai/gpt-4o": (5.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "anthropic/claude-3-5-sonnet": (3.0, 15.0),
    "__default__": (1.0, 3.0),
}

def estimate_cost(model: str, t_in: int, t_out: int) -> float:
    rates = MODEL_COSTS.get(model, MODEL_COSTS["__default__"])
    return round((t_in / 1e6) * rates[0] + (t_out / 1e6) * rates[1], 8)

def _provider(model_name: str) -> str:
    return model_name

def _is_open(model_name: str) -> bool:
    provider = _provider(model_name)
    b = _BREAKER[provider]
    if b["open_until"] > time.monotonic():
        return True
    if b["open_until"] > 0:          # cooldown expired → half-open
        b["open_until"] = 0.0
        b["failures"]   = 0
    return False

def _record_failure(model_name: str):
    provider = _provider(model_name)
    b = _BREAKER[provider]
    b["failures"] += 1
    if b["failures"] >= _BREAKER_THRESHOLD:
        b["open_until"] = time.monotonic() + _BREAKER_COOLDOWN
        logger.warning(f"[BREAKER] {provider} circuit OPEN for {_BREAKER_COOLDOWN}s")

def _record_success(model_name: str):
    provider = _provider(model_name)
    _BREAKER[provider] = {"failures": 0, "open_until": 0.0}

async def _backoff(attempt: int, base: float = 1.0, cap: float = 8.0):
    delay = min(base * (2 ** attempt), cap)
    await asyncio.sleep(delay)

class UnifiedAIClient:
    """
    Unified AI Client — OpenRouter + Groq fallback.
    Indestructible Edition (May 2026).
    """

    # ── Model Flavors (User-Switchable via /mode) ──────────────────
    FLAVORS = {
        "fast":   "google/gemini-2.0-flash-lite-preview-02-05:free",
        "smart":  "openai/gpt-oss-120b:free",
        "genius": "qwen/qwen3-coder-480b-instruct:free",
    }

    FLAVOR_FILE = "app/data/model_flavor.json"

    async def _get_flavor(self) -> str:
        flavor = await DatabaseManager.get_state("model_flavor")
        return flavor if flavor else "fast"

    async def _set_flavor(self, flavor: str):
        try:
            await DatabaseManager.set_state("model_flavor", flavor)
        except Exception as e:
            logger.warning(f"[AI] set_flavor failed: {e}")

    # ── Role-Based Model Map ─────────
    ROLE_MODELS = {
        "reasoner":  "google/gemini-2.0-flash-lite-preview-02-05:free",
        "writer":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "extractor": "google/gemini-2.0-flash-lite-preview-02-05:free",
        "fast":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "default":   "google/gemini-2.0-flash-lite-preview-02-05:free",
        "nova":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "hawk":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "closer":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "oracle":    "google/gemini-2.0-flash-lite-preview-02-05:free",
        "sentinel":  "google/gemini-2.0-flash-lite-preview-02-05:free",
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

        # ─── NATIVE GEMINI CLIENT (100% Free, High Limit B2B engine) ───
        self.google_client = None
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=google_key)
                self.google_client = genai
                logger.info("[+] Native Google Gemini Client — READY")
            except Exception as e:
                logger.warning(f"[-] Gemini native init failed: {e}")

        self.primary_client = None
        api_key = os.getenv("OPENROUTER_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        if api_key:
            try:
                from openai import AsyncOpenAI
                self.primary_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                logger.info(f"[+] Primary AI Client (OpenRouter) — READY")
            except Exception as e:
                logger.warning(f"[-] Primary AI init failed: {e}")

        self.groq_client = None
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                logger.info("[+] Fallback AI Client (Groq) — READY")
            except Exception as e:
                logger.warning(f"[-] Groq init failed: {e}")

    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                   tool_choice: Optional[str] = None,
                   temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        if not self.google_client and not self.primary_client and not self.groq_client:
            return SimpleNamespace(content="[!!] No AI providers available.", tool_calls=None)

        # ─── TIER 1: Native Google Gemini 2.0 (Fast, Free, Block-proof) ───
        if self.google_client and not tools:
            try:
                logger.info(f"[*] AI ({role}): Querying Native Google Gemini (gemini-2.0-flash-lite)...")
                # Format messages for the official google API
                system_instruction = ""
                contents = []
                for msg in messages:
                    if msg.get("role") == "system":
                        system_instruction = msg.get("content", "")
                    else:
                        contents.append({
                            "role": "user" if msg.get("role") == "user" else "model",
                            "parts": [msg.get("content", "")]
                        })

                config = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens
                }

                model = self.google_client.GenerativeModel(
                    model_name="gemini-2.0-flash-lite",
                    system_instruction=system_instruction if system_instruction else None
                )

                # Execute Google API in executor thread to maintain async flow
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(contents=contents, generation_config=config)
                )

                if response and response.text:
                    logger.info(f"[+] AI ({role}): Direct Gemini OK")
                    return SimpleNamespace(content=response.text, tool_calls=None)
            except Exception as e:
                logger.warning(f"[!] Direct Gemini API call failed: {e}. Falling back to other providers...")

        flavor = await self._get_flavor()
        primary_model = self.FLAVORS[flavor] if flavor in self.FLAVORS else self.ROLE_MODELS.get(role, self.ROLE_MODELS["default"])

        chain = [primary_model]
        for model in self.FALLBACK_CHAIN:
            if model not in chain: chain.append(model)

        last_error = None
        if self.primary_client:
            for attempt, model_name in enumerate(chain):
                if _is_open(model_name):
                    logger.info(f"[BREAKER] Skipping {model_name} — circuit open")
                    continue

                try:
                    logger.info(f"[*] AI ({role}): Trying {model_name}")
                    kwargs = {
                        "model": model_name, "messages": messages, "tools": tools,
                        "temperature": temperature, "max_tokens": max_tokens, "timeout": 60.0
                    }
                    if tool_choice: kwargs["tool_choice"] = tool_choice

                    response = await self.primary_client.chat.completions.create(**kwargs)
                    if response.choices:
                        _record_success(model_name)
                        logger.info(f"[+] AI ({role}): {model_name} OK")
                        return response.choices[0].message
                except Exception as e:
                    last_error = str(e)
                    _record_failure(model_name)
                    if any(kw in last_error.lower() for kw in ("credit", "quota", "balance", "429", "rate")):
                        logger.warning(f"[!] Rate limit on {model_name}. Backing off...")
                        await _backoff(attempt)
                    else:
                        logger.warning(f"[!] {model_name} failed: {e}")
                    continue

        # --- Phase 2: Groq (Limp Mode) ---
        if self.groq_client:
            try:
                logger.info(f"[*] AI ({role}): FAILOVER to Groq (Limp Mode)")
                response = await self.groq_client.chat.completions.create(
                    model=self.GROQ_MODEL, messages=messages,
                    temperature=temperature, max_tokens=max_tokens, timeout=30.0
                )
                if response.choices:
                    logger.warning("[!] Entering Groq limp mode — tools stripped")
                    # Return sentinel type so planner knows tools are offline
                    return GroqLimpResponse(content=response.choices[0].message.content)
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
