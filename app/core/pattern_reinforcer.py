import asyncio
import logging
from datetime import datetime, timedelta
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

DECAY_RATE        = 0.15
SUCCESS_THRESHOLD = 0.6
MIN_SAMPLE_SIZE   = 5

from app.core.sentinel import send_admin_message

HIGH_CONFIDENCE_THRESHOLD = 0.80
INSIGHT_NOTIFY_COOLDOWN = 86400

_notified_patterns: dict[str, datetime] = {}

class PatternReinforcer:
    """
    [P2] Nova's Autonomous Learning Loop.
    Reads metrics → Identifies winners → Updates learned_patterns.
    """

    def __init__(self):
        self._reinforced_this_cycle: set = set()

    async def run_cycle(self):
        """Scheduled reinforcement cycle."""
        logger.info("🧠 [HERMES] Starting autonomous learning cycle...")
        self._reinforced_this_cycle = set()  # reset idempotency guard
        try:
            await self._decay_stale_patterns()
            winners = await self._identify_winners()
            for w in winners:
                await self._upsert_pattern(
                    w["task_type"],
                    w["winning_approach"],
                    w["score"],
                    client_id=int(w.get("client_id", 0))
                )
            await self._prune_dead_patterns()
            logger.info(f"✅ [HERMES] Learning cycle complete. Winners reinforced: {len(winners)}")
        except Exception as e:
            logger.error(f"❌ [HERMES] Learning cycle failed: {e}")

    async def _decay_stale_patterns(self):
        """Stale patterns lose confidence over time."""
        await DatabaseManager.query(
            "UPDATE learned_patterns SET decay_score = MAX(0.0, decay_score - ?) WHERE last_used_at < datetime('now', '-48 hours')",
            (DECAY_RATE,)
        )

    async def _identify_winners(self) -> list:
        """Finds high-performing approaches from recent metrics including client context."""
        return await DatabaseManager.fetchall("""
            SELECT task_type, winning_approach, client_id, AVG(success_metric) as score
            FROM learned_patterns
            WHERE created_at > datetime('now', '-7 days')
            GROUP BY task_type, winning_approach, client_id
            HAVING COUNT(*) >= ? AND score >= ?
        """, (MIN_SAMPLE_SIZE, SUCCESS_THRESHOLD))

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
        # Idempotency guard: skip if already reinforced this cycle
        key = (task_type, approach, client_id)
        if key in self._reinforced_this_cycle:
            return
        self._reinforced_this_cycle.add(key)

        # Atomic upsert: INSERT new pattern or UPDATE existing one
        # Uses unique index idx_learned_patterns_unique on (task_type, winning_approach, client_id)
        await DatabaseManager.query(
            """INSERT INTO learned_patterns (id, task_type, winning_approach, client_id, pattern_type, content, decay_score, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, 0.1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT (task_type, winning_approach, client_id) DO UPDATE SET
                   decay_score = MIN(1.0, decay_score + 0.1),
                   last_used_at = CURRENT_TIMESTAMP""",
            (f"{task_type}:{approach}:{client_id}", task_type, approach, client_id, task_type, approach)
        )
        await self._maybe_notify_insight(task_type, approach, score, client_id)

    async def _prune_dead_patterns(self):
        await DatabaseManager.query("DELETE FROM learned_patterns WHERE decay_score < 0.05")

reinforcer = PatternReinforcer()
