"""[A-01] Metrics repository — metrics CRUD and performance stats."""
import asyncio
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class _MetricsRepo:
    """Mixin: metrics-related database operations."""

    @classmethod
    def update_metrics(cls, metrics_dict: dict, client_id: int = 0):
        with cls.connection() as conn:
            try:
                for key, value in metrics_dict.items():
                    conn.execute(
                        "INSERT INTO metrics (client_id, metric_key, metric_value) VALUES (?, ?, ?)",
                        (client_id, key, float(value))
                    )
                conn.commit()
            except Exception as e:
                logger.error(f"Error updating metrics: {e}")

    @classmethod
    async def aupdate_metrics(cls, metrics_dict: dict, client_id: int = 0):
        """Async wrapper for update_metrics (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cls.update_metrics(metrics_dict, client_id))

    @classmethod
    def get_metrics(cls, client_id: int = 0) -> dict:
        """Return pipeline metrics. Returns safe defaults if DB is unavailable."""
        empty = {
            "leads_found": 0, "emails_sent": 0,
            "replies_received": 0, "meetings_booked": 0,
            "calls_made": 0, "proposals_sent": 0, "cost": 0.0
        }
        try:
            with cls.connection() as conn:
                total = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ?", (client_id,)).fetchone()[0]
                contacted = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status IN ('Contacted','Email Sent')", (client_id,)).fetchone()[0]
                replied = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status = 'Replied'", (client_id,)).fetchone()[0]
                meetings = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status = 'Meeting Booked'", (client_id,)).fetchone()[0]
                
                calls_made_row = conn.execute(
                    "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'calls_made' ORDER BY recorded_at DESC LIMIT 1",
                    (client_id,)
                ).fetchone()
                calls_made = int(calls_made_row[0]) if calls_made_row else 0

                proposals_sent_row = conn.execute(
                    "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'proposals_sent' ORDER BY recorded_at DESC LIMIT 1",
                    (client_id,)
                ).fetchone()
                proposals_sent = int(proposals_sent_row[0]) if proposals_sent_row else 0

                cost_row = conn.execute(
                    "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'cost' ORDER BY recorded_at DESC LIMIT 1",
                    (client_id,)
                ).fetchone()
                cost = float(cost_row[0]) if cost_row else 0.0

                return {
                    "leads_found": int(total or 0), "emails_sent": int(contacted or 0),
                    "replies_received": int(replied or 0), "meetings_booked": int(meetings or 0),
                    "calls_made": calls_made, "proposals_sent": proposals_sent,
                    "cost": cost
                }
        except Exception as e:
            logger.error(f"[DB] get_metrics failed: {e}")
            return empty

    @classmethod
    async def aget_metrics(cls, client_id: int = 0) -> dict:
        """Async wrapper for get_metrics (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cls.get_metrics(client_id))

    @classmethod
    async def get_performance_stats(cls, client_id: int = 0) -> dict:
        return {
            "avg_leads_per_day": 0,
            "conversion_rate": 0,
            "response_time_avg": 0,
        }
