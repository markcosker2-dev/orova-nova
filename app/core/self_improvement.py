# -*- coding: utf-8 -*-
"""
OROVA Nova Self-Improvement Loop
Outcome Tracking, Strategy Optimization, and Learning Engine
"""

import os
import logging
import json
import datetime
from datetime import timedelta
import asyncio

from app.core.database import DatabaseManager
from app.core.ai_client import UnifiedAIClient
from app.skills.agentmail_skill import _send_telegram_alert

logger = logging.getLogger(__name__)


def wilson_lower_bound(successes: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound.

    Ranks strategies by the worst-case plausible win rate, so a 1/1=100%
    fluke (bound ~0.21) never beats a proven 30/100=30% (bound ~0.22+).
    """
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5
    return max(0.0, (centre - margin) / denom)


async def log_improvement(subject_type: str, subject_name: str, action: str,
                          rationale: str = "", client_id: int = 0) -> None:
    """Append one row to improvement_log — the Reflexion-style 'what changed
    and why' trace (ADR-0004 A2.2). vault_pull.py syncs it into
    vault/20-ops/improvement-log.md so agents and Mark can read back why a
    strategy/skill was promoted or retired before touching it again.
    Fail-open: bookkeeping must never break the loop that calls it."""
    try:
        await DatabaseManager.query(
            """INSERT INTO improvement_log (subject_type, subject_name, action, rationale, client_id)
               VALUES (?, ?, ?, ?, ?)""",
            (subject_type, subject_name, action, rationale, client_id),
        )
    except Exception as e:
        logger.debug(f"[IMPROVEMENT_LOG] insert skipped: {e}")


class SkillOutcomeTracker:
    """Per-skill outcome recording (ADR-0004 B1/B2.1) — the skill-code
    counterpart of OutcomeTracker's strategy-string records. Instrumented
    once, in planner.py's tool-execution loop, so no skill file needs its
    own call site. Rows feed /api/skill_health and (Phase 2) the
    SkillChallengerEvaluator's Wilson ranking."""

    @classmethod
    async def record(cls, skill_name: str, outcome: str, latency_ms: float = None,
                     client_id: int = 0, version_id: str = None, metadata: dict = None):
        """outcome: 'success' | 'degraded' | 'error' | 'timeout'. Never raises."""
        try:
            vid = version_id or f"{skill_name}.builtin"
            if version_id is None:
                # Lazily register the builtin champion version so rollups can
                # always join skill_outcomes -> skill_versions.
                await DatabaseManager.query(
                    """INSERT OR IGNORE INTO skill_versions (id, skill_name, version_label, source)
                       VALUES (?, ?, 'champion', 'builtin')""",
                    (vid, skill_name),
                )
            await DatabaseManager.query(
                """INSERT INTO skill_outcomes (skill_name, version_id, outcome, latency_ms, client_id, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (skill_name, vid, outcome, latency_ms,
                 client_id, json.dumps(metadata) if metadata else "{}"),
            )
        except Exception as e:
            logger.debug(f"[SKILL_OUTCOMES] record skipped for {skill_name}: {e}")


class SkillChallengerEvaluator:
    """Champion/challenger evaluation for SKILL VERSIONS (ADR-0004 B2.3) —
    the exact Wilson-bound machinery evaluate_challengers applies to strategy
    strings, generalized to versioned skill implementations recorded by
    SkillOutcomeTracker. This evaluator only flips labels from accumulated
    production outcomes; it never writes code. With no challengers registered
    (today's state: builtin champions only), every cycle is a clean no-op —
    it activates the day a forged/skill-creator challenger is registered.

    Thresholds mirror evaluate_challengers: promotion needs sample >= 20 and
    a Wilson bound strictly above the champion's; a challenger at >= 20
    samples with a bound below half the champion's is retired.
    """

    MIN_SAMPLE = 20
    RETIRE_RATIO = 0.5

    @classmethod
    async def run_cycle(cls, client_id: int = 0) -> dict:
        """Evaluate every skill with an active champion + challengers.
        Returns {"promoted": [...], "retired": [...]}. Never raises."""
        promoted, retired = [], []
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT v.skill_name, v.id AS version_id, v.version_label,
                          COUNT(o.id) AS n,
                          SUM(CASE WHEN o.outcome = 'success' THEN 1 ELSE 0 END) AS wins
                   FROM skill_versions v
                   LEFT JOIN skill_outcomes o ON o.version_id = v.id
                   WHERE v.active = 1
                   GROUP BY v.skill_name, v.id, v.version_label"""
            )
            by_skill: dict = {}
            for r in (rows or []):
                version = dict(r)
                version["n"] = int(version["n"] or 0)
                version["wilson"] = wilson_lower_bound(int(version["wins"] or 0), version["n"])
                by_skill.setdefault(version["skill_name"], []).append(version)

            for skill, versions in by_skill.items():
                champion = next((v for v in versions if v["version_label"] == "champion"), None)
                challengers = [v for v in versions if v["version_label"].startswith("challenger")]
                if not champion or not challengers:
                    continue
                for challenger in sorted(challengers, key=lambda v: v["wilson"], reverse=True):
                    if challenger["n"] < cls.MIN_SAMPLE:
                        continue
                    if challenger["wilson"] > champion["wilson"]:
                        await DatabaseManager.query(
                            "UPDATE skill_versions SET version_label = 'retired', active = 0 WHERE id = ?",
                            (champion["version_id"],))
                        await DatabaseManager.query(
                            "UPDATE skill_versions SET version_label = 'champion' WHERE id = ?",
                            (challenger["version_id"],))
                        rationale = (
                            f"Challenger Wilson {challenger['wilson']:.3f} (n={challenger['n']}) beat "
                            f"champion {champion['wilson']:.3f} (n={champion['n']})."
                        )
                        await log_improvement("skill", f"{skill}:{challenger['version_id']}", "promoted", rationale, client_id)
                        await log_improvement("skill", f"{skill}:{champion['version_id']}", "retired", rationale, client_id)
                        promoted.append(challenger["version_id"])
                        retired.append(champion["version_id"])
                        logger.info(f"[SKILL_CHALLENGER] Promoted {challenger['version_id']} over {champion['version_id']} for '{skill}'")
                        champion = challenger  # remaining challengers face the new champion
                    elif champion["wilson"] > 0 and challenger["wilson"] < champion["wilson"] * cls.RETIRE_RATIO:
                        await DatabaseManager.query(
                            "UPDATE skill_versions SET active = 0 WHERE id = ?",
                            (challenger["version_id"],))
                        await log_improvement(
                            "skill", f"{skill}:{challenger['version_id']}", "retired",
                            f"Wilson {challenger['wilson']:.3f} vs champion {champion['wilson']:.3f} "
                            f"at n={challenger['n']} (< half the champion with sufficient sample).",
                            client_id)
                        retired.append(challenger["version_id"])
                        logger.info(f"[SKILL_CHALLENGER] Retired {challenger['version_id']} for '{skill}'")
        except Exception as e:
            logger.error(f"[SKILL_CHALLENGER] cycle failed: {e}")
        return {"promoted": promoted, "retired": retired}


class OutcomeTracker:
    @classmethod
    async def record_outcome(cls, action: str, strategy: str, result: str, recipient: str = "", lead_id: int = 0, quality_score: float = 100.0, client_id: int = 0, metadata: dict = None):
        """Record an outreach outcome in the database."""
        now = datetime.datetime.now()
        meta_str = json.dumps(metadata) if metadata else "{}"
        try:
            await DatabaseManager.query(
                """INSERT INTO outreach_outcomes (action, strategy, recipient, lead_id, result, quality_score, send_hour, send_day, metadata, client_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (action, strategy, recipient, lead_id, result, quality_score, now.hour, now.weekday(), meta_str, client_id)
            )
            logger.info(f"[OUTCOME_TRACKER] Recorded outcome: action={action}, strategy={strategy}, result={result}")
        except Exception as e:
            logger.error(f"[OUTCOME_TRACKER] Failed to record outcome: {e}")

    @classmethod
    async def get_strategy_performance(cls, strategy_type: str, window_days: int = 7, client_id: int = 0) -> list:
        """Get win rates grouped by strategy values within a time window."""
        logger.info(f"[OUTCOME_TRACKER] Getting strategy performance for {strategy_type} ({window_days}d window)")
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT strategy,
                          COUNT(*) as total_sent,
                          SUM(CASE WHEN result='replied' THEN 1 ELSE 0 END) as replies,
                          SUM(CASE WHEN result='meeting' THEN 1 ELSE 0 END) as meetings,
                          SUM(CASE WHEN result='opened' THEN 1 ELSE 0 END) as opens,
                          SUM(CASE WHEN result='bounced' THEN 1 ELSE 0 END) as bounces
                   FROM outreach_outcomes
                   WHERE action='email_sent' AND client_id=?
                     AND datetime(created_at) >= datetime('now', ?)
                   GROUP BY strategy""",
                (client_id, f"-{window_days} days")
            )
            results = []
            for row in rows:
                sent = row["total_sent"]
                replies = row["replies"] or 0
                meetings = row["meetings"] or 0
                win_rate = (replies + meetings) / sent if sent > 0 else 0.0
                results.append({
                    "strategy": row["strategy"],
                    "total_sent": sent,
                    "replies": replies,
                    "meetings": meetings,
                    "opens": row["opens"] or 0,
                    "bounces": row["bounces"] or 0,
                    "win_rate": round(win_rate, 4),
                })
            return results
        except Exception as e:
            logger.error(f"[OUTCOME_TRACKER] Error getting strategy performance: {e}")
            return []

    @classmethod
    async def select_strategy(cls, strategy_type: str, client_id: int = 0, epsilon: float = 0.15) -> dict:
        """Champion/challenger selection (epsilon-greedy).

        85% of the time returns the champion (best Wilson bound); 15% of the
        time returns a random other active strategy so challengers keep
        collecting sample on a small cohort instead of starving.
        """
        import random
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT strategy_value, win_rate, sample_size, confidence, wilson_score
                   FROM learned_strategies
                   WHERE strategy_type = ? AND client_id = ? AND active = 1
                   ORDER BY wilson_score DESC, sample_size DESC""",
                (strategy_type, client_id)
            )
            if not rows:
                return {"strategy_value": None, "win_rate": 0.0, "sample_size": 0, "confidence": "none", "role": "none"}
            champion = rows[0]
            challengers = rows[1:]
            if challengers and random.random() < epsilon:
                pick = random.choice(challengers)
                role = "challenger"
            else:
                pick = champion
                role = "champion"
            return {
                "strategy_value": pick["strategy_value"],
                "win_rate": pick["win_rate"],
                "sample_size": pick["sample_size"],
                "confidence": pick["confidence"],
                "role": role,
            }
        except Exception as e:
            logger.error(f"[OUTCOME_TRACKER] select_strategy failed: {e}")
            return {"strategy_value": None, "win_rate": 0.0, "sample_size": 0, "confidence": "error", "role": "none"}

    @classmethod
    async def get_best_strategy(cls, strategy_type: str, client_id: int = 0) -> dict:
        """Get the top performing strategy with confidence interval."""
        logger.info(f"[OUTCOME_TRACKER] Getting best strategy for {strategy_type}")
        try:
            row = await DatabaseManager.fetchone(
                """SELECT strategy_value, win_rate, sample_size, confidence
                   FROM learned_strategies
                   WHERE strategy_type = ? AND client_id = ? AND active = 1
                   ORDER BY wilson_score DESC, sample_size DESC
                   LIMIT 1""",
                (strategy_type, client_id)
            )
            if row:
                return {
                    "strategy_value": row["strategy_value"],
                    "win_rate": row["win_rate"],
                    "sample_size": row["sample_size"],
                    "confidence": row["confidence"],
                }
            return {"strategy_value": None, "win_rate": 0.0, "sample_size": 0, "confidence": "none"}
        except Exception as e:
            logger.error(f"[OUTCOME_TRACKER] Error getting best strategy: {e}")
            return {"strategy_value": None, "win_rate": 0.0, "sample_size": 0, "confidence": "error"}


class StrategyOptimizer:
    # Industry baselines for cold start — based on B2B cold email benchmarks
    INDUSTRY_BASELINES = {
        "pas": 0.18,   # Pain-Agitate-Solve: 18% avg reply rate
        "bab": 0.22,   # Before-After-Bridge: 22% avg reply rate
        "aida": 0.15,  # Attention-Interest-Desire-Action: 15% avg reply rate
    }

    def __init__(self):
        self.ai = UnifiedAIClient()

    async def optimize_niche_targeting(self, client_id: int = 0) -> str:
        """Rank niches by ROI and persist the best performer."""
        logger.info("[STRATEGY_OPTIMIZER] Optimizing niche targeting...")
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT niche,
                          COUNT(*) as total_sent,
                          SUM(CASE WHEN result='replied' THEN 1 ELSE 0 END) as replies,
                          SUM(CASE WHEN result='meeting' THEN 1 ELSE 0 END) as meetings
                   FROM outreach_outcomes
                   WHERE action='email_sent' AND client_id=? AND niche IS NOT NULL AND niche != ''
                   GROUP BY niche""",
                (client_id,)
            )
            best_niche = ""
            best_roi = 0.0
            for row in rows:
                niche = row["niche"]
                sent = row["total_sent"]
                replies = row["replies"] or 0
                meetings = row["meetings"] or 0
                roi = (replies + meetings * 3) / sent if sent > 0 else 0.0  # meetings weighted 3x
                confidence = "low"
                if sent >= 20:
                    confidence = "high"
                elif sent >= 5:
                    confidence = "medium"
                strat_id = f"niche_{niche}"
                await DatabaseManager.query(
                    """INSERT OR REPLACE INTO learned_strategies (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id)
                       VALUES (?, 'niche', ?, ?, ?, ?, 1, ?)""",
                    (strat_id, niche, roi, sent, confidence, client_id)
                )
                if roi > best_roi:
                    best_roi = roi
                    best_niche = niche
            logger.info(f"[STRATEGY_OPTIMIZER] Optimized niche: {best_niche or 'none'} (ROI: {best_roi:.2f})")
            return best_niche
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error optimizing niche targeting: {e}")
            return ""

    async def generate_improvement_report(self, best_framework: str, best_hour: int, best_niche: str, client_id: int = 0) -> str:
        """Generate an AI-written summary of what changed and why."""
        logger.info("[STRATEGY_OPTIMIZER] Generating improvement report...")
        prompt = (
            f"You are the OROVA AI Strategy Analyst. Write a brief, data-driven improvement report "
            f"summarizing the following optimizations:\n\n"
            f"- Optimal email framework: {best_framework.upper()}\n"
            f"- Optimal send hour: {best_hour}:00\n"
            f"- Best performing niche: {best_niche or 'N/A'}\n\n"
            f"Write like the operator of a $100M company reviewing test results: state which "
            f"strategy is winning, what the data says, and the one change being shipped because "
            f"of it. 3-4 blunt sentences. No hedging, no filler, decisions over descriptions."
        )
        try:
            report = await self.ai.write(prompt)
            return report.strip()
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error generating report: {e}")
            return "Optimization cycle completed. Check learned_strategies table for updated performance data."

    async def optimize_email_framework(self, client_id: int = 0) -> str:
        """Analyze outreach outcomes by email strategy/framework and save the best one."""
        logger.info("[STRATEGY_OPTIMIZER] Optimizing email frameworks...")
        try:
            # Query outcome counts by strategy
            rows = await DatabaseManager.fetchall(
                """SELECT strategy, 
                          COUNT(*) as total_sent,
                          SUM(case when result='replied' then 1 else 0 end) as replies
                   FROM outreach_outcomes 
                   WHERE action='email_sent' AND client_id=?
                   GROUP BY strategy""",
                (client_id,)
            )
            
            best_framework = "pas"  # default
            best_win_rate = 0.0

            # Cold start: seed with industry baselines if no data
            if not rows:
                logger.info("[STRATEGY_OPTIMIZER] No email framework data — seeding industry baselines")
                for framework, baseline_rate in self.INDUSTRY_BASELINES.items():
                    strat_id = f"email_framework_{framework}"
                    await DatabaseManager.query(
                        """INSERT OR IGNORE INTO learned_strategies
                           (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id)
                           VALUES (?, 'email_framework', ?, ?, 0, 'baseline', 1, ?)""",
                        (strat_id, framework, baseline_rate, client_id)
                    )
                return "pas"  # default until real data arrives
            
            for row in rows:
                strategy = row["strategy"]
                sent = row["total_sent"]
                replies = row["replies"] or 0
                win_rate = replies / sent if sent > 0 else 0.0
                wilson = wilson_lower_bound(replies, sent)

                confidence = "low"
                if sent >= 20:
                    confidence = "high"
                elif sent >= 5:
                    confidence = "medium"

                # Insert or update learned strategies
                strat_id = f"email_framework_{strategy}"
                await DatabaseManager.query(
                    """INSERT OR REPLACE INTO learned_strategies (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id, wilson_score)
                       VALUES (?, 'email_framework', ?, ?, ?, ?, 1, ?, ?)""",
                    (strat_id, strategy, win_rate, sent, confidence, client_id, wilson)
                )

                # Champion by Wilson bound, not raw rate (small-sample safe)
                if wilson > best_win_rate:
                    best_win_rate = wilson
                    best_framework = strategy
                    
            logger.info(f"[STRATEGY_OPTIMIZER] Optimized email framework: {best_framework} (win rate: {best_win_rate:.2f})")
            return best_framework
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error optimizing email framework: {e}")
            return "pas"

    async def optimize_send_timing(self, client_id: int = 0) -> int:
        """Find the best hour of the day for higher reply rates."""
        logger.info("[STRATEGY_OPTIMIZER] Optimizing send timing...")
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT send_hour, 
                          COUNT(*) as total_sent,
                          SUM(case when result='replied' then 1 else 0 end) as replies
                   FROM outreach_outcomes 
                   WHERE action='email_sent' AND client_id=?
                   GROUP BY send_hour""",
                (client_id,)
            )
            
            best_hour = 10  # default 10:00 AM
            best_win_rate = 0.0
            
            for row in rows:
                hour = row["send_hour"]
                sent = row["total_sent"]
                replies = row["replies"] or 0
                win_rate = replies / sent if sent > 0 else 0.0
                wilson = wilson_lower_bound(replies, sent)

                confidence = "low"
                if sent >= 15:
                    confidence = "high"
                elif sent >= 5:
                    confidence = "medium"

                strat_id = f"send_timing_{hour}"
                await DatabaseManager.query(
                    """INSERT OR REPLACE INTO learned_strategies (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id, wilson_score)
                       VALUES (?, 'send_timing', ?, ?, ?, ?, 1, ?, ?)""",
                    (strat_id, str(hour), win_rate, sent, confidence, client_id, wilson)
                )

                if wilson > best_win_rate:
                    best_win_rate = wilson
                    best_hour = hour
                    
            logger.info(f"[STRATEGY_OPTIMIZER] Optimized optimal send hour: {best_hour}:00")
            return best_hour
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error optimizing send timing: {e}")
            return 10

    async def prune_dead_leads(self, threshold_days: int = 14, client_id: int = 0) -> str:
        """
        Identify dead/stale leads.
        Does NOT auto-prune. Instead, compiles a list of candidates and proposes
        them to the CEO via Telegram for approval.
        """
        logger.info("[STRATEGY_OPTIMIZER] Finding stale leads for pruning...")
        try:
            # Query leads with no activity for threshold_days
            rows = await DatabaseManager.fetchall(
                """SELECT id, business, owner, email, status, updated_at 
                   FROM leads 
                   WHERE client_id = ? 
                   AND status IN ('Email Sent', 'Contacted', 'New') 
                   AND datetime(updated_at) < datetime('now', ?)""",
                (client_id, f"-{threshold_days} days")
            )
            
            if not rows:
                return "No stale leads found."
                
            lead_list = []
            lead_ids = []
            for row in rows:
                lead_list.append(f"• {row['business']} ({row['owner']}) — last active {row['updated_at']}")
                lead_ids.append(row["id"])
                
            # Propose pruning to CEO via Telegram
            stale_leads_text = "\n".join(lead_list[:15])
            if len(lead_list) > 15:
                stale_leads_text += f"\n...and {len(lead_list) - 15} more leads."
                
            proposal_msg = (
                f"🗑️ **Stale Leads Pruning Proposal**\n\n"
                f"Nova has identified **{len(lead_list)}** leads with zero activity in {threshold_days}+ days.\n\n"
                f"**Stale Leads:**\n{stale_leads_text}\n\n"
                f"Would you like me to archive these leads? Reply with `/approve_pruning` to confirm."
            )
            
            # Save the proposal state to state_store
            await DatabaseManager.set_state("pending_prune_lead_ids", lead_ids)
            await _send_telegram_alert(proposal_msg)
            
            return f"Proposed archiving of {len(lead_list)} stale leads."
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error proposing lead pruning: {e}")
            return f"Error proposing lead pruning: {e}"


class ImprovementLoop:
    def __init__(self):
        self.optimizer = StrategyOptimizer()
        self.ai = UnifiedAIClient()

    async def evaluate_challengers(self, strategy_type: str, client_id: int = 0) -> list:
        """Promote-or-retire cycle for the champion/challenger system.

        A challenger with enough sample (>=20 sends) whose Wilson bound is
        less than half the champion's gets retired (active=0) — it stops
        receiving the exploration traffic. Promotion is implicit: rankings
        use the Wilson bound, so a challenger that beats the champion simply
        becomes the champion on the next selection.
        """
        retired = []
        try:
            rows = await DatabaseManager.fetchall(
                """SELECT id, strategy_value, sample_size, wilson_score
                   FROM learned_strategies
                   WHERE strategy_type = ? AND client_id = ? AND active = 1
                   ORDER BY wilson_score DESC""",
                (strategy_type, client_id)
            )
            if len(rows) < 2:
                return retired
            champion_wilson = rows[0]["wilson_score"] or 0.0
            if champion_wilson <= 0:
                return retired
            for row in rows[1:]:
                sample = row["sample_size"] or 0
                wilson = row["wilson_score"] or 0.0
                if sample >= 20 and wilson < champion_wilson * 0.5:
                    await DatabaseManager.query(
                        "UPDATE learned_strategies SET active = 0 WHERE id = ?",
                        (row["id"],)
                    )
                    retired.append(row["strategy_value"])
                    logger.info(f"[IMPROVEMENT_LOOP] Retired underperforming {strategy_type} '{row['strategy_value']}' (wilson {wilson:.3f} vs champion {champion_wilson:.3f}, n={sample})")
                    # Deterministic rationale (not an extra LLM call): the
                    # numbers ARE the reason, and this must work LLM-dead.
                    await log_improvement(
                        "strategy", f"{strategy_type}:{row['strategy_value']}", "retired",
                        f"Wilson {wilson:.3f} vs champion {champion_wilson:.3f} at n={sample} "
                        f"(< half the champion with sufficient sample).",
                        client_id,
                    )
        except Exception as e:
            logger.error(f"[IMPROVEMENT_LOOP] evaluate_challengers failed: {e}")
        return retired

    async def run(self, client_id: int = 0):
        """Main self-improvement loop runner.
        Aggregates outcomes → runs optimizations → persists strategies → logs changes.
        """
        logger.info("[IMPROVEMENT_LOOP] Running self-improvement cycle...")

        # 1. Run optimizations
        best_framework = await self.optimizer.optimize_email_framework(client_id)
        best_hour = await self.optimizer.optimize_send_timing(client_id)
        best_niche = await self.optimizer.optimize_niche_targeting(client_id)

        # 1.5 Evaluate challengers: retire proven losers, keep exploring the rest
        retired = []
        for stype in ("email_framework", "send_timing"):
            retired.extend(await self.evaluate_challengers(stype, client_id))
        
        # 2. Propose stale leads for pruning
        prune_proposal = await self.optimizer.prune_dead_leads(threshold_days=14, client_id=client_id)
        
        # 3. Generate AI-written improvement report
        report_text = await self.optimizer.generate_improvement_report(
            best_framework=best_framework,
            best_hour=best_hour,
            best_niche=best_niche,
            client_id=client_id
        )
        
        # 4. Send weekly learning report to Telegram
        retired_note = f"\n\n🧪 Retired strategies: {', '.join(retired)}" if retired else ""
        await _send_telegram_alert(f"📈 **Nova Learning Report**\n\n{report_text}\n\n🗑️ Stale leads: {prune_proposal}{retired_note}")
