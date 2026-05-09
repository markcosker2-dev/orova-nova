import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

class TelegramQueue:
    """
    [P2] Bounded Async Queue + Single Worker.
    Ensures Render (512MB RAM) isn't overwhelmed by concurrent AI calls.
    Serialized processing: One message at a time.
    """
    def __init__(self, maxsize: int = 50):
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._worker_task: asyncio.Task | None = None
        self._handler: Callable[[dict], Awaitable[None]] | None = None

    async def start(self, handler: Callable[[dict], Awaitable[None]]):
        self._handler = handler
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"📥 Telegram Bounded Queue started (maxsize={self._q.maxsize})")

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
            finally:
                self._q.task_done()

# Global instance
tg_queue = TelegramQueue(maxsize=50)
