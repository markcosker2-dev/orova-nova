import asyncio
import logging
from datetime import datetime, timedelta
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

DECAY_RATE        = 0.15    # Confidence loss per stale cycle
SUCCESS_THRESHOLD = 0.6     # Min success rate to remain a "Winner"
MIN_SAMPLE_SIZE   = 5       # Min data points before learning

class PatternReinforcer:
    """
    [P2] Nova's Autonomous Learning Loop.
    Reads metrics → Identifies winners → Updates learned_patterns.
    """

    async def run_cycle(self):
        """Scheduled reinforcement cycle."""
        logger.info("🧠 [HERMES] Starting autonomous learning cycle...")
        try:
            await self._decay_stale_patterns()
            winners = await self._identify_winners()
            for w in winners:
                await self._upsert_pattern(w["task_type"], w["winning_approach"], w["score"])
            await self._prune_dead_patterns()
            logger.info(f"✅ [HERMES] Learning cycle complete. Winners reinforced: {len(winners)}")
        except Exception as e:
            logger.error(f"❌ [HERMES] Learning cycle failed: {e}")

    async def _decay_stale_patterns(self):
        """Stale patterns lose confidence over time."""
        cutoff = datetime.utcnow() - timedelta(hours=48)
        await DatabaseManager.query(
            "UPDATE learned_patterns SET decay_score = MAX(0.0, decay_score - ?) WHERE last_used_at < ?",
            (DECAY_RATE, cutoff.isoformat())
        )

    async def _identify_winners(self) -> list:
        """Finds high-performing approaches from recent metrics."""
        # Simplified logic: Join metrics with patterns
        return await DatabaseManager.fetchall("""
            SELECT task_type, winning_approach, AVG(success_metric) as score
            FROM learned_patterns
            WHERE created_at > datetime('now', '-7 days')
            GROUP BY task_type, winning_approach
            HAVING COUNT(*) >= ? AND score >= ?
        """, (MIN_SAMPLE_SIZE, SUCCESS_THRESHOLD))

from app.core.sentinel import send_admin_message

# ── [P5] Thresholds ──────────────────────────────────────────────────────────
HIGH_CONFIDENCE_THRESHOLD = 0.80     # Score at which Nova surfaces the insight
INSIGHT_NOTIFY_COOLDOWN = 86400      # 24h

_notified_patterns: dict[str, datetime] = {}

class PatternReinforcer:
    async def _maybe_notify_insight(self, task_type: str, approach: str, score: float, client_id: int):
        if score < HIGH_CONFIDENCE_THRESHOLD: return
        key = f"{client_id}:{task_type}:{approach}"
        now = datetime.utcnow()
        if key in _notified_patterns and (now - _notified_patterns[key]).total_seconds() < INSIGHT_NOTIFY_COOLDOWN:
            return
        _notified_patterns[key] = now
        
        msg = (
            f"💎 *OROVA Luxury Insight*\n"
            f"Client: `{client_id}`\n"
            f"Task: `{task_type}`\n"
            f"Winning Approach Identified.\n"
            f"Confidence Score: `{round(score, 4)}`"
        )
        await send_admin_message(msg)

    async def _upsert_pattern(self, task_type: str, approach: str, score: float, client_id: int = 0):
        await DatabaseManager.query(
            "UPDATE learned_patterns SET decay_score = MIN(1.0, decay_score + ?), last_used_at = CURRENT_TIMESTAMP WHERE task_type = ? AND winning_approach = ? AND client_id = ?",
            (0.1, task_type, approach, client_id)
        )
        await self._maybe_notify_insight(task_type, approach, score, client_id)

    async def _prune_dead_patterns(self):
        await DatabaseManager.query("DELETE FROM learned_patterns WHERE decay_score < 0.05")

# Global instance
reinforcer = PatternReinforcer()
