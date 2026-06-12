"""
HermesClaw Self-Learning Loop
=============================
Captures execution traces → detects patterns → crystallizes reusable skills →
persists a deepening knowledge model of user preferences.

Lifecycle:
  1. After every TaskPlanner.execute(), record_trace() stores the tool call
     sequence, goal, outcome, and latency.
  2. detect_patterns() scans recent traces for repeated tool sequences
     (n-gram frequency) and successful workflows.
  3. crystallize_skill() promotes a pattern that meets the minimum occurrence
     threshold into a named, parameterised skill in learned_skills.
  4. persist_knowledge() updates the user-preference model so future prompts
     can be disambiguated faster.
"""

import json
import hashlib
import logging
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# ── Tunables ────────────────────────────────────────────────────────────────
# Minimum number of times a tool sequence must appear before crystallisation
MIN_OCCURRENCES = 3
# N-gram window sizes to scan (2-grams, 3-grams)
NGRAM_SIZES = [2, 3, 4]
# Maximum skills to keep per task category
MAX_SKILLS_PER_CATEGORY = 50
# Minimum success rate for a pattern to be considered "winning"
MIN_SUCCESS_RATE = 0.6
# Knowledge freshness half-life in hours
KNOWLEDGE_HALF_LIFE_HOURS = 168  # 7 days


# ── Data Classes ────────────────────────────────────────────────────────────
@dataclass
class ExecutionTrace:
    session_id: str
    agent_id: str
    goal: str
    tool_sequence: List[str]
    outcome: str  # "completed", "degraded", "blocked", "max_steps", "error"
    total_steps: int
    total_latency_ms: float
    client_id: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectedPattern:
    ngram: Tuple[str, ...]
    count: int
    success_rate: float
    avg_latency_ms: float
    category: str  # derived from goal keywords


@dataclass
class CrystallizedSkill:
    skill_id: str
    name: str
    description: str
    tool_sequence: List[str]
    category: str
    confidence: float
    occurrences: int
    avg_latency_ms: float


