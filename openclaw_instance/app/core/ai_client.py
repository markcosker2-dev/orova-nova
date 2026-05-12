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
    Unified AI Client — OpenRouter with FREE models as PRIMARY.
    
    Each sub-agent uses a different model optimized for its specific task:
    - reasoner  → deepseek/deepseek-r1:free (best reasoning, math, code)
    - writer   → meta-llama/llama-3.1-8b-instruct:free (best instruction following)
    - extractor → google/gemini-2.0-flash-lite:free (fast extraction)
    - vision   → google/gemini-2.0-flash-exp (vision, images)
    - default  → google/gemini-2.0-flash-lite:free
    
    FALLBACK: Groq → MiMo for redundancy
    """

    # ── Model Map: Best free models per sub-agent role ─────────
    AGENT_MODELS = {
        "nova":      "llama-3.3-70b-versatile",  # Director: Needs heavy reasoning
        "hawk":      "llama-3.1-8b-instant",     # Scraper: Fast extraction
        "gate":      "llama-3.3-70b-versatile",  # Qualification: Nuanced logic
        "quill":     "llama-3.3-70b-versatile",  # Copywriter: Creative quality
        "closer":    "llama-3.3-70b-versatile",  # Sales: Strategic framing
        "oracle":    "llama-3.3-70b-versatile",  # Analytics: Math & logic
        "viper":     "llama-3.1-8b-instant",     # Stealth: Fast data operations
        "sage":      "llama-3.1-8b-instant",     # Ads: Analytical extraction
        "default":   "llama-3.3-70b-versatile",  # Default baseline
    }
    OPENROUTER_FREE_CHAIN = [
        "deepseek/deepseek-r1:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "google/gemini-2.0-flash-lite:free",
        "mistralai/mistral-7b-instruct:free",
        "google/gemini-2.0-flash-exp",
    ]

    # Groq fallback models (also free, very fast)
    GROQ_FREE_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile", 
    ]

    def __init__(self):
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")

        # ── PRIMARY: Groq (Ultra-fast, native function calling) ─────
        self.groq_client = None
        groq_key = cfg.groq_api_key or os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1"
                )
                logger.info("[+] Groq PRIMARY READY")
            except Exception as e:
                logger.warning(f"[-] Groq init failed: {e}")

        # ── FALLBACK 1: OpenRouter (Free models) ─────
        self.or_client = None
        api_key = cfg.openai_api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import AsyncOpenAI
                self.or_client = AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_headers={
                        "HTTP-Referer": "https://orova-nova.onrender.com",
                        "X-Title": "OROVA Nova Hub"
                    }
                )
                logger.info("[+] OpenRouter FALLBACK READY")
            except Exception as e:
                logger.warning(f"[-] OpenRouter init failed: {e}")

        # ── FALLBACK 2: MiMo/Kilo (secondary) ──────────
        self.mimo_client = None
        mimo_key = getattr(cfg, 'mimo_api_key', None) or os.getenv("MIMO_API_KEY")
        mimo_url = getattr(cfg, 'mimo_base_url', None) or os.getenv("MIMO_BASE_URL", "https://api.kilocode.ai/v1")
        if mimo_key and "INSERT" not in (mimo_key or ""):
            try:
                from openai import AsyncOpenAI
                self.mimo_client = AsyncOpenAI(
                    api_key=mimo_key,
                    base_url=mimo_url
                )
                logger.info(f"[+] MiMo FALLBACK 2 READY")
            except Exception as e:
                logger.warning(f"[-] MiMo init failed: {e}")

        # Log role → model mappings
        logger.info("🎭 Sub-Agent Model Assignments:")
        for role, model in self.AGENT_MODELS.items():
            logger.info(f"    [{role:10}] → {model}")

    # ================================================================
    #  MAIN CHAT METHOD
    # ================================================================
    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                   temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        """
        Send a chat request through Groq PRIMARY with OpenRouter/MiMo failover.

        Args:
            messages: Either a string (auto-wrapped) or List[Dict] of messages
            tools: Optional tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Max response tokens
            role: The agent ID (nova, hawk, quill, etc.) to fetch the correct Groq model.
        """

        # Auto-wrap string prompts
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        errors = []
        model = self.AGENT_MODELS.get(role, self.AGENT_MODELS["default"])

        # â”€â”€ Phase 1: Groq PRIMARY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.groq_client:
            models_to_try = [model]
            if model != "llama-3.1-8b-instant":
                models_to_try.append("llama-3.1-8b-instant")
            models_to_try.append("mixtral-8x7b-32768")
            
            groq_success = False
            for current_model in models_to_try:
                # Optimized Context Slicer for 8b Models (TPM limit 6,000)
                active_messages = messages
                if "8b-instant" in current_model:
                    char_count = sum(len(m.get("content", "")) for m in messages)
                    if char_count > 15000: # Approx 4k-5k tokens
                        logger.info(f"[!] AI ({role}): Slicing history for 8b TPM limit")
                        # Keep System Prompt + last 2 messages
                        active_messages = [messages[0]] + messages[-2:]
                
                model = current_model  # update variable for logging overrides if needed
                response = None
                for attempt in range(2):
                    try:
                        logger.info(f"[*] AI ({role}): Trying Groq ({current_model})" + (f" (retry {attempt+1})" if attempt > 0 else ""))
                        response = await self.groq_client.chat.completions.create(
                            model=model,
                            messages=messages,
                            tools=tools,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            timeout=30.0
                        )
                        if response and response.choices:
                            logger.info(f"[+] AI ({role}): Groq ({model}) responded.")
                            return response.choices[0].message
                    except Exception as e:
                        err_str = str(e)
                        logger.warning(f"[!] Groq ({current_model}) failed: {e}")
                        errors.append(f"Groq ({current_model}): {err_str}")
                        if "rate_limit_exceeded" in err_str or "quota" in err_str.lower() or "429" in err_str:
                            break  # Break retry loop, moves to the NEXT model in models_to_try
                        if attempt < 1:
                            await asyncio.sleep(0.5)
                            continue
                if response and hasattr(response, 'choices') and response.choices:
                    break
        else:
            errors.append("Groq (Skipped: GROQ_API_KEY missing or invalid in Render Envs)")

        # â”€â”€ Phase 2: GEMINI NATIVE FALLBACK â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        gemini_key = getattr(cfg, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                from openai import AsyncOpenAI
                self.gemini_client = AsyncOpenAI(
                    api_key=gemini_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                )
                logger.info(f"[*] AI ({role}): Falling back to Gemini Native")
                response = await self.gemini_client.chat.completions.create(
                    model="gemini-2.0-flash",
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=60.0
                )
                if response.choices:
                    logger.info(f"[+] AI ({role}): Gemini Native responded.")
                    return response.choices[0].message
            except Exception as e:
                err_str = str(e)
                # If 2.0 flash fails for some reason, try lite
                try:
                    logger.info(f"[*] AI ({role}): Trying gemini-2.0-flash-lite")
                    response = await self.gemini_client.chat.completions.create(
                        model="gemini-2.0-flash-lite",
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=60.0
                    )
                    if response.choices:
                        logger.info(f"[+] AI ({role}): Gemini Native Lite responded.")
                        return response.choices[0].message
                except Exception as e2:
                    errors.append(f"Gemini Native: {str(e2)}")
            else:
                errors.append(f"Gemini Native: {err_str}")
        else:
            errors.append("Gemini Native (Skipped: GEMINI_API_KEY missing)")
            if self.or_client:
                or_model = "google/gemini-2.0-flash-lite:free"
                try:
                    logger.info(f"[*] AI ({role}): Falling back to OpenRouter ({or_model})")
                    response = await self.or_client.chat.completions.create(
                        model=or_model,
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=60.0
                    )
                    if response.choices:
                        content_str = response.choices[0].message.content or ""
                        if not (content_str and content_str.strip().startswith("<")):
                            logger.info(f"[+] AI ({role}): OpenRouter responded.")
                            return response.choices[0].message
                        else:
                            logger.warning(f"[!] AI ({role}): OpenRouter returned HTML garbage.")
                            errors.append("OpenRouter: Returned HTML 404 page")
                except Exception as e:
                    err_str = str(e)
                    if "<!DOCTYPE" in err_str or "html" in err_str.lower()[:50]:
                        errors.append("OpenRouter: Cloudflare IP Block")
                    else:
                        errors.append(f"OpenRouter: {err_str}")

        # â”€â”€ Phase 3: MiMo FALLBACK 2 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.mimo_client:
            mimo_model = getattr(cfg, "mimo_model", None) or os.getenv("MIMO_MODEL", "MiMo/v2-pro")
            try:
                logger.info(f"[*] AI ({role}): MiMo fallback ({mimo_model})")
                response = await self.mimo_client.chat.completions.create(
                    model=mimo_model,
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=120.0
                )
                if response.choices:
                    content_str = response.choices[0].message.content or ""
                    # CONTENT PROTECTION: Block HTML Leaks (404 pages)
                    if content_str.strip().startswith("<"):
                        logger.warning(f"[!] AI ({role}): MiMo returned HTML garbage. Rejecting.")
                        errors.append("MiMo: Returned HTML 404 page")
                    else:
                        logger.info(f"[+] AI ({role}): MiMo responded.")
                        return response.choices[0].message
            except Exception as e:
                errors.append(f"MiMo: {str(e)}")
        
        last_error_log = " | ".join(errors)
        logger.error(f"[!!] All AI providers failed for role `{role}`. Errors: {last_error_log}")
        
        # Create a mock response block if everything fails
        from collections import namedtuple
        MockMsg = namedtuple("MockMsg", ["content", "tool_calls"])
        err_msg = f"ðŸš¨ ALL AI PROVIDERS FAILED\nRole: {role}\nDiagnostic Trace:\n- " + "\n- ".join(errors)
        return MockMsg(content=err_msg, tool_calls=None)
