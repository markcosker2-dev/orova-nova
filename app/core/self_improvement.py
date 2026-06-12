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
    async def get_best_strategy(cls, strategy_type: str, client_id: int = 0) -> dict:
        """Get the top performing strategy with confidence interval."""
        logger.info(f"[OUTCOME_TRACKER] Getting best strategy for {strategy_type}")
        try:
            row = await DatabaseManager.fetchone(
                """SELECT strategy_value, win_rate, sample_size, confidence
                   FROM learned_strategies
                   WHERE strategy_type = ? AND client_id = ? AND active = 1
                   ORDER BY win_rate DESC, sample_size DESC
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
            f"Explain in 3-4 sentences why these strategies are winning and what it means "
            f"for the business. Use a professional but punchy tone suitable for a CEO Telegram update."
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
            
            for row in rows:
                strategy = row["strategy"]
                sent = row["total_sent"]
                replies = row["replies"] or 0
                win_rate = replies / sent if sent > 0 else 0.0
                
                confidence = "low"
                if sent >= 20:
                    confidence = "high"
                elif sent >= 5:
                    confidence = "medium"
                    
                # Insert or update learned strategies
                strat_id = f"email_framework_{strategy}"
                await DatabaseManager.query(
                    """INSERT OR REPLACE INTO learned_strategies (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id)
                       VALUES (?, 'email_framework', ?, ?, ?, ?, 1, ?)""",
                    (strat_id, strategy, win_rate, sent, confidence, client_id)
                )
                
                if win_rate > best_win_rate:
                    best_win_rate = win_rate
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
                
                confidence = "low"
                if sent >= 15:
                    confidence = "high"
                elif sent >= 5:
                    confidence = "medium"
                    
                strat_id = f"send_timing_{hour}"
                await DatabaseManager.query(
                    """INSERT OR REPLACE INTO learned_strategies (id, strategy_type, strategy_value, win_rate, sample_size, confidence, active, client_id)
                       VALUES (?, 'send_timing', ?, ?, ?, ?, 1, ?)""",
                    (strat_id, str(hour), win_rate, sent, confidence, client_id)
                )
                
                if win_rate > best_win_rate:
                    best_win_rate = win_rate
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
            _send_telegram_alert(proposal_msg)
            
            return f"Proposed archiving of {len(lead_list)} stale leads."
        except Exception as e:
            logger.error(f"[STRATEGY_OPTIMIZER] Error proposing lead pruning: {e}")
            return f"Error proposing lead pruning: {e}"


class ImprovementLoop:
    def __init__(self):
        self.optimizer = StrategyOptimizer()
        self.ai = UnifiedAIClient()

    async def run(self, client_id: int = 0):
        """Main self-improvement loop runner.
        Aggregates outcomes → runs optimizations → persists strategies → logs changes.
        """
        logger.info("[IMPROVEMENT_LOOP] Running self-improvement cycle...")
        
        # 1. Run optimizations
        best_framework = await self.optimizer.optimize_email_framework(client_id)
        best_hour = await self.optimizer.optimize_send_timing(client_id)
        best_niche = await self.optimizer.optimize_niche_targeting(client_id)
        
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
        _send_telegram_alert(f"📈 **Nova Learning Report**\n\n{report_text}\n\n🗑️ Stale leads: {prune_proposal}")
