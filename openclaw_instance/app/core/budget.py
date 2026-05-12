"""
OROVA Nova — Per-Agent Budget Tracker
Prevents runaway API costs by enforcing daily/hourly spend caps per agent.
"""
import os
import json
import logging
from datetime import datetime, date
from typing import Optional, Dict

logger = logging.getLogger(__name__)

BUDGET_FILE = os.getenv("OROVA_BUDGET_FILE", "/opt/orova/data/budgets.json")

# Default daily caps per agent (USD)
DEFAULT_BUDGETS = {
    "HAWK": {"daily_cap": 2.00, "hourly_cap": 0.50, "per_call_cap": 0.10},
    "SAGE": {"daily_cap": 5.00, "hourly_cap": 1.00, "per_call_cap": 0.15},
    "Quill": {"daily_cap": 1.50, "hourly_cap": 0.40, "per_call_cap": 0.08},
    "Oracle": {"daily_cap": 1.00, "hourly_cap": 0.30, "per_call_cap": 0.05},
    "Nova": {"daily_cap": 3.00, "hourly_cap": 0.80, "per_call_cap": 0.12},
    "Viper": {"daily_cap": 1.00, "hourly_cap": 0.30, "per_call_cap": 0.05},
    "Closer": {"daily_cap": 1.00, "hourly_cap": 0.25, "per_call_cap": 0.08},
    "Sentinel": {"daily_cap": 0.50, "hourly_cap": 0.15, "per_call_cap": 0.03},
    "default": {"daily_cap": 2.00, "hourly_cap": 0.50, "per_call_cap": 0.10}
}


class BudgetTracker:
    """Per-agent cost enforcement."""

    def __init__(self, budget_file: str = None):
        self.budget_file = budget_file or BUDGET_FILE
        os.makedirs(os.path.dirname(self.budget_file), exist_ok=True)

        if not os.path.exists(self.budget_file):
            self._save({})

    def _load(self) -> Dict:
        with open(self.budget_file, "r") as f:
            return json.load(f)

    def _save(self, data: Dict):
        with open(self.budget_file, "w") as f:
            json.dump(data, f, indent=2)

    def _get_today(self) -> str:
        return date.today().isoformat()

    def _get_hour(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d-%H")

    def get_limits(self, agent: str) -> Dict:
        return DEFAULT_BUDGETS.get(agent, DEFAULT_BUDGETS["default"])

    def record_spend(self, agent: str, cost_usd: float) -> Dict:
        """Record a spend and return budget status."""
        data = self._load()
        today = self._get_today()
        hour = self._get_hour()

        if agent not in data:
            data[agent] = {"daily": {}, "hourly": {}}

        # Daily tracking
        if today not in data[agent]["daily"]:
            data[agent]["daily"] = {today: {"spent": 0.0, "calls": 0}}
        data[agent]["daily"][today]["spent"] += cost_usd
        data[agent]["daily"][today]["calls"] += 1

        # Hourly tracking
        if hour not in data[agent]["hourly"]:
            data[agent]["hourly"] = {hour: {"spent": 0.0, "calls": 0}}
        data[agent]["hourly"][hour]["spent"] += cost_usd
        data[agent]["hourly"][hour]["calls"] += 1

        self._save(data)

        return self.check_budget(agent)

    def check_budget(self, agent: str) -> Dict:
        """Check if agent is within budget."""
        data = self._load()
        today = self._get_today()
        hour = self._get_hour()
        limits = self.get_limits(agent)

        daily_spent = data.get(agent, {}).get("daily", {}).get(today, {}).get("spent", 0.0)
        hourly_spent = data.get(agent, {}).get("hourly", {}).get(hour, {}).get("spent", 0.0)
        daily_calls = data.get(agent, {}).get("daily", {}).get(today, {}).get("calls", 0)

        daily_ok = daily_spent < limits["daily_cap"]
        hourly_ok = hourly_spent < limits["hourly_cap"]

        return {
            "agent": agent,
            "daily_spent": round(daily_spent, 4),
            "daily_cap": limits["daily_cap"],
            "daily_remaining": round(limits["daily_cap"] - daily_spent, 4),
            "daily_ok": daily_ok,
            "hourly_spent": round(hourly_spent, 4),
            "hourly_cap": limits["hourly_cap"],
            "hourly_ok": hourly_ok,
            "daily_calls": daily_calls,
            "can_proceed": daily_ok and hourly_ok
        }

    def get_all_status(self) -> Dict:
        """Get budget status for all agents."""
        return {agent: self.check_budget(agent) for agent in DEFAULT_BUDGETS}

    def should_throttle(self, agent: str) -> bool:
        """Returns True if agent should be throttled."""
        status = self.check_budget(agent)
        return not status["can_proceed"]


# Global instance
budget = BudgetTracker()
