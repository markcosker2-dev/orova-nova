"""
OROVA Nova — Revenue Tracker
Tracks pipeline value, forecast, win rate, and deal progression.
This is what makes Nova a real business, not just a lead generator.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REVENUE_FILE = os.getenv("OROVA_REVENUE_FILE", "/opt/orova/data/revenue_pipeline.json")


class RevenueTracker:
    """
    Tracks the money. Every lead has a dollar value.
    Nova knows exactly how much revenue is in the pipeline.
    """

    # Default deal values by vertical (can be customized)
    DEFAULT_DEAL_VALUES = {
        "LuxuryRemodeling": 25000,
        "HVAC": 8000,
        "Roofing": 15000,
        "Automotive": 12000,
        "Plumbing": 5000,
        "General": 10000
    }

    # Stage multipliers (probability of closing at each stage)
    STAGE_PROBABILITIES = {
        "New": 0.05,
        "Contacted": 0.10,
        "Interested": 0.25,
        "Meeting Booked": 0.50,
        "Proposal Sent": 0.70,
        "Won": 1.00,
        "Lost": 0.00
    }

    def __init__(self):
        self.pipeline_file = REVENUE_FILE
        os.makedirs(os.path.dirname(self.pipeline_file), exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.pipeline_file):
            with open(self.pipeline_file, "r") as f:
                self.pipeline = json.load(f)
        else:
            self.pipeline = {
                "deals": [],
                "monthly_targets": {},
                "closed_revenue": 0,
                "settings": {
                    "default_deal_values": self.DEFAULT_DEAL_VALUES,
                    "currency": "USD"
                }
            }
            self._save()

    def _save(self):
        with open(self.pipeline_file, "w") as f:
            json.dump(self.pipeline, f, indent=2)

    def add_deal(self, lead_id: int, business: str, vertical: str,
                 estimated_value: float = None, stage: str = "New",
                 contact: str = "", email: str = "", phone: str = ""):
        """Add a deal to the revenue pipeline."""
        if estimated_value is None:
            estimated_value = self.pipeline["settings"]["default_deal_values"].get(
                vertical, self.DEFAULT_DEAL_VALUES["General"]
            )

        deal = {
            "lead_id": lead_id,
            "business": business,
            "vertical": vertical,
            "estimated_value": estimated_value,
            "weighted_value": estimated_value * self.STAGE_PROBABILITIES.get(stage, 0.05),
            "stage": stage,
            "contact": contact,
            "email": email,
            "phone": phone,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "notes": []
        }

        # Check for duplicates
        for existing in self.pipeline["deals"]:
            if existing["lead_id"] == lead_id:
                return {"status": "duplicate", "deal": existing}

        self.pipeline["deals"].append(deal)
        self._save()

        logger.info(f"[REVENUE] Deal added: {business} — ${estimated_value:,.0f} ({stage})")
        return {"status": "added", "deal": deal}

    def update_stage(self, lead_id: int, new_stage: str, note: str = ""):
        """Move a deal to a new stage."""
        for deal in self.pipeline["deals"]:
            if deal["lead_id"] == lead_id:
                old_stage = deal["stage"]
                deal["stage"] = new_stage
                deal["weighted_value"] = deal["estimated_value"] * self.STAGE_PROBABILITIES.get(new_stage, 0.05)
                deal["updated_at"] = datetime.utcnow().isoformat()

                if note:
                    deal["notes"].append({
                        "note": note,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                # If won, add to closed revenue
                if new_stage == "Won":
                    self.pipeline["closed_revenue"] += deal["estimated_value"]
                    logger.info(f"[REVENUE] DEAL WON: {deal['business']} — ${deal['estimated_value']:,.0f}")

                self._save()
                return {"status": "updated", "old_stage": old_stage, "new_stage": new_stage}

        return {"status": "not_found"}

    def get_pipeline_summary(self) -> Dict:
        """Get complete pipeline overview."""
        deals = self.pipeline["deals"]
        active = [d for d in deals if d["stage"] not in ("Won", "Lost")]

        total_value = sum(d["estimated_value"] for d in active)
        weighted_value = sum(d["weighted_value"] for d in active)

        by_stage = {}
        for deal in active:
            stage = deal["stage"]
            if stage not in by_stage:
                by_stage[stage] = {"count": 0, "value": 0, "weighted": 0}
            by_stage[stage]["count"] += 1
            by_stage[stage]["value"] += deal["estimated_value"]
            by_stage[stage]["weighted"] += deal["weighted_value"]

        by_vertical = {}
        for deal in active:
            v = deal["vertical"]
            if v not in by_vertical:
                by_vertical[v] = {"count": 0, "value": 0}
            by_vertical[v]["count"] += 1
            by_vertical[v]["value"] += deal["estimated_value"]

        # Win rate
        closed = [d for d in deals if d["stage"] in ("Won", "Lost")]
        won = [d for d in closed if d["stage"] == "Won"]
        win_rate = len(won) / max(len(closed), 1) * 100

        # Average deal size
        avg_deal = total_value / max(len(active), 1)

        return {
            "total_pipeline_value": round(total_value, 2),
            "weighted_pipeline_value": round(weighted_value, 2),
            "closed_revenue": self.pipeline["closed_revenue"],
            "active_deals": len(active),
            "total_deals": len(deals),
            "win_rate": round(win_rate, 1),
            "average_deal_size": round(avg_deal, 2),
            "by_stage": by_stage,
            "by_vertical": by_vertical,
            "currency": self.pipeline["settings"]["currency"]
        }

    def get_forecast(self, days_ahead: int = 30) -> Dict:
        """Revenue forecast based on pipeline stages and probabilities."""
        deals = self.pipeline["deals"]
        active = [d for d in deals if d["stage"] not in ("Won", "Lost")]

        # Expected revenue = sum of weighted values
        expected = sum(d["weighted_value"] for d in active)

        # Best case = all active deals close
        best_case = sum(d["estimated_value"] for d in active)

        # Conservative = only deals in Proposal+ stages
        conservative = sum(
            d["weighted_value"] for d in active
            if d["stage"] in ("Proposal Sent", "Meeting Booked")
        )

        return {
            "forecast_period_days": days_ahead,
            "expected_revenue": round(expected, 2),
            "best_case": round(best_case, 2),
            "conservative": round(conservative, 2),
            "deals_in_pipeline": len(active),
            "confidence": "medium" if len(active) > 5 else "low"
        }

    def get_monthly_report(self) -> Dict:
        """Monthly revenue report."""
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0)

        deals_this_month = [
            d for d in self.pipeline["deals"]
            if d.get("created_at", "") >= month_start.isoformat()
        ]

        won_this_month = [
            d for d in self.pipeline["deals"]
            if d["stage"] == "Won" and d.get("updated_at", "") >= month_start.isoformat()
        ]

        revenue_this_month = sum(d["estimated_value"] for d in won_this_month)

        return {
            "month": now.strftime("%B %Y"),
            "new_deals": len(deals_this_month),
            "deals_won": len(won_this_month),
            "revenue_closed": round(revenue_this_month, 2),
            "pipeline_value": round(sum(d["estimated_value"] for d in deals_this_month if d["stage"] not in ("Won", "Lost")), 2),
            "summary": self.get_pipeline_summary()
        }

    def set_monthly_target(self, month: str, target: float):
        """Set a monthly revenue target. Format: '2026-04'"""
        self.pipeline["monthly_targets"][month] = target
        self._save()

    def get_target_progress(self, month: str = None) -> Dict:
        """Check progress toward monthly target."""
        if month is None:
            month = datetime.utcnow().strftime("%Y-%m")

        target = self.pipeline["monthly_targets"].get(month, 0)
        if target == 0:
            return {"month": month, "target": 0, "closed": 0, "progress": 0, "status": "no_target_set"}

        # Revenue closed this month
        now = datetime.utcnow()
        month_start = now.replace(day=1).isoformat()
        closed = sum(
            d["estimated_value"] for d in self.pipeline["deals"]
            if d["stage"] == "Won" and d.get("updated_at", "") >= month_start
        )

        progress = (closed / target) * 100

        return {
            "month": month,
            "target": target,
            "closed": round(closed, 2),
            "remaining": round(target - closed, 2),
            "progress": round(progress, 1),
            "status": "on_track" if progress >= 50 else "behind" if progress > 0 else "no_progress"
        }


# Global instance
revenue = RevenueTracker()
