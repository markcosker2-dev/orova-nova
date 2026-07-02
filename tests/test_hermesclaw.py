# Run this after any change to verify nothing broke:
# python -m pytest tests/test_hermesclaw.py -v

"""
HermesClaw Test Suite
=====================
Verifies all 3 components: Email Proofreader, CEO Brain, Self-Improvement Loop.
Plus: Lead scoring, database tables, planner registration, worker lanes.
"""
import sys
import os
import asyncio
import sqlite3
import importlib
import inspect
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Fix 1: Email Proofreader ──────────────────────────────────────

class TestEmailProofreader:
    def test_imports(self):
        from app.skills.email_proofreader import proofread_email
        assert asyncio.iscoroutinefunction(proofread_email)

    def test_verdict_types(self):
        """Any verdict must be one of the three allowed values."""
        from app.skills.email_proofreader import proofread_email
        src = inspect.getsource(proofread_email)
        assert "pass" in src
        assert "rewrite" in src
        assert "reject" in src

    def test_proofread_rejects_on_llm_failure(self):
        """If the LLM is completely broken, the proofreader must REJECT, not silently pass."""
        async def run():
            from app.skills.email_proofreader import proofread_email
            with patch("app.skills.email_proofreader.UnifiedAIClient") as MockAI:
                instance = MockAI.return_value
                instance.extract = AsyncMock(side_effect=Exception("LLM down"))
                result = await proofread_email(
                    to="test@example.com",
                    subject="Test",
                    body="Test body",
                    recipient_context=""
                )
                assert result["verdict"] == "reject", f"Expected reject, got {result['verdict']}"
                assert result["score"] == 0.0
                assert "BLOCKED" in result["fixes"]
        asyncio.run(run())

    def test_proofread_parses_valid_json(self):
        """When LLM returns valid JSON, parse it correctly."""
        async def run():
            from app.skills.email_proofreader import proofread_email
            with patch("app.skills.email_proofreader.UnifiedAIClient") as MockAI:
                instance = MockAI.return_value
                mock_response = json.dumps({
                    "verdict": "pass",
                    "score": 92,
                    "fixes": "None",
                    "improved_subject": "Hi John",
                    "improved_body": "Hi John, quick question..."
                })
                instance.extract = AsyncMock(return_value=mock_response)
                result = await proofread_email(
                    to="john@example.com",
                    subject="Hey",
                    body="Hey there",
                    recipient_context=""
                )
                assert result["verdict"] == "pass"
                assert result["score"] == 92.0
        asyncio.run(run())

    def test_proofread_extracts_json_from_wrapped_text(self):
        """When LLM wraps JSON in markdown, extract it."""
        async def run():
            from app.skills.email_proofreader import proofread_email
            with patch("app.skills.email_proofreader.UnifiedAIClient") as MockAI:
                instance = MockAI.return_value
                mock_response = '```json\n{"verdict":"rewrite","score":65,"fixes":"Too formal","improved_subject":"Hey!","improved_body":"Quick question"}\n```'
                instance.extract = AsyncMock(return_value=mock_response)
                result = await proofread_email(
                    to="test@example.com",
                    subject="Hey",
                    body="Body",
                    recipient_context=""
                )
                assert result["verdict"] == "rewrite"
                assert result["score"] == 65.0
        asyncio.run(run())


# ── Fix 2: CEO Brain ──────────────────────────────────────────────

class TestCEOBrain:
    def test_imports(self):
        from app.core.ceo_brain import CEOBrain
        assert hasattr(CEOBrain, "morning_brief")
        assert hasattr(CEOBrain, "pipeline_health_check")
        assert hasattr(CEOBrain, "propose_tasks")
        assert hasattr(CEOBrain, "auto_schedule_day")
        assert hasattr(CEOBrain, "cancel_auto_execute")
        assert hasattr(CEOBrain, "_execute_tasks")
        assert hasattr(CEOBrain, "get_status")

    def test_pipeline_health_check(self):
        """Verify pipeline_health_check returns health_score and alerts.
        Mocks DatabaseManager to avoid hitting real DB schema issues."""
        async def run():
            from app.core.ceo_brain import CEOBrain
            # Patch both get_metrics (classmethod) and fetchone (async classmethod)
            with patch("app.core.ceo_brain.DatabaseManager.get_metrics", return_value={
                "leads_found": 25, "emails_sent": 50,
                "replies_received": 5, "meetings_booked": 1, "calls_made": 0
            }) as mock_get_metrics, \
                 patch("app.core.ceo_brain.DatabaseManager.fetchone", new_callable=AsyncMock, return_value={"cnt": 0}) as mock_fetchone, \
                 patch("app.core.ceo_brain.DatabaseManager.fetchall", new_callable=AsyncMock, return_value=[]) as mock_fetchall:
                brain = CEOBrain()
                health = await brain.pipeline_health_check()
                assert "health_score" in health
                assert "alerts" in health
                assert isinstance(health["health_score"], (int, float))
                assert isinstance(health["alerts"], list)
        asyncio.run(run())

    def test_morning_brief_delegates_to_get_status(self):
        """morning_brief should use get_status to build the status section."""
        import inspect as _ins
        from app.core.ceo_brain import CEOBrain
        src = _ins.getsource(CEOBrain.morning_brief)
        assert "get_status" in src or "is_fresh" in src, "morning_brief should check for fresh start"


