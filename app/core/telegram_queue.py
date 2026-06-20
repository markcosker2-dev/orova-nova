import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Awaitable, Optional

import httpx

logger = logging.getLogger(__name__)

# ── Dead-letter storage ─────────────────────────────────────
_DLQ_DIR = Path(os.getenv("DLQ_DIR", "data/traces/dlq"))
_MAX_RETRIES = 3
_BASE_BACKOFF = 2.0  # seconds, doubles each retry


def _write_dlq(chat_id: int, text: str, error: str, attempt: int) -> None:
    """Persist a permanently failed message to disk for later recovery."""
    _DLQ_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "chat_id": chat_id,
        "text": text[:4096],
        "error": str(error),
        "attempt": attempt,
        "ts": time.time(),
    }
    fname = _DLQ_DIR / f"dlq_{chat_id}_{int(time.time())}.json"
    try:
        fname.write_text(json.dumps(entry, default=str, ensure_ascii=False))
    except Exception as exc:
        logger.error(f"[DLQ] Failed to write dead-letter file: {exc}")


class TelegramQueue:
    """
    [P2] Bounded Async Queue + Single Worker.
    Ensures Render (512MB RAM) isn't overwhelmed by concurrent AI calls.
    Serialized processing: One message at a time.

    [R-04] Dead-letter queue: failed messages are retried with
    exponential backoff up to _MAX_RETRIES, then persisted to disk.
    """
    def __init__(self, maxsize: int = 50):
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._worker_task: Optional[asyncio.Task] = None
        self._handler: Optional[Callable[[dict], Awaitable[None]]] = None

    async def start(self, handler: Callable[[dict], Awaitable[None]]):
        self._handler = handler
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"📥 Telegram Bounded Queue started (maxsize={self._q.maxsize})")

    async def add_message(self, chat_id: int, text: str, parse_mode: Optional[str] = None) -> bool:
        """Send an outgoing Telegram message via the Bot API.

        Retries with exponential backoff up to _MAX_RETRIES.
        Permanently failed messages are written to the dead-letter queue.
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("[TelegramQueue] Cannot send message: TELEGRAM_BOT_TOKEN missing.")
            _write_dlq(chat_id, text, "TELEGRAM_BOT_TOKEN missing", attempt=0)
            return False

        payload = {"chat_id": chat_id, "text": text[:4096]}
        if parse_mode:
            payload["parse_mode"] = parse_mode

        last_error = ""
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    res = await client.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json=payload,
                    )
                if res.status_code == 200:
                    return True
                last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                logger.error(f"[TelegramQueue] Send failed (attempt {attempt+1}/{_MAX_RETRIES}): {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.error(f"[TelegramQueue] Send exception (attempt {attempt+1}/{_MAX_RETRIES}): {e}")

            # Exponential backoff: 2s, 4s, 8s …
            backoff = _BASE_BACKOFF * (2 ** attempt)
            await asyncio.sleep(backoff)

        # All retries exhausted → dead-letter
        logger.error(f"[TelegramQueue] All {_MAX_RETRIES} attempts failed for chat_id={chat_id}. Writing to DLQ.")
        _write_dlq(chat_id, text, last_error, attempt=_MAX_RETRIES)
        return False

    async def stop(self):
        await self._q.join()
        if self._worker_task:
            self._worker_task.cancel()
        logger.info("🛑 Telegram Bounded Queue stopped.")

    async def enqueue(self, data: dict) -> bool:
        """Returns False (backpressure) if queue is full."""
        try:
            self._q.put_nowait(data)
            return True
        except asyncio.QueueFull:
            logger.warning("⚠️ Telegram Queue FULL. Applying backpressure.")
            return False

    async def _worker(self):
        """Single serialized consumer — one AI call in flight at a time."""
        while True:
            data = await self._q.get()
            try:
                if self._handler:
                    await self._handler(data)
            except Exception as e:
                logger.error(f"[TG_QUEUE] Worker error: {e}", exc_info=True)
                # Persist the failed inbound message to DLQ for recovery
                chat_id = data.get("message", {}).get("chat", {}).get("id", "unknown")
                text = data.get("message", {}).get("text", str(data)[:500])
                _write_dlq(chat_id, text, f"Worker error: {e}", attempt=0)
            finally:
                self._q.task_done()

# Global instance
tg_queue = TelegramQueue(maxsize=50)
