import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def get_browser_launch_args() -> Dict[str, Any]:
    """
    Returns the appropriate launch arguments for Playwright.
    Handles ARM64 (Oracle Cloud) vs x64 (Local/AWS) environments.
    """
    # Check for custom executable path (crucial for ARM64)
    executable_path = os.environ.get("CHROME_PATH") or os.environ.get("EXECUTABLE_PATH")
    
    # Common safe arguments
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu"
    ]
    
    launch_options = {
        "headless": True,
        "args": args
    }
    
    if executable_path and os.path.exists(executable_path):
        logger.info(f"🚀 Playwright: Using custom Chromium at {executable_path}")
        launch_options["executable_path"] = executable_path
    elif os.name != 'nt':  # Linux-specific ARM checks
        # Potential ARM locations if not explicitly set
        potential_paths = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/bin/google-chrome"
        ]
        for path in potential_paths:
            if os.path.exists(path):
                logger.info(f"🚀 Playwright: Auto-detected Chromium at {path}")
                launch_options["executable_path"] = path
                break
                
    return launch_options
