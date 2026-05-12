"""
OROVA Nova — Audit Trail Logger
Every agent action gets logged with full context for debugging and compliance.
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

AUDIT_DIR = os.getenv("OROVA_AUDIT_DIR", "/opt/orova/data/audit")


class AuditTrail:
    """Searchable audit trail for all agent actions."""

    def __init__(self, audit_dir: str = None):
        self.audit_dir = audit_dir or AUDIT_DIR
        os.makedirs(self.audit_dir, exist_ok=True)

    def _get_log_file(self) -> str:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return os.path.join(self.audit_dir, f"audit_{today}.jsonl")

    def log(
        self,
        agent: str,
        action: str,
        input_data: Any = None,
        output_data: Any = None,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        duration_ms: int = 0,
        status: str = "success",
        error: str = None,
        metadata: Dict = None
    ):
        """Log a single agent action."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "action": action,
            "status": status,
            "cost_usd": round(cost_usd, 6),
            "tokens_used": tokens_used,
            "duration_ms": duration_ms,
            "input": str(input_data)[:500] if input_data else None,
            "output": str(output_data)[:500] if output_data else None,
            "error": error,
            "metadata": metadata or {}
        }

        log_file = self._get_log_file()
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def search(
        self,
        agent: str = None,
        action: str = None,
        date: str = None,
        status: str = None,
        limit: int = 50
    ) -> list:
        """Search audit trail entries."""
        if date:
            log_file = os.path.join(self.audit_dir, f"audit_{date}.jsonl")
        else:
            log_file = self._get_log_file()

        if not os.path.exists(log_file):
            return []

        results = []
        with open(log_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if agent and entry.get("agent") != agent:
                    continue
                if action and entry.get("action") != action:
                    continue
                if status and entry.get("status") != status:
                    continue

                results.append(entry)

                if len(results) >= limit:
                    break

        return results

    def get_daily_summary(self, date: str = None) -> Dict:
        """Get cost and action summary for a day."""
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        entries = self.search(date=date, limit=10000)

        total_cost = sum(e.get("cost_usd", 0) for e in entries)
        total_tokens = sum(e.get("tokens_used", 0) for e in entries)
        agents_used = set(e.get("agent", "unknown") for e in entries)
        errors = [e for e in entries if e.get("status") == "error"]

        return {
            "date": date,
            "total_actions": len(entries),
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "agents_active": list(agents_used),
            "error_count": len(errors),
            "error_rate": round(len(errors) / max(len(entries), 1) * 100, 1)
        }


# Global instance
audit = AuditTrail()
