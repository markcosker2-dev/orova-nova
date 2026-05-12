import os
import logging
import asyncio
import json
from typing import List, Dict, Optional, Any
from types import SimpleNamespace

from app.core.config import cfg

logger = logging.getLogger(__name__)


class UnifiedAIClient:
    """
    OROVA Engine — DeepSeek as PRIMARY AI Engine.

    PRIMARY: DeepSeek Chat
    FALLBACK: Groq -> OpenRouter

    All sub-agents use DeepSeek by default

    AGGRESSIVE MEMORY MANAGEMENT:
    - Context window limits enforced
    - Automatic conversation pruning
    - Memory cleanup after each operation
    """

    # ── Model Map: DeepSeek models per sub-agent role ─────────
    AGENT_MODELS = {
        "nova":      "deepseek-chat",    # Director: Heavy reasoning
        "hawk":      "deepseek-chat",    # Lead Hunter: Fast extraction
        "gate":      "deepseek-chat",    # Qualification: Nuanced logic
        "quill":     "deepseek-chat",    # Copywriter: Creative quality
        "closer":    "deepseek-chat",    # Sales: Strategic framing
        "oracle":    "deepseek-chat",    # Analytics: Math & logic
        "viper":     "deepseek-chat",    # Stealth: Fast data operations
        "sage":      "deepseek-chat",    # Ads: Analytical extraction
        "default":   "deepseek-chat",    # Default: Balanced performance
    }

    def __init__(self):
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")

        # ── PRIMARY: DeepSeek Client ─────
        self.deepseek_client = None
        deepseek_key = getattr(cfg, "deepseek_api_key", None) or os.getenv("DEEPSEEK_API_KEY")
        if deepseek_key:
            try:
                from openai import AsyncOpenAI
                self.deepseek_client = AsyncOpenAI(
                    api_key=deepseek_key,
                    base_url="https://api.deepseek.com/v1"
                )
                logger.info("[+] DeepSeek PRIMARY READY")
            except Exception as e:
                logger.warning(f"[-] DeepSeek init failed: {e}")
        else:
            logger.warning("[-] DEEPSEEK_API_KEY not set - limited functionality")

        # ── FALLBACK: Groq Client ─────
        self.groq_client = None
        groq_key = getattr(cfg, "groq_api_key", None) or os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                logger.info("[+] Groq FALLBACK READY")
            except Exception as e:
                logger.warning(f"[-] Groq init failed: {e}")

        # ── MEMORY MANAGEMENT ─────
        self.active_conversations = {}  # Track active conversation contexts
        self.memory_limits = {
            "max_context_length": 100000,  # Characters, not tokens
            "max_messages": 20,  # Max messages per conversation
            "cleanup_interval": 300,  # Clean up every 5 minutes
        }

        # Log role → model mappings
        logger.info("🎭 FREE Sub-Agent Model Assignments:")
        for role, model in self.AGENT_MODELS.items():
            logger.info(f"    [{role:10}] → {model}")

    # ================================================================
    #  FREE CHAT METHOD - 100% FREE OPERATION
    # ================================================================
    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                    temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        """
        Send a chat request through FREE Gemini 1.5 Flash with memory management.

        Args:
            messages: Either a string (auto-wrapped) or List[Dict] of messages
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Max response tokens (limited by free tier)
            role: The agent ID (nova, hawk, quill, etc.) to fetch the correct model.
        """

        # Auto-wrap string prompts
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        # AGGRESSIVE MEMORY MANAGEMENT: Prune conversation history
        messages = self._prune_conversation(messages, role)

        errors = []
        model = self.AGENT_MODELS.get(role, self.AGENT_MODELS["default"])

        # ── PRIMARY: DeepSeek ─────────────────
        if self.deepseek_client:
            try:
                logger.info(f"[*] AI ({role}): Using DeepSeek {model}")

                response = await self.deepseek_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=30.0
                )

                if response and response.choices:
                    logger.info(f"[+] AI ({role}): DeepSeek {model} responded.")
                    return response.choices[0].message

            except Exception as e:
                err_str = str(e)
                logger.warning(f"[!] DeepSeek {model} failed: {err_str}")
                errors.append(f"DeepSeek {model}: {err_str}")

        # ── FALLBACK: Groq ─────────────────
        if self.groq_client:
            try:
                logger.info(f"[*] AI ({role}): Falling back to Groq")

                response = await self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=temperature,
                    max_tokens=min(max_tokens, 8192),
                    timeout=15.0
                )

                if response and response.choices:
                    logger.info(f"[+] AI ({role}): Groq responded.")
                    return response.choices[0].message

            except Exception as e:
                err_str = str(e)
                logger.warning(f"[!] Groq failed: {err_str}")
                errors.append(f"Groq: {err_str}")

        # ── EMERGENCY FALLBACK: Return error message ──────────────
        last_error_log = " | ".join(errors)
        logger.error(f"[!!] ALL FREE AI PROVIDERS FAILED for role `{role}`. Errors: {last_error_log}")

        # Create a mock response for graceful failure
        from collections import namedtuple
        MockMsg = namedtuple("MockMsg", ["content", "tool_calls"])
        err_msg = f"🚨 FREE AI SYSTEM UNAVAILABLE\nRole: {role}\nPlease check GEMINI_API_KEY configuration.\n\nDiagnostic:\n" + "\n".join(f"- {e}" for e in errors)
        return MockMsg(content=err_msg, tool_calls=None)

    # ── MEMORY MANAGEMENT METHODS ────────────────────────────────

    def _prune_conversation(self, messages: List[Dict], role: str) -> List[Dict]:
        """Aggressively prune conversation to stay within memory limits."""
        if len(messages) <= self.memory_limits["max_messages"]:
            return messages

        # Keep system message + last N messages
        pruned = []
        system_msg = None
        for msg in messages:
            if msg.get("role") == "system":
                system_msg = msg
                break

        if system_msg:
            pruned.append(system_msg)

        # Keep last N non-system messages
        recent_messages = [m for m in messages if m.get("role") != "system"]
        pruned.extend(recent_messages[-self.memory_limits["max_messages"]:])

        logger.info(f"🧠 Memory pruned for {role}: {len(messages)} → {len(pruned)} messages")
        return pruned


    
    async def generate_response(self, prompt: str, temperature=0.7, max_tokens=2000, role: str = "default") -> str:
        """Alias for chat() method - maintains backwards compatibility"""
        response = await self.chat(prompt, temperature=temperature, max_tokens=max_tokens, role=role)
        return response.content
