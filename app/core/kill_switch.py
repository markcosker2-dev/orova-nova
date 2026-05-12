"""
OROVA Nova — Kill Switch
Emergency stop for all autonomous operations.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

KILL_SWITCH_FILE = os.getenv("OROVA_KILL_SWITCH", "/opt/orova/data/.kill_switch")


class KillSwitch:
    """
    One-command emergency stop.
    When activated, all agents halt. No outbound actions allowed.
    """

    def __init__(self, kill_file: str = None):
        self.kill_file = kill_file or KILL_SWITCH_FILE
        os.makedirs(os.path.dirname(self.kill_file), exist_ok=True)

    def activate(self, reason: str = "manual"):
        """Activate the kill switch. All agents will stop."""
        data = {
            "active": True,
            "reason": reason,
            "activated_at": datetime.utcnow().isoformat(),
            "activated_by": "system"
        }
        with open(self.kill_file, "w") as f:
            json.dump(data, f)

        logger.critical(f"[KILL SWITCH] ACTIVATED: {reason}")
        return data

    def deactivate(self):
        """Deactivate the kill switch. Agents resume."""
        if os.path.exists(self.kill_file):
            os.remove(self.kill_file)
        logger.info("[KILL SWITCH] Deactivated. Agents resuming.")

    def is_active(self) -> bool:
        """Check if kill switch is active."""
        return os.path.exists(self.kill_file)

    def get_status(self) -> dict:
        """Get kill switch status."""
        if not self.is_active():
            return {"active": False}

        with open(self.kill_file, "r") as f:
            return json.load(f)

    def check_before_action(self, agent: str, action: str) -> bool:
        """
        Call before any outbound action.
        Returns True if action is allowed, False if kill switch is active.
        """
        if self.is_active():
            status = self.get_status()
            logger.warning(
                f"[KILL SWITCH] Blocked {agent}.{action}: {status.get('reason', 'active')}"
            )
            return False
        return True


# Global instance
kill_switch = KillSwitch()
