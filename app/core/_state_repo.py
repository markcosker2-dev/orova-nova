"""[A-01] State repository — key/value state store operations."""
import json
import logging

logger = logging.getLogger(__name__)


class _StateRepo:
    """Mixin: state_store key/value operations."""

    @classmethod
    async def get_state(cls, key: str, default=None):
        row = await cls.fetchone("SELECT value FROM state_store WHERE key = ?", (key,))
        if row:
            try:
                return json.loads(row["value"])
            except: return row["value"]
        return default

    @classmethod
    async def set_state(cls, key: str, value):
        if not isinstance(value, str):
            value = json.dumps(value)
        await cls.query("INSERT OR REPLACE INTO state_store (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
