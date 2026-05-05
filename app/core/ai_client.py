import os
import logging
import asyncio
import json
from typing import List, Dict, Optional, Any
from types import SimpleNamespace

logger = logging.getLogger(__name__)


class UnifiedAIClient:
    """
    Unified AI Client — Direct Provider Access via OpenRouter + Groq fallback.

    Primary: OpenRouter (OPENAI_API_KEY + OPENAI_BASE_URL from .env)
    Fallback: Groq (GROQ_API_KEY for ultra-fast inference)

    Role-Based Model Selection:
        reasoner  → Claude Sonnet 4   (complex reasoning, tool use, planner)
        writer    → Claude Sonnet 4   (persuasive copywriting, emails)
        extractor → GPT-4o            (structured JSON extraction)
        fast      → GPT-4o-mini       (quick tasks, classification)
        default   → Claude Sonnet 4   (general purpose)
    """

    # ── Model Flavors (Dynamic Brain Selection) ───────────────────
    FLAVORS = {
        "fast":   "google/gemini-2.0-flash-lite-preview-02-05:free",
        "smart":  "meta-llama/llama-3.3-70b-instruct:free",
        "genius": "deepseek/deepseek-r1:free"
    }

    FLAVOR_FILE = "app/data/model_flavor.json"

    def _get_flavor(self) -> str:
        """Read the current brain flavor from disk."""
        try:
            if os.path.exists(self.FLAVOR_FILE):
                with open(self.FLAVOR_FILE, 'r') as f:
                    return json.load(f).get("flavor", "fast")
        except: pass
        return "fast"

    def _set_flavor(self, flavor: str):
        """Save the current brain flavor to disk."""
        try:
            os.makedirs(os.path.dirname(self.FLAVOR_FILE), exist_ok=True)
            with open(self.FLAVOR_FILE, 'w') as f:
                json.dump({"flavor": flavor}, f)
        except: pass

    # ── Model Flavors (May 2026 Imperial Strategy) ──────────────
    FLAVORS = {
        "fast":   "google/gemini-2.0-flash-lite-preview-02-05:free", # Speed
        "smart":  "openai/gpt-oss-120b:free",                       # CEO Failsafe
        "genius": "qwen/qwen3-coder-480b-instruct:free",           # Logic Beast
        "kimi":   "moonshotai/kimi-k2.6"                            # CEO Primary (1T Param)
    }

    FLAVOR_FILE = "app/data/model_flavor.json"

    def _get_flavor(self) -> str:
        """Read the current brain flavor from disk."""
        try:
            if os.path.exists(self.FLAVOR_FILE):
                with open(self.FLAVOR_FILE, 'r') as f:
                    return json.load(f).get("flavor", "fast")
        except: pass
        return "fast"

    def _set_flavor(self, flavor: str):
        """Save the current brain flavor to disk."""
        try:
            os.makedirs(os.path.dirname(self.FLAVOR_FILE), exist_ok=True)
            with open(self.FLAVOR_FILE, 'w') as f:
                json.dump({"flavor": flavor}, f)
        except: pass

    # ── Imperial Agent Grid (Specialized Brains) ──────────────────
    ROLE_MODELS = {
        # Core Roles
        "reasoner":  "openai/gpt-oss-120b:free",
        "writer":    "meta-llama/llama-3.3-70b-instruct:free",
        "extractor": "google/gemini-2.0-flash-lite-preview-02-05:free",
        "fast":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "default":   "openai/gpt-oss-120b:free",

        # Agent-Specific Specialists
        "nova":      "google/gemini-2.0-flash-lite-preview-02-05:free", # CEO (Stable Tool Caller)
        "hawk":      "qwen/qwen3-coder-480b-instruct:free",       # Research (480B)
        "closer":    "meta-llama/llama-3.3-70b-instruct:free",    # Sales (Llama 3.3)
        "pixel":     "google/gemini-2.0-flash-lite-preview-02-05:free", # Creative (Vision)
        "atlas":     "qwen/qwen3-coder-480b-instruct:free",       # Dev (Coding)
        "oracle":    "openai/gpt-oss-120b:free",                  # Finance (Logic)
        "sentinel":  "google/gemini-2.0-flash-lite-preview-02-05:free", # Ops
        "echo":      "google/gemini-2.0-flash-lite-preview-02-05:free",
        "viper":     "google/gemini-2.0-flash-lite-preview-02-05:free"
    }

    FALLBACK_CHAIN = [
        "openai/gpt-oss-120b:free",
        "qwen/qwen3-coder-480b-instruct:free",
        "google/gemini-2.0-flash-lite-preview-02-05:free",
    ]

    # Groq uses different model names
    GROQ_MODEL = "llama-3.3-70b-versatile"

    def __init__(self):
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")

        # ── Primary: OpenRouter via OPENAI_API_KEY ────────────────
        self.primary_client = None
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        if api_key:
            try:
                from openai import AsyncOpenAI
                self.primary_client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url
                )
                logger.info(f"[+] Primary AI Client (OpenRouter) -- READY at {base_url}")
            except Exception as e:
                logger.warning(f"[-] Primary AI Client init failed: {e}")
        else:
            logger.warning("[-] OPENAI_API_KEY not set — primary AI unavailable")

        # ── Fallback: Groq for ultra-fast inference ───────────────
        self.groq_client = None
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                logger.info("[+] Fallback AI Client (Groq) -- READY")
            except Exception as e:
                logger.warning(f"[-] Groq fallback init failed: {e}")

        # Log available models
        for role, model in self.ROLE_MODELS.items():
            logger.info(f"    [{role}] → {model}")

    # ================================================================
    #  MAIN CHAT METHOD
    # ================================================================
    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                   temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        """
        Send a chat request through OpenRouter, with Groq failover.

        Args:
            messages: Either a string (auto-wrapped) or List[Dict] of messages
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Max response tokens
            role: One of 'reasoner', 'writer', 'extractor', 'fast', 'default'
                  Selects the optimal model for the task type.
        """

        # ── Auto-wrap string prompts ──────────────────────────────
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        if not self.primary_client and not self.groq_client:
            return SimpleNamespace(
                content="[!!] No AI providers available. Check OPENAI_API_KEY and GROQ_API_KEY.",
                tool_calls=None
            )

        # ── Select primary model based on flavor override ──────────
        flavor = self._get_flavor()
        if flavor in self.FLAVORS:
            primary_model = self.FLAVORS[flavor]
        else:
            primary_model = self.ROLE_MODELS.get(role, self.ROLE_MODELS["default"])

        # Build fallback chain: primary first, then others (deduplicated)
        chain = [primary_model]
        for model in self.FALLBACK_CHAIN:
            if model not in chain:
                chain.append(model)

        # ── Phase 1: Try each model on OpenRouter ─────────────────
        last_error = None
        if self.primary_client:
            for model_name in chain:
                for attempt in range(2):
                    try:
                        logger.info(f"[*] AI ({role}): Trying {model_name}" + (f" (retry {attempt+1})" if attempt > 0 else ""))
                        response = await self.primary_client.chat.completions.create(
                            model=model_name,
                            messages=messages,
                            tools=tools,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            timeout=90.0
                        )
                        if response.choices:
                            logger.info(f"[+] AI ({role}): {model_name} responded.")
                            return response.choices[0].message
                    except Exception as e:
                        last_error = str(e)
                        err_lower = last_error.lower()

                        # Quota / rate limit → skip retries, try next model
                        if any(kw in err_lower for kw in ("credit", "quota", "balance", "429", "rate")):
                            logger.warning(f"[!] Quota/rate limit on {model_name}. Trying next...")
                            break

                        # Connection or timeout → retry after delay
                        if any(kw in err_lower for kw in ("timeout", "connect", "refused", "reset", "connection")):
                            logger.warning(f"[!] Connection issue on {model_name} (attempt {attempt+1}/2)")
                            if attempt < 1:
                                await asyncio.sleep(3)
                                continue
                            else:
                                break

                        # Other error → log and try next model
                        logger.warning(f"[!] {model_name} failed: {e}")
                        break

        # ── Phase 2: Groq Failover ────────────────────────────────
        if self.groq_client:
            try:
                logger.info(f"[*] AI ({role}): FAILOVER to Groq ({self.GROQ_MODEL})")
                response = await self.groq_client.chat.completions.create(
                    model=self.GROQ_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30.0
                )
                if response.choices:
                    logger.info(f"[+] AI ({role}): Groq responded.")
                    return response.choices[0].message
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[!] Groq failover failed: {e}")

        # ── All providers failed ──────────────────────────────────
        self._send_alert(
            f"🚨 **ALL AI PROVIDERS FAILED**\n"
            f"Role: {role}\n"
            f"Last error: {last_error[:200] if last_error else 'Unknown'}\n"
            f"Check OPENAI_API_KEY and GROQ_API_KEY"
        )

        return SimpleNamespace(
            content=f"[!!] All AI providers failed for role '{role}'. Last error: {last_error[:100] if last_error else 'Unknown'}",
            tool_calls=None
        )

    # ================================================================
    #  CONVENIENCE METHODS (Role Shortcuts)
    # ================================================================
    async def reason(self, messages, tools=None, **kwargs):
        """Use the best reasoning model (planner, complex tasks)."""
        return await self.chat(messages, tools=tools, role="reasoner", **kwargs)

    async def write(self, prompt: str, **kwargs):
        """Use the best writing model. Returns plain text string."""
        result = await self.chat(prompt, role="writer", **kwargs)
        return result.content or ""

    async def extract(self, prompt: str, **kwargs):
        """Use the best extraction model. Returns plain text string."""
        result = await self.chat(prompt, role="extractor", temperature=0.2, **kwargs)
        return result.content or ""

    async def quick(self, prompt: str, **kwargs):
        """Use the fastest model. Returns plain text string."""
        result = await self.chat(prompt, role="fast", **kwargs)
        return result.content or ""

    # ================================================================
    #  TELEGRAM ALERT
    # ================================================================
    def _send_alert(self, msg: str):
        """Send System Health alert to Admin via Telegram."""
        if not self.tg_token or not self.admin_chat_id:
            return
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            payload = {"chat_id": self.admin_chat_id, "text": msg, "parse_mode": "Markdown"}
            try:
                httpx.post(url, json=payload, timeout=5.0)
            except Exception:
                pass
        except Exception:
            pass
