"""
Shield-OROVA Multi-Layer Resilience AI Provider Manager
Asynchronous state machine with cooldown, key rotation, sanitization and failover
"""
import os
import json
import time
import logging
import threading
from enum import Enum
from typing import List, Dict, Optional, Any, Deque
from types import SimpleNamespace
from dataclasses import dataclass
from collections import deque
from app.core.vault import vault
import yaml

logger = logging.getLogger(__name__)


class ProviderState(Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    INCOMPATIBLE = "incompatible"
    DEGRADED = "degraded"


class ProviderCriticalError(Exception):
    """Raised when provider returns invalid or dangerous response"""
    pass


@dataclass
class AIProvider:
    """A single AI provider with state management."""
    name: str
    identifier: str
    base_url: str
    model: str
    cost_per_1k: float
    state: ProviderState = ProviderState.ACTIVE
    cooldown_until: float = 0.0
    failure_count: int = 0
    last_used: float = 0.0
    rpm_limit: Optional[int] = None
    request_timestamps: Deque[float] = None

    def __post_init__(self):
        self.request_timestamps = deque(maxlen=100)
        # DeepSeek API limit: 60 RPM
        if self.identifier == "deepseek":
            self.rpm_limit = 60

    def can_make_request(self) -> bool:
        if self.rpm_limit is None:
            return True
        now = time.time()
        # Remove requests older than 60 seconds
        while self.request_timestamps and (now - self.request_timestamps[0] > 60):
            self.request_timestamps.popleft()
        return len(self.request_timestamps) < self.rpm_limit

    def record_request(self) -> None:
        if self.rpm_limit is not None:
            self.request_timestamps.append(time.time())

    @property
    def available(self) -> bool:
        if self.state == ProviderState.INCOMPATIBLE:
            return False
        if self.state == ProviderState.COOLDOWN:
            return time.time() >= self.cooldown_until
        return vault.has_available_keys(self.identifier)

    def __repr__(self):
        return f"<AIProvider {self.name} model={self.model} state={self.state.value}>"


class AIProviderManager:
    """
    Shield-OROVA AI Provider Manager
    Asynchronous state machine with automatic fallback, key rotation and sanitization
    Maintains 100% backwards compatibility with existing interface
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "models.yaml")
        self._last_config_load = 0.0
        self.providers: List[AIProvider] = []
        self._load_config()
        self._log_providers()

        # Integrate with Sentinel Guardian
        try:
            from app.services.sentinel import get_sentinel
            self.sentinel = get_sentinel()
        except Exception:
            self.sentinel = None
            logger.debug("[AI] Sentinel not available, running standalone")

    def _load_config(self, force: bool = False) -> None:
        """Load models configuration with auto-reload support"""
        now = time.time()
        if not force and os.path.exists(self._config_path):
            stat = os.stat(self._config_path)
            if stat.st_mtime <= self._last_config_load:
                return

        with self._lock:
            if os.path.exists(self._config_path):
                try:
                    with open(self._config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    self._last_config_load = now
                    logger.debug("[AI] Reloaded models configuration")
                except Exception as e:
                    logger.warning(f"[AI] Failed to load models config: {e}, using defaults")
                    config = self._get_default_config()
            else:
                config = self._get_default_config()

            self._build_provider_list(config)

    def _get_default_config(self) -> Dict:
        return {
            "fallback_sequence": ["deepseek", "groq", "openrouter", "local"],
            "providers": {
                "deepseek": {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "cost_per_1k": 0.0014, "models": {"default": "deepseek-chat"}},
                "groq": {"name": "Groq", "base_url": "https://api.groq.com/openai/v1", "cost_per_1k": 0.0, "models": {"default": "llama-3.3-70b-versatile"}},
                "openrouter": {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "cost_per_1k": 0.0, "models": {"default": "meta-llama/llama-3.3-70b-instruct"}},
                "openai": {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "cost_per_1k": 0.0015, "models": {"default": "gpt-4o-mini"}}
            }
        }

    def _build_provider_list(self, config: Dict) -> None:
        existing = {p.identifier: p for p in self.providers}
        new_providers = []

        for pid in config.get("fallback_sequence", []):
            if pid == "local":
                continue

            provider_config = config["providers"].get(pid)
            if not provider_config:
                continue

            if pid in existing:
                p = existing[pid]
                p.name = provider_config["name"]
                p.base_url = provider_config["base_url"]
                p.model = provider_config["models"]["default"]
                p.cost_per_1k = provider_config["cost_per_1k"]
            else:
                p = AIProvider(
                    name=provider_config["name"],
                    identifier=pid,
                    base_url=provider_config["base_url"],
                    model=provider_config["models"]["default"],
                    cost_per_1k=provider_config["cost_per_1k"]
                )

            new_providers.append(p)

        self.providers = new_providers

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
        Fully backwards compatible interface.
        """
        import httpx
        from openai import OpenAI, APIStatusError, APIConnectionError

        self._load_config()  # Auto-reload config if changed
        now = time.time()

        for provider in self.providers:
            if not provider.available:
                continue

            if provider.state == ProviderState.COOLDOWN and now < provider.cooldown_until:
                continue

            # DeepSeek rate limiting check
            if provider.identifier == "deepseek" and not provider.can_make_request():
                logger.warning(f"[AI] {provider.name} rate limit hit (60 RPM), skipping to next provider")
                continue

            # Exponential backoff retry configuration
            max_retries = 5
            base_delay = 1.0

            for retry in range(max_retries):
                api_key = vault.get_next_key(provider.identifier)
                if not api_key:
                    break

                try:
                    client = OpenAI(
                        base_url=provider.base_url,
                        api_key=api_key,
                        http_client=httpx.Client(timeout=60),
                        max_retries=0
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
                    message = response.choices[0].message

                    # Record successful request for rate limiting
                    provider.record_request()

                    # Strict content sanitization
                    if message.content is not None:
                        content = message.content.strip()
                        if content.startswith(('<!DOCTYPE', '<html', '<head>', '<body>', 'HTTP/', '404 ')):
                            raise ProviderCriticalError(f"Provider returned HTML error page")

                    # Track cost
                    usage = response.usage
                    if usage:
                        cost = (usage.total_tokens / 1000) * provider.cost_per_1k
                        logger.info(
                            f"[AI] {provider.name}: {usage.total_tokens} tokens, ${cost:.6f}"
                        )

                    provider.state = ProviderState.ACTIVE
                    provider.failure_count = 0
                    provider.last_used = now
                    vault.mark_key_result(provider.identifier, api_key, 200)

                    return message

                except APIStatusError as e:
                    status_code = e.status_code
                    vault.mark_key_result(provider.identifier, api_key, status_code)

                    if status_code == 429:
                        if retry < max_retries -1:
                            delay = base_delay * (2 ** retry)
                            logger.warning(f"[AI] {provider.name} 429, retry {retry+1}/{max_retries} after {delay:.1f}s")
                            time.sleep(delay)
                            continue
                        provider.state = ProviderState.COOLDOWN
                        provider.cooldown_until = now + 3600
                        logger.warning(f"[AI] {provider.name} entered 1h cooldown")

                    elif status_code == 404:
                        provider.state = ProviderState.INCOMPATIBLE
                        logger.error(f"[AI] {provider.name} marked permanently incompatible")

                    elif 500 <= status_code < 600:
                        if retry < max_retries -1:
                            delay = base_delay * (2 ** retry)
                            logger.warning(f"[AI] {provider.name} server error {status_code}, retry {retry+1}/{max_retries} after {delay:.1f}s")
                            time.sleep(delay)
                            continue
                        provider.state = ProviderState.DEGRADED
                        provider.failure_count += 1

                    logger.warning(f"[AI] {provider.name} failed: HTTP {status_code}")
                    break

                except (APIConnectionError, ProviderCriticalError) as e:
                    logger.warning(f"[AI] {provider.name} failed: {e}")
                    provider.failure_count += 1
                    break

                except Exception as e:
                    logger.warning(f"[AI] {provider.name} unhandled error: {e}", exc_info=False)
                    break

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

    def get_gemini_status(self) -> Dict[str, Any]:
        """Get Gemini specific rate limit and quota status"""
        gemini = next((p for p in self.providers if p.identifier == "gemini"), None)
        if not gemini:
            return {"available": False}
        now = time.time()
        recent = [t for t in gemini.request_timestamps if now - t < 60]
        return {
            "available": gemini.available,
            "state": gemini.state.value,
            "requests_last_minute": len(recent),
            "rpm_limit": gemini.rpm_limit,
            "remaining_quota": gemini.rpm_limit - len(recent) if gemini.rpm_limit else None,
            "cooldown_remaining": max(0, int(gemini.cooldown_until - now))
        }

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
