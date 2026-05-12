import os
import time
import logging
import requests
from threading import Thread

logger = logging.getLogger(__name__)

def ping_self(url: str, interval: int = 600):
    """
    Pings the provided URL every 'interval' seconds to keep a Hugging Face Space awake.
    """
    if not url:
        logger.warning("⚠️ No URL provided for Keep Awake ping.")
        return

    logger.info(f"🚀 Starting Keep Awake pinger for {url}")
    while True:
        try:
            # We don't care about the response, just making the request
            requests.get(url, timeout=10)
            logger.info("📡 Ping sent to keep Nova awake.")
        except Exception as e:
            logger.error(f"⚠️ Keep Awake ping failed: {e}")
        
        time.sleep(interval)

def start_keep_awake():
    """
    Starts the pinger in a background thread if SPACE_ID is detected.
    """
    space_id = os.environ.get("SPACE_ID")
    if space_id:
        # Hugging Face Spaces URLs follow this pattern: https://{username}-{space_name}.hf.space
        # But we can also use the generic health endpoint if it's hosted there.
        # For HF, we usually ping the public URL.
        site_url = f"https://{space_id.replace('/', '-')}.hf.space"
        thread = Thread(target=ping_self, args=(site_url,), daemon=True)
        thread.start()
    else:
        logger.info("ℹ️ Not running on Hugging Face (SPACE_ID not found). Keep Awake skipped.")

if __name__ == "__main__":
    # Test
    start_keep_awake()