# ── Fix 3: Self-Improvement Loop ──────────────────────────────────

class TestSelfImprovement:
    def test_imports(self):
        from app.core.self_improvement import OutcomeTracker, StrategyOptimizer, ImprovementLoop
        assert OutcomeTracker is not None
        assert StrategyOptimizer is not None
        assert ImprovementLoop is not None

    def test_database_tables_exist(self):
        db = sqlite3.connect("app/orova.db")
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        db.close()
        assert "outreach_outcomes" in tables, "outreach_outcomes table missing"
        assert "learned_strategies" in tables, "learned_strategies table missing"

    def test_industry_baselines_seeded(self):
        """StrategyOptimizer should have industry baselines for cold start."""
        from app.core.self_improvement import StrategyOptimizer
        src = inspect.getsource(StrategyOptimizer)
        assert "pas" in src.lower() or "PAS" in src, "Missing PAS baseline"
        assert "bab" in src.lower() or "BAB" in src, "Missing BAB baseline"


# ── Planner Registration ──────────────────────────────────────────

class TestPlannerRegistration:
    def test_proofread_in_outreach_tools(self):
        """proofread_email must be in OUTREACH_TOOLS (class attribute on TaskPlanner)."""
        import re as _re
        import inspect
        from app.core.planner import TaskPlanner
        src = inspect.getsource(TaskPlanner)
        # Find OUTREACH_TOOLS = [...] and check if proofread_email is inside
        match = _re.search(r'OUTREACH_TOOLS\s*=\s*\[(.*?)\]', src, _re.DOTALL)
        assert match, "OUTREACH_TOOLS list not found in TaskPlanner"
        outreach_tools_content = match.group(1)
        assert "proofread_email" in outreach_tools_content, \
            f"proofread_email not found in OUTREACH_TOOLS. Found: {outreach_tools_content[:200]}"

    def test_planner_imports_proofread(self):
        """Verify the planner imports proofread_email.

        The planner lazy-loads skills via _LazyModule for startup performance,
        so accept either a direct import or the lazy-module registration.
        """
        import inspect
        from app.core import planner
        src = inspect.getsource(planner)
        direct_import = "from app.skills.email_proofreader import proofread_email" in src
        lazy_import = (
            '_LazyModule("app.skills.email_proofreader"' in src
            and '"proofread_email"' in src
        )
        assert direct_import or lazy_import, (
            "planner must import proofread_email (directly or via _LazyModule)"
        )


# ── Worker Lanes ───────────────────────────────────────────────────

class TestWorkerLanes:
    def test_lane6_ceo_brain_exists(self):
        from app.worker import ceo_brain_job
        assert callable(ceo_brain_job)

    def test_lane7_health_check_exists(self):
        from app.worker import health_check_job
        assert callable(health_check_job)

    def test_lane8_self_improvement_exists(self):
        from app.worker import self_improvement_job
        assert callable(self_improvement_job)

    def test_lane9_sequence_drip_exists(self):
        from app.worker import sequence_drip_job
        assert callable(sequence_drip_job)

    def test_all_lanes_registered_in_source(self):
        """Verify all 9 lanes are registered via schedule."""
        import inspect
        from app import worker
        src = inspect.getsource(worker)
        assert "Lane 6" in src or "lane_6" in src.lower() or "17:00" in src
        assert "Lane 7" in src or "lane_7" in src.lower() or "health_check_job" in src
        assert "Lane 8" in src or "lane_8" in src.lower() or "self_improvement_job" in src
        assert "Lane 9" in src or "lane_9" in src.lower() or "sequence_drip_job" in src


# ── Lead Scoring ──────────────────────────────────────────────────

class TestLeadScoring:
    def test_good_lead_passes(self):
        from app.skills.smart_scraper import score_lead_for_orova
        lead = {
            "name": "John Smith",
            "email": "john@luxurytile.com",
            "phone": "555-123-4567",
            "source": "apollo_browser"
        }
        result = score_lead_for_orova(lead)
        assert result["filter_decision"] in ("PASS", "BORDERLINE")
        assert result["orova_score"] >= 5

    def test_minimal_lead_gets_lower_score(self):
        """A lead with minimal info should score lower than a fully qualified lead."""
        from app.skills.smart_scraper import score_lead_for_orova
        good_lead = {
            "name": "John Smith",
            "email": "john@luxurytile.com",
            "phone": "555-123-4567",
            "source": "apollo_browser"
        }
        minimal_lead = {
            "name": "",
            "email": "info@company.com",
            "phone": "",
            "source": "html"
        }
        good = score_lead_for_orova(good_lead)
        bad = score_lead_for_orova(minimal_lead)
        assert good["orova_score"] > bad["orova_score"], \
            f"Good lead ({good['orova_score']}) should score higher than minimal lead ({bad['orova_score']})"


# ── Runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))