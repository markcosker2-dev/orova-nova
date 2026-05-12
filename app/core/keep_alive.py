"""
OROVA Nova — Keep-Alive Ping
Pings your own health endpoint every 10 minutes to prevent HF Spaces from sleeping.
Add this to your main.py startup if deploying to Hugging Face Spaces.
"""
import os
import threading
import time
import logging

logger = logging.getLogger(__name__)


def keep_alive_ping(url: str = None, interval: int = 600):
    """Ping a URL every N seconds to keep the service awake."""
    if not url:
        space_id = os.getenv("SPACE_ID")
        if space_id:
            user_name = space_id.replace("/", "-").lower()
            url = f"https://{user_name}.hf.space/health"
        else:
            return

    def _ping():
        while True:
            try:
                import requests
                requests.get(url, timeout=10)
                logger.debug(f"[KEEP-ALIVE] Pinged {url}")
            except Exception:
                pass
            time.sleep(interval)

    thread = threading.Thread(target=_ping, daemon=True)
    thread.start()
    logger.info(f"[KEEP-ALIVE] Pinging every {interval}s: {url}")
