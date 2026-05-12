"""
Shield-OROVA API Key Rotation Vault
Thread-safe multi-key management per provider with automatic rotation on 429
"""
import os
import threading
import logging
from typing import List, Dict, Optional, Iterator
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class KeyStatus(Enum):
    ACTIVE = "active"
    EXHAUSTED = "exhausted"
    INVALID = "invalid"
    COOLDOWN = "cooldown"


@dataclass
class APIKey:
    value: str
    status: KeyStatus
    last_used: float = 0.0
    failure_count: int = 0
    cooldown_until: float = 0.0


class APIKeyVault:
    """
    Thread-safe API Key Rotation Vault
    Manages multiple keys per provider with automatic rotation and cooldown
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._provider_keys: Dict[str, List[APIKey]] = {}
        self._rotation_lock = threading.Lock()
        self._load_all_keys()
        self._initialized = True
        logger.info("[VAULT] API Key Vault initialized")

    def _load_all_keys(self) -> None:
        """Load all keys from environment variables with _1, _2, _3 suffix pattern"""
        providers = ["GROQ", "OPENROUTER", "GOOGLE", "DEEPSEEK", "OPENAI", "MIMO"]

        for provider in providers:
            keys = []
            index = 1

            while True:
                env_key = f"{provider}_API_KEY_{index}"
                value = os.getenv(env_key)

                if not value:
                    # Fallback to base key without suffix
                    if index == 1:
                        base_value = os.getenv(f"{provider}_API_KEY")
                        if base_value and base_value != "demo-key":
                            keys.append(APIKey(value=base_value, status=KeyStatus.ACTIVE))
                    break

                if value and value != "demo-key":
                    keys.append(APIKey(value=value, status=KeyStatus.ACTIVE))

                index += 1
                if index > 10:  # Safety limit
                    break

            self._provider_keys[provider.lower()] = keys
            logger.debug(f"[VAULT] Loaded {len(keys)} keys for {provider}")

    def get_next_key(self, provider: str) -> Optional[str]:
        """
        Get next available active key for provider.
        Thread-safe round-robin rotation.
        """
        with self._rotation_lock:
            keys = self._provider_keys.get(provider.lower(), [])
            now = getattr(__import__('time'), 'time')()

            # Reset cooldown keys if time has passed
            for key in keys:
                if key.status == KeyStatus.COOLDOWN and now >= key.cooldown_until:
                    key.status = KeyStatus.ACTIVE
                    key.failure_count = 0

            active_keys = [k for k in keys if k.status == KeyStatus.ACTIVE]
            if not active_keys:
                return None

            # Select least recently used active key
            active_keys.sort(key=lambda x: x.last_used)
            selected = active_keys[0]
            selected.last_used = now

            return selected.value

    def mark_key_result(self, provider: str, key_value: str, status_code: int) -> bool:
        """
        Mark key usage result. Returns True if rotation is recommended.
        429 = cooldown for 3600s, 401/403 = invalid, 404 = incompatible
        """
        with self._rotation_lock:
            keys = self._provider_keys.get(provider.lower(), [])
            now = getattr(__import__('time'), 'time')()

            for key in keys:
                if key.value != key_value:
                    continue

                if status_code == 429:
                    key.failure_count += 1
                    key.status = KeyStatus.COOLDOWN
                    key.cooldown_until = now + 3600
                    logger.warning(f"[VAULT] {provider} key entered cooldown until {key.cooldown_until}")
                    return True

                elif status_code in (401, 403):
                    key.status = KeyStatus.INVALID
                    logger.error(f"[VAULT] {provider} key marked invalid")
                    return True

                elif status_code == 404:
                    key.status = KeyStatus.INVALID
                    return True

                elif 200 <= status_code < 300:
                    key.failure_count = 0
                    key.status = KeyStatus.ACTIVE
                    return False

            return False

    def has_available_keys(self, provider: str) -> bool:
        """Check if provider has any active keys"""
        keys = self._provider_keys.get(provider.lower(), [])
        now = getattr(__import__('time'), 'time')()

        for key in keys:
            if key.status == KeyStatus.ACTIVE:
                return True
            if key.status == KeyStatus.COOLDOWN and now >= key.cooldown_until:
                return True

        return False

    def get_provider_status(self) -> Dict:
        """Get status of all provider keys"""
        result = {}
        for provider, keys in self._provider_keys.items():
            active = sum(1 for k in keys if k.status == KeyStatus.ACTIVE)
            result[provider] = {
                "total": len(keys),
                "active": active,
                "cooldown": sum(1 for k in keys if k.status == KeyStatus.COOLDOWN),
                "invalid": sum(1 for k in keys if k.status == KeyStatus.INVALID)
            }
        return result


# Global singleton
vault = APIKeyVault()
