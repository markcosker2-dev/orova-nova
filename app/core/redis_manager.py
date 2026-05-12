import os
import json
import logging
import redis
from typing import Dict, List, Optional, Any
import time

logger = logging.getLogger(__name__)


class FreeRedisManager:
    """
    FREE Upstash Redis Manager — 100% FREE DATABASE

    Features:
    - Upstash Redis: 500K commands/month, 256MB storage (FREE)
    - Automatic data compression for memory efficiency
    - TTL-based cleanup for temporary data
    - Parallel-safe operations
    - Automatic reconnection handling

    Data Structure:
    - leads:{client_id} — Hash of lead data
    - metrics:{client_id} — Hash of metrics
    - tasks:{client_id} — List of tasks
    - content:{client_id} — List of content items
    - memories:{client_id} — List of memories
    - chat:{client_id}:{session_id} — Chat history
    """

    def __init__(self):
        self.redis_url = os.getenv("UPSTASH_REDIS_URL")
        self.redis_token = os.getenv("UPSTASH_REDIS_TOKEN")

        if not self.redis_url or not self.redis_token:
            logger.warning("⚠️  Upstash Redis not configured. Using in-memory fallback.")
            self.client = None
            self.memory_store = {}  # Fallback in-memory store
        else:
            try:
                self.client = redis.from_url(
                    self.redis_url,
                    password=self.redis_token,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    max_connections=10
                )
                # Test connection
                self.client.ping()
                logger.info("✅ Upstash Redis connected (FREE TIER)")
            except Exception as e:
                logger.error(f"❌ Upstash Redis connection failed: {e}")
                self.client = None
                self.memory_store = {}

        # Memory management settings
        self.memory_limits = {
            "max_keys_per_namespace": 1000,
            "ttl_seconds": 86400 * 30,  # 30 days
            "cleanup_interval": 3600,  # Clean every hour
        }

        # Compression for large data
        self.enable_compression = True

    # ── CORE REDIS OPERATIONS ─────────────────────────────────────

    def _redis_op(self, operation: str, *args, **kwargs):
        """Safe Redis operation with fallback to memory store."""
        if self.client:
            try:
                return getattr(self.client, operation)(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Redis {operation} failed: {e}")
                return self._memory_fallback(operation, *args, **kwargs)
        else:
            return self._memory_fallback(operation, *args, **kwargs)

    def _memory_fallback(self, operation: str, *args, **kwargs):
        """In-memory fallback for when Redis is unavailable."""
        if operation == "hget":
            key, field = args
            return self.memory_store.get(key, {}).get(field)
        elif operation == "hgetall":
            key = args[0]
            return self.memory_store.get(key, {})
        elif operation == "hset":
            key, field, value = args
            if key not in self.memory_store:
                self.memory_store[key] = {}
            self.memory_store[key][field] = value
            return 1
        elif operation == "lrange":
            key, start, end = args
            lst = self.memory_store.get(key, [])
            return lst[start:end+1] if end != -1 else lst[start:]
        elif operation == "lpush":
            key, *values = args
            if key not in self.memory_store:
                self.memory_store[key] = []
            self.memory_store[key].extend(reversed(values))
            return len(self.memory_store[key])
        elif operation == "ltrim":
            key, start, end = args
            if key in self.memory_store:
                self.memory_store[key] = self.memory_store[key][start:end+1]
        elif operation == "delete":
            key = args[0]
            return 1 if self.memory_store.pop(key, None) is not None else 0
        elif operation == "exists":
            key = args[0]
            return 1 if key in self.memory_store else 0
        return None

    # ── DATA COMPRESSION ──────────────────────────────────────────

    def _compress_data(self, data: Any) -> str:
        """Compress large data structures."""
        if not self.enable_compression:
            return json.dumps(data)

        json_str = json.dumps(data, separators=(',', ':'))
        if len(json_str) > 1000:  # Only compress large data
            import gzip
            import base64
            compressed = gzip.compress(json_str.encode())
            return f"COMPRESSED:{base64.b64encode(compressed).decode()}"
        return json_str

    def _decompress_data(self, data: str) -> Any:
        """Decompress data if needed."""
        if data.startswith("COMPRESSED:"):
            import gzip
            import base64
            compressed_data = base64.b64decode(data[11:])
            json_str = gzip.decompress(compressed_data).decode()
            return json.loads(json_str)
        return json.loads(data)

    # ── LEADS MANAGEMENT ──────────────────────────────────────────

    def save_lead(self, lead_data: Dict, client_id: int = 0) -> None:
        """Save a lead with deduplication."""
        business = lead_data.get("business") or lead_data.get("company") or lead_data.get("title", "")
        url = lead_data.get("url", "")

        # Deduplication
        if url:
            existing = self.get_lead_by_url(url, client_id)
            if existing:
                logger.info(f"[REDIS] Duplicate lead skipped (URL): {url}")
                return

        if business:
            existing = self.get_lead_by_business(business, client_id)
            if existing:
                logger.info(f"[REDIS] Duplicate lead skipped (business): {business}")
                return

        # Create lead key
        lead_id = f"{int(time.time())}_{hash(business) % 10000}"
        lead_key = f"leads:{client_id}:{lead_id}"

        # Prepare lead data
        lead_data["id"] = lead_id
        lead_data["client_id"] = client_id
        lead_data["created_at"] = time.time()

        # Save to Redis hash
        for field, value in lead_data.items():
            if value is not None:
                self._redis_op("hset", lead_key, field, self._compress_data(value) if isinstance(value, (dict, list)) else str(value))

        # Set TTL
        self._redis_op("expire", lead_key, self.memory_limits["ttl_seconds"])

        # Add to leads index
        index_key = f"leads_index:{client_id}"
        self._redis_op("lpush", index_key, lead_id)
        self._redis_op("ltrim", index_key, 0, self.memory_limits["max_keys_per_namespace"] - 1)
        self._redis_op("expire", index_key, self.memory_limits["ttl_seconds"])

        logger.info(f"[REDIS] Lead saved: {business} (ID: {lead_id})")

    def get_leads(self, client_id: int = 0) -> List[Dict]:
        """Get all leads for a client."""
        index_key = f"leads_index:{client_id}"
        lead_ids = self._redis_op("lrange", index_key, 0, -1) or []

        leads = []
        for lead_id in lead_ids:
            lead_key = f"leads:{client_id}:{lead_id}"
            lead_data = self._redis_op("hgetall", lead_key)
            if lead_data:
                # Parse data
                parsed_lead = {}
                for field, value in lead_data.items():
                    try:
                        if field in ["score", "client_id"]:
                            parsed_lead[field] = int(value)
                        elif field == "created_at":
                            parsed_lead[field] = float(value)
                        else:
                            parsed_lead[field] = self._decompress_data(value) if value.startswith("{") or value.startswith("[") else value
                    except:
                        parsed_lead[field] = value
                leads.append(parsed_lead)

        return leads

    def get_lead_by_url(self, url: str, client_id: int = 0) -> Optional[Dict]:
        """Find lead by URL."""
        leads = self.get_leads(client_id)
        for lead in leads:
            if lead.get("url") == url:
                return lead
        return None

    def get_lead_by_business(self, business: str, client_id: int = 0) -> Optional[Dict]:
        """Find lead by business name."""
        leads = self.get_leads(client_id)
        for lead in leads:
            if lead.get("business", "").lower() == business.lower():
                return lead
        return None

    # ── METRICS MANAGEMENT ────────────────────────────────────────

    def get_metrics(self, client_id: int = 0) -> Dict:
        """Get metrics for a client."""
        metrics_key = f"metrics:{client_id}"
        metrics_data = self._redis_op("hgetall", metrics_key) or {}

        # Parse numeric values
        parsed = {}
        for key, value in metrics_data.items():
            try:
                parsed[key] = int(value)
            except:
                parsed[key] = 0

        # Default metrics
        defaults = {
            "leads_found": 0,
            "emails_sent": 0,
            "replies_received": 0,
            "meetings_booked": 0,
            "calls_made": 0,
            "proposals_sent": 0
        }

        return {**defaults, **parsed}

    def update_metrics(self, data: Dict, client_id: int = 0) -> None:
        """Update metrics (merge, not overwrite)."""
        if not data:
            return

        metrics_key = f"metrics:{client_id}"
        for key, value in data.items():
            if isinstance(value, (int, float)):
                self._redis_op("hset", metrics_key, key, str(int(value)))

        self._redis_op("expire", metrics_key, self.memory_limits["ttl_seconds"])

    # ── TASKS MANAGEMENT ──────────────────────────────────────────

    def get_tasks(self, client_id: int = 0) -> List[Dict]:
        """Get all tasks for a client."""
        tasks_key = f"tasks:{client_id}"
        tasks_json = self._redis_op("lrange", tasks_key, 0, -1) or []

        tasks = []
        for task_json in tasks_json:
            try:
                tasks.append(self._decompress_data(task_json))
            except:
                continue

        return tasks

    def save_task(self, task_data: Dict, client_id: int = 0) -> None:
        """Save a task."""
        tasks_key = f"tasks:{client_id}"
        task_json = self._compress_data(task_data)
        self._redis_op("lpush", tasks_key, task_json)
        self._redis_op("ltrim", tasks_key, 0, self.memory_limits["max_keys_per_namespace"] - 1)
        self._redis_op("expire", tasks_key, self.memory_limits["ttl_seconds"])

    # ── CONTENT MANAGEMENT ────────────────────────────────────────

    def get_content(self, client_id: int = 0) -> List[Dict]:
        """Get all content for a client."""
        content_key = f"content:{client_id}"
        content_json = self._redis_op("lrange", content_key, 0, -1) or []

        content = []
        for item_json in content_json:
            try:
                content.append(self._decompress_data(item_json))
            except:
                continue

        return content

    def save_content(self, content_data: Dict, client_id: int = 0) -> None:
        """Save content."""
        content_key = f"content:{client_id}"
        content_json = self._compress_data(content_data)
        self._redis_op("lpush", content_key, content_json)
        self._redis_op("ltrim", content_key, 0, self.memory_limits["max_keys_per_namespace"] - 1)
        self._redis_op("expire", content_key, self.memory_limits["ttl_seconds"])

    # ── MEMORIES MANAGEMENT ───────────────────────────────────────

    def get_memories(self, client_id: int = 0) -> List[Dict]:
        """Get all memories for a client."""
        memories_key = f"memories:{client_id}"
        memories_json = self._redis_op("lrange", memories_key, 0, -1) or []

        memories = []
        for memory_json in memories_json:
            try:
                memories.append(self._decompress_data(memory_json))
            except:
                continue

        return memories

    def save_memory(self, memory_data: Dict, client_id: int = 0) -> None:
        """Save a memory."""
        memories_key = f"memories:{client_id}"
        memory_json = self._compress_data(memory_data)
        self._redis_op("lpush", memories_key, memory_json)
        self._redis_op("ltrim", memories_key, 0, self.memory_limits["max_keys_per_namespace"] - 1)
        self._redis_op("expire", memories_key, self.memory_limits["ttl_seconds"])

    # ── CHAT HISTORY MANAGEMENT ───────────────────────────────────

    def get_chat_history(self, client_id: int = 0, session_id: str = "default") -> List[Dict]:
        """Get chat history for a session."""
        chat_key = f"chat:{client_id}:{session_id}"
        messages_json = self._redis_op("lrange", chat_key, 0, -1) or []

        messages = []
        for msg_json in messages_json:
            try:
                messages.append(self._decompress_data(msg_json))
            except:
                continue

        return messages

    def save_chat_message(self, message: Dict, client_id: int = 0, session_id: str = "default") -> None:
        """Save a chat message."""
        chat_key = f"chat:{client_id}:{session_id}"
        message_json = self._compress_data(message)
        self._redis_op("lpush", chat_key, message_json)
        self._redis_op("ltrim", chat_key, 0, self.memory_limits["max_messages"] - 1)
        self._redis_op("expire", chat_key, self.memory_limits["ttl_seconds"])

    # ── UTILITY METHODS ───────────────────────────────────────────

    def cleanup_expired_data(self) -> None:
        """Clean up expired data (called periodically)."""
        logger.info("[REDIS] Running memory cleanup...")
        # Redis automatically expires data with TTL, but we can add custom cleanup here
        pass

    def get_stats(self) -> Dict:
        """Get Redis usage statistics."""
        if self.client:
            try:
                info = self.client.info()
                return {
                    "connected": True,
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "uptime_days": info.get("uptime_in_days", 0)
                }
            except:
                pass

        return {
            "connected": False,
            "fallback_mode": True,
            "keys_in_memory": len(self.memory_store)
        }


# Global instance
redis_manager = FreeRedisManager()