# ── Core Loop ───────────────────────────────────────────────────────────────
class SelfLearningLoop:
    """Orchestrates the full learn-from-experience pipeline."""

    def __init__(self):
        self._initialized = False

    # ── 1. Trace Recording ──────────────────────────────────────────────
    async def record_trace(self, trace: ExecutionTrace):
        """Persist an execution trace for later pattern analysis."""
        seq_json = json.dumps(trace.tool_sequence)
        seq_hash = hashlib.md5(seq_json.encode()).hexdigest()[:16]
        meta_json = json.dumps(trace.metadata)

        await DatabaseManager.query(
            """INSERT INTO execution_traces
               (session_id, agent_id, goal, tool_sequence, tool_sequence_hash,
                outcome, total_steps, total_latency_ms, client_id,
                timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace.session_id,
                trace.agent_id,
                trace.goal[:500],
                seq_json,
                seq_hash,
                trace.outcome,
                trace.total_steps,
                trace.total_latency_ms,
                trace.client_id,
                trace.timestamp,
                meta_json,
            ),
        )
        logger.debug(
            f"[SELF_LEARN] Recorded trace {trace.session_id} "
            f"(seq={seq_json[:80]}… outcome={trace.outcome})"
        )

    # ── 2. Pattern Detection ────────────────────────────────────────────
    async def detect_patterns(
        self, client_id: int = 0, lookback_days: int = 7
    ) -> List[DetectedPattern]:
        """Scan recent traces for repeated n-gram tool sequences."""
        rows = await DatabaseManager.fetchall(
            """SELECT tool_sequence, outcome, total_latency_ms, goal
               FROM execution_traces
               WHERE client_id = ?
                 AND timestamp >= ?""",
            (client_id, time.time() - lookback_days * 86400),
        )

        if not rows:
            return []

        # Build n-gram frequency map
        ngram_stats: Dict[tuple, Dict] = defaultdict(
            lambda: {"count": 0, "successes": 0, "latency_sum": 0.0}
        )

        for row in rows:
            try:
                seq = json.loads(row["tool_sequence"])
            except (json.JSONDecodeError, TypeError):
                continue

            outcome = row["outcome"]
            latency = row["total_latency_ms"] or 0
            is_success = outcome in ("completed", "ok")

            for n in NGRAM_SIZES:
                for i in range(len(seq) - n + 1):
                    ngram = tuple(seq[i : i + n])
                    stats = ngram_stats[ngram]
                    stats["count"] += 1
                    stats["latency_sum"] += latency
                    if is_success:
                        stats["successes"] += 1

        # Filter to patterns meeting thresholds
        detected: List[DetectedPattern] = []
        for ngram, stats in ngram_stats.items():
            count = stats["count"]
            if count < MIN_OCCURRENCES:
                continue
            success_rate = stats["successes"] / count
            if success_rate < MIN_SUCCESS_RATE:
                continue
            avg_latency = stats["latency_sum"] / count
            category = self._categorize_ngram(ngram)
            detected.append(
                DetectedPattern(
                    ngram=ngram,
                    count=count,
                    success_rate=round(success_rate, 4),
                    avg_latency_ms=round(avg_latency, 1),
                    category=category,
                )
            )

        # Sort by count descending
        detected.sort(key=lambda d: d.count, reverse=True)
        logger.info(
            f"[SELF_LEARN] Detected {len(detected)} patterns "
            f"from {len(rows)} traces"
        )
        return detected

    # ── 3. Skill Crystallization ────────────────────────────────────────
    async def crystallize_skill(
        self, pattern: DetectedPattern
    ) -> Optional[CrystallizedSkill]:
        """Promote a detected pattern into a persisted reusable skill."""
        skill_id = hashlib.md5(
            ("::".join(pattern.ngram)).encode()
        ).hexdigest()[:12]

        # Check if skill already exists
        existing = await DatabaseManager.fetchone(
            "SELECT id FROM learned_skills WHERE id = ?", (skill_id,)
        )
        if existing:
            # Update confidence and occurrences
            await DatabaseManager.query(
                """UPDATE learned_skills
                   SET confidence = ?, occurrences = ?, avg_latency_ms = ?
                   WHERE id = ?""",
                (pattern.success_rate, pattern.count, pattern.avg_latency_ms, skill_id),
            )
            logger.debug(f"[SELF_LEARN] Updated skill {skill_id}")
        else:
            # Check category cap
            cat_count_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) as cnt FROM learned_skills WHERE category = ?",
                (pattern.category,),
            )
            if cat_count_row and cat_count_row["cnt"] >= MAX_SKILLS_PER_CATEGORY:
                # Evict lowest-confidence skill in category
                await DatabaseManager.query(
                    """DELETE FROM learned_skills WHERE category = ?
                       AND id = (
                         SELECT id FROM learned_skills WHERE category = ?
                         ORDER BY confidence ASC, occurrences ASC LIMIT 1
                       )""",
                    (pattern.category, pattern.category),
                )

            name = self._generate_skill_name(pattern)
            description = self._generate_skill_description(pattern)
            seq_json = json.dumps(list(pattern.ngram))

            await DatabaseManager.query(
                """INSERT INTO learned_skills
                   (id, name, description, tool_sequence, category,
                    confidence, occurrences, avg_latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (
                    skill_id,
                    name,
                    description,
                    seq_json,
                    pattern.category,
                    pattern.success_rate,
                    pattern.count,
                    pattern.avg_latency_ms,
                ),
            )
            logger.info(
                f"[SELF_LEARN] ✨ Crystallized new skill: {name} "
                f"(confidence={pattern.success_rate:.2f}, "
                f"occurrences={pattern.count})"
            )

        return CrystallizedSkill(
            skill_id=skill_id,
            name=name if not existing else f"skill_{skill_id}",
            description=description if not existing else "",
            tool_sequence=list(pattern.ngram),
            category=pattern.category,
            confidence=pattern.success_rate,
            occurrences=pattern.count,
            avg_latency_ms=pattern.avg_latency_ms,
        )

    # ── 4. Knowledge Persistence ────────────────────────────────────────
    async def persist_knowledge(
        self, client_id: int = 0, goal: str = "", outcome: str = ""
    ):
        """Update the deepening preference model based on observed outcomes."""
        if not goal:
            return

        # Extract preference signals from the goal
        pref_signals = self._extract_preference_signals(goal)

        for key, value in pref_signals.items():
            # Upsert preference with exponential moving average
            existing = await DatabaseManager.fetchone(
                """SELECT id, confidence, sample_count
                   FROM user_preferences
                   WHERE client_id = ? AND pref_key = ? AND pref_value = ?""",
                (client_id, key, value),
            )

            if existing:
                new_count = existing["sample_count"] + 1
                # EMA: new_confidence = alpha * 1 + (1-alpha) * old_confidence
                alpha = 1.0 / new_count  # learning rate decreases with more samples
                new_confidence = alpha * 1.0 + (1 - alpha) * existing["confidence"]
                await DatabaseManager.query(
                    """UPDATE user_preferences
                       SET confidence = ?, sample_count = ?,
                           last_seen_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (round(new_confidence, 4), new_count, existing["id"]),
                )
            else:
                await DatabaseManager.query(
                    """INSERT INTO user_preferences
                       (client_id, pref_key, pref_value, confidence,
                        sample_count, created_at)
                       VALUES (?, ?, ?, 0.5, 1, CURRENT_TIMESTAMP)""",
                    (client_id, key, value),
                )

    async def get_learned_skills(
        self, category: Optional[str] = None, min_confidence: float = 0.0
    ) -> List[Dict]:
        """Retrieve learned skills for injection into agent context."""
        query = (
            "SELECT * FROM learned_skills WHERE confidence >= ?"
        )
        params: list = [min_confidence]
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY confidence DESC, occurrences DESC LIMIT 20"

        rows = await DatabaseManager.fetchall(query, tuple(params))
        return [dict(row) for row in rows]

    async def get_preference_model(self, client_id: int = 0) -> Dict[str, Any]:
        """Retrieve the user preference model for context injection."""
        rows = await DatabaseManager.fetchall(
            """SELECT pref_key, pref_value, confidence, sample_count
               FROM user_preferences
               WHERE client_id = ? AND confidence > 0.3
               ORDER BY confidence DESC""",
            (client_id,),
        )
        model: Dict[str, List] = defaultdict(list)
        for row in rows:
            model[row["pref_key"]].append(
                {
                    "value": row["pref_value"],
                    "confidence": row["confidence"],
                    "samples": row["sample_count"],
                }
            )
        return dict(model)

    # ── 5. Full Cycle ──────────────────────────────────────────────────
    async def run_cycle(self, client_id: int = 0):
        """Execute a complete learning cycle:
        detect patterns → crystallize skills → prune stale data.
        Called by the Self-Improvement lane (Lane 8) every 6 hours.
        """
        logger.info("🧠 [SELF_LEARN] Starting learning cycle...")

        # 1. Detect patterns
        patterns = await self.detect_patterns(client_id=client_id)

        # 2. Crystallize top patterns into skills
        crystallized = 0
        for pattern in patterns[:20]:  # Cap at 20 per cycle
            skill = await self.crystallize_skill(pattern)
            if skill:
                crystallized += 1

        # 3. Prune old traces (> 30 days)
        await self._prune_old_traces()

        # 4. Prune low-confidence preferences
        await self._prune_stale_preferences()

        logger.info(
            f"🧠 [SELF_LEARN] Cycle complete. "
            f"Patterns detected: {len(patterns)}, "
            f"Skills crystallized: {crystallized}"
        )

        return {
            "patterns_detected": len(patterns),
            "skills_crystallized": crystallized,
        }

    # ── Internal Helpers ────────────────────────────────────────────────
    def _categorize_ngram(self, ngram: Tuple[str, ...]) -> str:
        """Derive a category label from the tool sequence."""
        tools = set(ngram)
        if tools & {"find_leads", "sgai_search_and_extract", "google_search", "research_lead"}:
            return "lead_generation"
        if tools & {"send_outreach", "send_email", "create_drip_campaign", "generate_sequence"}:
            return "outreach"
        if tools & {"browse_agent", "elite_scrape", "stealth_extract", "sgai_deep_extract"}:
            return "research"
        if tools & {"write_content", "write_cold_email", "write_ad_copy"}:
            return "content"
        if tools & {"pipeline_report", "conversion_analysis", "roi_calculator"}:
            return "analytics"
        if tools & {"check_replies", "reply_to_email"}:
            return "engagement"
        return "general"

    def _generate_skill_name(self, pattern: DetectedPattern) -> str:
        """Create a human-readable name from the tool sequence."""
        short_names = {
            "find_leads": "FindLeads",
            "research_lead": "Research",
            "send_outreach": "Outreach",
            "send_email": "Email",
            "browse_agent": "Browse",
            "elite_scrape": "Scrape",
            "deep_research": "DeepResearch",
            "write_cold_email": "ColdEmail",
            "create_drip_campaign": "Drip",
            "check_replies": "CheckReplies",
            "pipeline_report": "Pipeline",
            "proofread_email": "Proofread",
            "generate_sequence": "FollowUp",
            "run_seo_audit": "SEO",
            "analyze_competitor": "Competitor",
        }
        parts = [
            short_names.get(tool, tool.title().replace("_", ""))
            for tool in pattern.ngram
        ]
        return f"auto_{'_'.join(parts)}"

    def _generate_skill_description(self, pattern: DetectedPattern) -> str:
        """Auto-generate a description for the crystallized skill."""
        tools_str = " → ".join(pattern.ngram)
        return (
            f"Auto-learned workflow: {tools_str}. "
            f"Success rate: {pattern.success_rate:.0%} across "
            f"{pattern.count} executions. "
            f"Avg latency: {pattern.avg_latency_ms:.0f}ms."
        )

    def _extract_preference_signals(self, goal: str) -> Dict[str, str]:
        """Extract preference signals from a goal string."""
        signals: Dict[str, str] = {}
        goal_lower = goal.lower()

        # Vertical preference
        verticals = {
            "automotive": "automotive",
            "car dealer": "automotive",
            "luxury car": "automotive",
            "plumber": "home_services",
            "hvac": "home_services",
            "roofing": "home_services",
            "real estate": "real_estate",
            "fitness": "fitness",
            "dentist": "healthcare",
            "lawyer": "legal",
        }
        for keyword, vertical in verticals.items():
            if keyword in goal_lower:
                signals["preferred_vertical"] = vertical
                break

        # Task preference
        if any(w in goal_lower for w in ["find leads", "search for", "hunt"]):
            signals["preferred_task_type"] = "lead_generation"
        elif any(w in goal_lower for w in ["send", "email", "outreach"]):
            signals["preferred_task_type"] = "outreach"
        elif any(w in goal_lower for w in ["research", "analyze", "audit"]):
            signals["preferred_task_type"] = "research"
        elif any(w in goal_lower for w in ["write", "draft", "content"]):
            signals["preferred_task_type"] = "content"

        # Depth preference
        if any(w in goal_lower for w in ["quick", "fast", "simple"]):
            signals["preferred_depth"] = "shallow"
        elif any(w in goal_lower for w in ["deep", "thorough", "comprehensive"]):
            signals["preferred_depth"] = "deep"

        return signals

    async def _prune_old_traces(self, max_age_days: int = 30):
        """Remove traces older than max_age_days."""
        await DatabaseManager.query(
            "DELETE FROM execution_traces WHERE timestamp < ?",
            (time.time() - max_age_days * 86400,),
        )

    async def _prune_stale_preferences(self, min_confidence: float = 0.1):
        """Remove preferences that have decayed below threshold."""
        await DatabaseManager.query(
            "DELETE FROM user_preferences WHERE confidence < ?",
            (min_confidence,),
        )


# ── Schema Bootstrap ────────────────────────────────────────────────────────

EXECUTION_TRACES_DDL = """
CREATE TABLE IF NOT EXISTS execution_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT 'nova',
    goal TEXT NOT NULL,
    tool_sequence TEXT NOT NULL,
    tool_sequence_hash TEXT NOT NULL,
    outcome TEXT NOT NULL,
    total_steps INTEGER NOT NULL DEFAULT 0,
    total_latency_ms REAL NOT NULL DEFAULT 0,
    client_id INTEGER NOT NULL DEFAULT 0,
    timestamp REAL NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_traces_client_ts
    ON execution_traces(client_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_traces_hash
    ON execution_traces(tool_sequence_hash);
"""

LEARNED_SKILLS_DDL = """
CREATE TABLE IF NOT EXISTS learned_skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    tool_sequence TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    confidence REAL NOT NULL DEFAULT 0.5,
    occurrences INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_skills_category
    ON learned_skills(category, confidence DESC);
"""

USER_PREFERENCES_DDL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER NOT NULL DEFAULT 0,
    pref_key TEXT NOT NULL,
    pref_value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    sample_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(client_id, pref_key, pref_value)
);
CREATE INDEX IF NOT EXISTS idx_prefs_client
    ON user_preferences(client_id, confidence DESC);
"""


async def ensure_tables():
    """Create learning tables if they don't exist."""
    for ddl in [EXECUTION_TRACES_DDL, LEARNED_SKILLS_DDL, USER_PREFERENCES_DDL]:
        try:
            await DatabaseManager.query(ddl)
        except Exception as e:
            logger.warning(f"[SELF_LEARN] Table creation note: {e}")


# ── Singleton ───────────────────────────────────────────────────────────────
self_learning_loop = SelfLearningLoop()