import os
import logging
import asyncio
import json
import re
import time
import uuid
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
    "meta-llama/llama-3.3-70b-instruct:free": (0.0, 0.0), # Free tier
    "qwen/qwen3-next-80b-a3b-instruct:free": (0.0, 0.0), # Free tier
    "qwen/qwen3-coder:free": (0.0, 0.0), # Free tier
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
    if b["open_until"] > 0:
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


def _err_status(e: Exception):
    """HTTP status from an SDK exception, if it carries one."""
    return getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)


def _err_body(e: Exception) -> str:
    """Provider response body (or str(e)) — the part that says WHY."""
    body = getattr(e, "body", None)
    return str(body if body else e)[:500]


def _tc_read(tc, *path, default=None):
    """Read a nested field from a tool call that may be a dict, an OpenAI SDK
    object, or a SimpleNamespace — message history carries all three."""
    node = tc
    for key in path:
        if isinstance(node, dict):
            node = node.get(key)
        else:
            node = getattr(node, key, None)
        if node is None:
            return default
    return node

class UnifiedAIClient:
    """
    Unified AI Client — Groq primary, Gemini secondary, OpenRouter tertiary.
    """

    FLAVORS = {
        "fast":   "meta-llama/llama-3.3-70b-instruct:free",
        "smart":  "qwen/qwen3-next-80b-a3b-instruct:free",
        "genius": "qwen/qwen3-coder:free",
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

    ROLE_MODELS = {
        "default":   "meta-llama/llama-3.3-70b-instruct:free",
        "nova":      "meta-llama/llama-3.3-70b-instruct:free",
    }

    FALLBACK_CHAIN = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-next-80b-a3b-instruct:free",
        "qwen/qwen3-coder:free",
    ]

    GROQ_MODEL = "llama-3.3-70b-versatile"

    def __init__(self):
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")

        # ─── GROQ CLIENT (Primary — OpenAI-compatible, supports tool calling) ──
        self.groq_client = None
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                from openai import AsyncOpenAI
                self.groq_client = AsyncOpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
                logger.info("[+] Groq AI Client — READY")
            except Exception as e:
                logger.warning(f"[-] Groq init failed: {e}")

        # ─── NATIVE GEMINI CLIENT (Secondary / Free) ──
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

        # ─── OPENROUTER (Tertiary fallback) ──
        self.primary_client = None
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
        if api_key:
            try:
                from openai import AsyncOpenAI
                self.primary_client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    default_headers={
                        "HTTP-Referer": "https://orova.ai",
                        "X-Title": "OROVA",
                    }
                )
                logger.info(f"[+] Primary AI Client (OpenRouter) — READY")
            except Exception as e:
                logger.warning(f"[-] Primary AI init failed: {e}")

    async def chat(self, messages, tools: Optional[List[Dict]] = None,
                   tool_choice: Optional[str] = None,
                   temperature=0.7, max_tokens=2000, role: str = "default") -> Any:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        # Per-request failure ledger: every tier that fails (or is skipped)
        # leaves a structured record, so the terminal error can always say WHY.
        request_id = uuid.uuid4().hex[:8]
        failures: List[Dict] = []

        def _record_provider_failure(provider: str, model: str, exc: Optional[Exception],
                                     detail: str = "", log_stack: bool = True):
            rec = {
                "request_id": request_id, "role": role,
                "provider": provider, "model": model,
                "status": _err_status(exc) if exc else None,
                "error": type(exc).__name__ if exc else "Skipped",
                "detail": (detail or (_err_body(exc) if exc else ""))[:500],
            }
            failures.append(rec)
            logger.error("[AI-FAIL] %s", json.dumps(rec, default=str),
                         exc_info=exc if log_stack and exc else None)

        if not self.groq_client and not self.google_client and not self.primary_client:
            logger.error(f"[AI-FAIL {request_id}] No AI providers configured "
                         f"(GROQ_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY all missing or failed init)")
            return SimpleNamespace(
                content="[!!] No AI providers available — no provider API key is configured or all failed init. "
                        "Check GROQ_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY.",
                tool_calls=None)

        # ─── TIER 1: Groq (Primary — full tool support, free tier available) ───
        # Breaker: live 2026-07-20, worker lanes hammered a 429'd Groq+Gemini
        # once per second — the breaker (already guarding Tier 3) now covers
        # Tiers 1-2 so quota exhaustion fails fast for the cooldown instead.
        if self.groq_client and _is_open("groq"):
            _record_provider_failure("groq", self.GROQ_MODEL, None,
                                     detail="circuit breaker open — skipped", log_stack=False)
        elif self.groq_client:
            # 'tool_use_failed' 400s are the model emitting args that violate a
            # tool schema (live 2026-07-19: morning_brief client_id="OROVA" vs
            # integer) — a bad generation, not an outage, so one retry is cheap
            # and usually lands.
            for groq_attempt in (1, 2):
                try:
                    groq_kwargs = {
                        "model": self.GROQ_MODEL, "messages": messages,
                        "temperature": temperature, "max_tokens": max_tokens, "timeout": 60.0,
                    }
                    if tools:
                        groq_kwargs["tools"] = tools
                        groq_kwargs["tool_choice"] = tool_choice or "auto"
                        logger.info(f"[*] Groq ({role}) req={request_id}: Querying with {len(tools)} tools")
                    else:
                        logger.info(f"[*] Groq ({role}) req={request_id}: Querying (text-only)")

                    response = await self.groq_client.chat.completions.create(**groq_kwargs)
                    if response.choices:
                        _record_success("groq")
                        msg = response.choices[0].message
                        if msg.tool_calls:
                            logger.info(f"[+] Groq ({role}): OK with {len(msg.tool_calls)} tool call(s)")
                            return msg
                        if not tools:
                            logger.info(f"[+] Groq ({role}): OK (text)")
                            return msg
                        logger.warning(f"[!] Groq ({role}): text when tools available — reprompting")
                        return GroqLimpResponse(content=msg.content)
                    _record_provider_failure("groq", self.GROQ_MODEL, None,
                                             detail="empty choices in response", log_stack=False)
                    break
                except Exception as e:
                    if groq_attempt == 1 and "tool_use_failed" in _err_body(e):
                        logger.warning(f"[!] Groq ({role}) req={request_id}: model emitted "
                                       f"schema-invalid tool args — retrying once. {_err_body(e)[:200]}")
                        continue
                    _record_failure("groq")
                    _record_provider_failure("groq", self.GROQ_MODEL, e)
                    break
        else:
            _record_provider_failure("groq", self.GROQ_MODEL, None,
                                     detail="not configured (GROQ_API_KEY missing or init failed)",
                                     log_stack=False)

        # ─── TIER 2: Native Google Gemini (Free, with proper conversation format) ───
        gemini_model_name = "gemini-2.5-flash" if tools else "gemini-2.5-flash-lite"
        if self.google_client and _is_open("gemini"):
            _record_provider_failure("gemini", gemini_model_name, None,
                                     detail="circuit breaker open — skipped", log_stack=False)
        elif self.google_client:
            try:
                logger.info(f"[*] Gemini ({role}) req={request_id}: Querying...")
                system_instruction = ""
                contents = self._convert_messages_to_gemini(messages)

                for msg in messages:
                    if msg.get("role") == "system":
                        system_instruction = msg.get("content", "")
                        break

                gen_config = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens
                }

                model = self.google_client.GenerativeModel(
                    model_name=gemini_model_name,
                    system_instruction=system_instruction if system_instruction else None
                )

                gemini_tools = None
                if tools:
                    gemini_tools = self._convert_tools_to_gemini(tools)

                loop = asyncio.get_running_loop()
                gen_kwargs = {"contents": contents, "generation_config": gen_config}
                if gemini_tools:
                    gen_kwargs["tools"] = gemini_tools

                response = await loop.run_in_executor(
                    None,
                    lambda: model.generate_content(**gen_kwargs)
                )

                if response:
                    tool_calls = None
                    text = response.text if response.text else ""

                    if (hasattr(response, "candidates") and response.candidates and
                        response.candidates[0].content.parts and
                        any(hasattr(p, "function_call") and p.function_call
                            for p in response.candidates[0].content.parts)):
                        tool_calls = []
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, "function_call") and part.function_call:
                                fc = part.function_call
                                args = dict(fc.args) if fc.args else {}
                                tool_calls.append(SimpleNamespace(
                                    id=f"gemini_{fc.name}_{int(time.time()*1000)}",
                                    type="function",
                                    function=SimpleNamespace(
                                        name=fc.name,
                                        arguments=json.dumps(args)
                                    )
                                ))
                        logger.info(f"[+] Gemini ({role}): OK with {len(tool_calls)} tool call(s)")
                    else:
                        # Text fallback: parse text for tool calls if tools were provided
                        if text and tools:
                            parsed = self._extract_tool_calls_from_text(text, tools)
                            if parsed:
                                tool_calls = parsed
                                text = ""
                                logger.info(f"[+] Gemini ({role}): text parsed -> {len(tool_calls)} tool call(s)")

                    if text or tool_calls:
                        _record_success("gemini")
                        return SimpleNamespace(content=text, tool_calls=tool_calls)
                    _record_provider_failure("gemini", gemini_model_name, None,
                                             detail="empty response (no text, no tool calls)",
                                             log_stack=False)
            except Exception as e:
                _record_failure("gemini")
                _record_provider_failure("gemini", gemini_model_name, e)
        else:
            _record_provider_failure("gemini", gemini_model_name, None,
                                     detail="not configured (GOOGLE_API_KEY missing or init failed)",
                                     log_stack=False)

        # ─── TIER 3: OpenRouter (Tertiary) ───
        if self.primary_client:
            primary_model = self.ROLE_MODELS.get(role, self.ROLE_MODELS["default"])
            chain = [primary_model] + [m for m in self.FALLBACK_CHAIN if m != primary_model]

            for attempt, model_name in enumerate(chain):
                if _is_open(model_name):
                    logger.info(f"[BREAKER] Skipping {model_name} — circuit open")
                    _record_provider_failure("openrouter", model_name, None,
                                             detail="circuit breaker open — skipped", log_stack=False)
                    continue
                try:
                    logger.info(f"[*] OpenRouter ({role}) req={request_id}: Trying {model_name}")
                    kwargs = {
                        "model": model_name, "messages": messages, "tools": tools,
                        "temperature": temperature, "max_tokens": max_tokens, "timeout": 60.0
                    }
                    if tool_choice: kwargs["tool_choice"] = tool_choice

                    response = await self.primary_client.chat.completions.create(**kwargs)
                    if response.choices:
                        _record_success(model_name)
                        logger.info(f"[+] OpenRouter ({role}): {model_name} OK")
                        return response.choices[0].message
                    _record_provider_failure("openrouter", model_name, None,
                                             detail="empty choices in response", log_stack=False)
                except Exception as e:
                    _record_failure(model_name)
                    _record_provider_failure("openrouter", model_name, e)
                    if any(kw in _err_body(e).lower() for kw in ("credit", "quota", "balance", "429", "rate")):
                        logger.warning(f"[!] Rate limit on {model_name}. Backing off...")
                        await _backoff(attempt)
                    continue
        else:
            _record_provider_failure("openrouter", "-", None,
                                     detail="not configured (OPENROUTER_API_KEY missing or init failed)",
                                     log_stack=False)

        # Terminal failure: every tier left a record above. Summarize per
        # provider for the user-facing message; the full ledger is in the logs
        # under [AI-FAIL] with this request_id.
        reasons = "; ".join(
            f"{f['provider']}" + (f"[{f['model']}]" if f.get("model") not in (None, "-") else "") +
            f": {f['error']}" + (f" HTTP {f['status']}" if f.get("status") else "") +
            (f" — {f['detail'][:120]}" if f.get("detail") else "")
            for f in failures
        ) or "no failure records (bug — report this)"
        logger.error(f"[AI-FAIL {request_id}] ALL providers failed for role '{role}': "
                     f"{json.dumps(failures, default=str)[:2000]}")
        return SimpleNamespace(
            content=f"[!!] All AI providers failed for role '{role}' (req {request_id}). {reasons}",
            tool_calls=None
        )

    def _convert_messages_to_gemini(self, messages: list) -> list:
        """Convert OpenAI-format messages to Gemini-format contents.
        
        Handles system, user, assistant (with tool_calls), and tool responses
        properly for multi-turn tool-using conversations.
        """
        contents = []
        for msg in messages:
            role = msg.get("role", "")
            if role == "system":
                continue  # handled separately as system_instruction
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": msg.get("content", "")}]
                })
            elif role == "assistant":
                parts = []
                content = msg.get("content", "")
                if content:
                    parts.append({"text": content})
                # tool_calls may be dicts, OpenAI SDK objects, or SimpleNamespace
                # (Groq returns SDK objects; assuming dicts crashed the whole
                # Gemini tier with "'ChatCompletionMessageToolCall' object has
                # no attribute 'get'", live 2026-07-19).
                for tc in (msg.get("tool_calls") or []):
                    try:
                        name = _tc_read(tc, "function", "name")
                        if not name:
                            continue
                        args = _tc_read(tc, "function", "arguments", default="{}")
                        if isinstance(args, str):
                            args = json.loads(args) if args.strip() else {}
                        if not isinstance(args, dict):
                            args = {}
                        parts.append({
                            "function_call": {
                                "name": name,
                                "args": args
                            }
                        })
                    except (json.JSONDecodeError, KeyError):
                        continue
                if parts:
                    contents.append({"role": "model", "parts": parts})
            elif role == "tool":
                # Gemini wants function_response in a user-part message
                # Find the name of the function that was called
                tc_id = msg.get("tool_call_id", "")
                name = self._find_tool_name_from_id(tc_id, messages) or "unknown"
                contents.append({
                    "role": "function",
                    "parts": [{
                        "function_response": {
                            "name": name,
                            "response": {"result": msg.get("content", "")}
                        }
                    }]
                })
        return contents

    def _find_tool_name_from_id(self, tool_call_id: str, messages: list) -> str:
        """Look backwards through messages to find the tool call name by ID.
        Tool calls may be dicts or SDK objects — read defensively."""
        for msg in reversed(messages):
            tool_calls = (msg.get("tool_calls") if isinstance(msg, dict)
                          else getattr(msg, "tool_calls", None)) or []
            for tc in tool_calls:
                if _tc_read(tc, "id") == tool_call_id:
                    return _tc_read(tc, "function", "name", default="")
        return ""

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

    @staticmethod
    def _strip_openai_only_schema_fields(node):
        """Remove JSON-Schema fields Gemini's Schema proto rejects.

        OpenAI strict-mode tools carry `additionalProperties` (and we mark
        `strict` on some); Gemini fails the WHOLE request with 'Unknown field
        for Schema: additionalProperties' — which took out the tier-2 fallback
        exactly when Groq 400'd (live 2026-07-15). Strips recursively; returns
        a cleaned copy, never mutates the shared TOOLS definitions."""
        _BANNED = {"additionalProperties", "strict", "$schema", "minLength",
                   "maxLength", "pattern", "default", "examples"}
        if isinstance(node, dict):
            return {k: UnifiedAIClient._strip_openai_only_schema_fields(v)
                    for k, v in node.items() if k not in _BANNED}
        if isinstance(node, list):
            return [UnifiedAIClient._strip_openai_only_schema_fields(v) for v in node]
        return node

    def _convert_tools_to_gemini(self, tools: List[Dict]) -> List:
        """Convert OpenAI-style tool definitions to Gemini function calling format.
        Returns a single function_declarations array containing all tools, as Gemini expects."""
        declarations = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                func = tool["function"]
                declarations.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": self._strip_openai_only_schema_fields(func.get("parameters", {}))
                })
        return [{"function_declarations": declarations}] if declarations else None

    def _extract_tool_calls_from_text(self, text: str, tools: List[Dict]) -> Optional[List]:
        """Parse text responses that name tool calls instead of using function calling."""
        tool_names = {t["function"]["name"] for t in tools if t.get("function")}
        found_calls = []

        json_pat = re.compile(r'```(?:json)?\s*\{\s*"tool"\s*:\s*"(\w+)"', re.IGNORECASE)
        for match in json_pat.finditer(text):
            name = match.group(1)
            if name in tool_names:
                block_start = text.find("{", match.start())
                if block_start >= 0:
                    depth, end = 1, block_start
                    for i in range(block_start + 1, len(text)):
                        if text[i] == "{": depth += 1
                        elif text[i] == "}":
                            depth -= 1
                            if depth == 0: end = i + 1; break
                    if end > block_start:
                        try:
                            block = json.loads(text[block_start:end])
                            args = block.get("arguments", block.get("args", block.get("parameters", {})))
                            if isinstance(args, dict):
                                found_calls.append(SimpleNamespace(
                                    id=f"gemini_ext_{name}_{int(time.time()*1000)}",
                                    type="function",
                                    function=SimpleNamespace(name=name, arguments=json.dumps(args))
                                ))
                                continue
                        except Exception: pass

        if not found_calls:
            for name in tool_names:
                if re.search(rf'\b(?:using|calling|running|execute|run)\b.*?\b{re.escape(name)}\b', text, re.IGNORECASE):
                    found_calls.append(SimpleNamespace(
                        id=f"gemini_txt_{name}_{int(time.time()*1000)}",
                        type="function",
                        function=SimpleNamespace(name=name, arguments="{}")
                    ))
                elif re.search(rf'\b{re.escape(name)}\b.*?\btool\b', text, re.IGNORECASE):
                    found_calls.append(SimpleNamespace(
                        id=f"gemini_txt_{name}_{int(time.time()*1000)}",
                        type="function",
                        function=SimpleNamespace(name=name, arguments="{}")
                    ))

        return found_calls if found_calls else None

    async def _send_alert(self, msg: str):
        if not self.tg_token or not self.admin_chat_id:
            return
        try:
            import httpx
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            async with httpx.AsyncClient() as client:
                await client.post(url, json={"chat_id": self.admin_chat_id, "text": msg}, timeout=5.0)
        except Exception: pass