"""Tests for ADR-0004 Phase 1 — vault-context injection, skill-outcome
tracking, the improvement changelog, and their API/vault-sync surfaces.

Per the ADR's ship criteria: vault_context fail-open + cap behavior,
SkillOutcomeTracker.record, plus the new endpoints and vault_pull helpers.
Mirrors the test style of test_owner_finder.py / test_hermesclaw.py:
plain asyncio.run + unittest.mock, fully offline.
"""
import asyncio
import importlib.util
import inspect
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from app.core import vault_context
from app.core import self_improvement


# ── vault_context (A1): fail-open + caps ────────────────────────────────────

def test_missing_vault_dir_returns_empty_string(tmp_path):
    with patch.object(vault_context, "VAULT_DIR", tmp_path / "does-not-exist"):
        assert vault_context.get_vault_context() == ""


def test_reads_always_read_notes_with_per_note_cap(tmp_path):
    brain = tmp_path / "10-brain"
    brain.mkdir(parents=True)
    (brain / "active-context.md").write_text("ACTIVE-MARKER " + "x" * 5000, encoding="utf-8")
    (brain / "strategy-snapshot.md").write_text("STRATEGY-MARKER", encoding="utf-8")
    with patch.object(vault_context, "VAULT_DIR", tmp_path):
        digest = vault_context.get_vault_context()
    assert "ACTIVE-MARKER" in digest
    assert "STRATEGY-MARKER" in digest
    assert len(digest) <= vault_context.MAX_TOTAL_CHARS


def test_niche_note_is_included_when_present(tmp_path):
    (tmp_path / "10-brain").mkdir(parents=True)
    skills = tmp_path / "50-skills"
    skills.mkdir()
    (skills / "find_leads.md").write_text("NICHE-NOTE-MARKER", encoding="utf-8")
    with patch.object(vault_context, "VAULT_DIR", tmp_path):
        digest = vault_context.get_vault_context(niche="find_leads")
    assert "NICHE-NOTE-MARKER" in digest


def test_unreadable_vault_fails_open(tmp_path):
    with patch.object(vault_context, "VAULT_DIR", tmp_path), \
         patch.object(Path, "exists", side_effect=RuntimeError("fs exploded")):
        assert vault_context.get_vault_context() == ""


# ── SkillOutcomeTracker (B1/B2.1) ────────────────────────────────────────────

def test_record_registers_builtin_version_and_inserts_outcome():
    query = AsyncMock()
    with patch("app.core.self_improvement.DatabaseManager.query", query):
        asyncio.run(self_improvement.SkillOutcomeTracker.record(
            "find_leads", "success", latency_ms=123.4, client_id=0))
    assert query.await_count == 2  # INSERT OR IGNORE version row + outcome row
    version_sql = query.await_args_list[0].args[0]
    outcome_args = query.await_args_list[1].args[1]
    assert "INSERT OR IGNORE INTO skill_versions" in version_sql
    assert outcome_args[0] == "find_leads"
    assert outcome_args[1] == "find_leads.builtin"
    assert outcome_args[2] == "success"


def test_record_with_explicit_version_skips_registration():
    query = AsyncMock()
    with patch("app.core.self_improvement.DatabaseManager.query", query):
        asyncio.run(self_improvement.SkillOutcomeTracker.record(
            "find_leads", "error", version_id="find_leads.a1b2c3"))
    assert query.await_count == 1
    assert query.await_args.args[1][1] == "find_leads.a1b2c3"


def test_record_never_raises_on_db_failure():
    with patch("app.core.self_improvement.DatabaseManager.query",
               AsyncMock(side_effect=RuntimeError("db down"))):
        asyncio.run(self_improvement.SkillOutcomeTracker.record("x", "success"))


# ── improvement_log (A2.2) ──────────────────────────────────────────────────

def test_log_improvement_inserts_row():
    query = AsyncMock()
    with patch("app.core.self_improvement.DatabaseManager.query", query):
        asyncio.run(self_improvement.log_improvement(
            "strategy", "email_framework:aida", "retired", "Wilson 0.1 vs 0.3", 0))
    sql, params = query.await_args.args
    assert "INSERT INTO improvement_log" in sql
    assert params[:3] == ("strategy", "email_framework:aida", "retired")


def test_log_improvement_swallows_db_errors():
    with patch("app.core.self_improvement.DatabaseManager.query",
               AsyncMock(side_effect=RuntimeError("db down"))):
        asyncio.run(self_improvement.log_improvement("skill", "x", "promoted"))


def test_retiring_a_challenger_writes_improvement_log():
    rows = [
        {"id": "champ", "strategy_value": "bab", "sample_size": 100, "wilson_score": 0.30},
        {"id": "loser", "strategy_value": "aida", "sample_size": 25, "wilson_score": 0.05},
    ]
    log_mock = AsyncMock()
    with patch("app.core.self_improvement.DatabaseManager.fetchall",
               AsyncMock(return_value=rows)), \
         patch("app.core.self_improvement.DatabaseManager.query", AsyncMock()), \
         patch("app.core.self_improvement.log_improvement", log_mock):
        retired = asyncio.run(self_improvement.ImprovementLoop().evaluate_challengers("email_framework"))
    assert retired == ["aida"]
    log_mock.assert_awaited_once()
    assert log_mock.await_args.args[2] == "retired"


# ── API endpoints (A2) ──────────────────────────────────────────────────────

def test_api_skill_health_computes_win_rate_and_wilson():
    from app.core.hermesclaw_endpoints import api_skill_health
    rows = [{"skill_name": "find_leads", "version_id": "find_leads.builtin",
             "n": 40, "wins": 30, "avg_latency_ms": 850.0, "last_used": "2026-07-10"}]
    with patch("app.core.hermesclaw_endpoints.DatabaseManager.fetchall",
               AsyncMock(return_value=rows)):
        result = asyncio.run(api_skill_health())
    skill = result["skills"][0]
    assert skill["win_rate"] == 0.75
    assert 0 < skill["wilson"] < 0.75  # lower bound is strictly below the point rate


def test_api_improvement_log_passes_since_id():
    from app.core.hermesclaw_endpoints import api_improvement_log
    fetchall = AsyncMock(return_value=[])
    with patch("app.core.hermesclaw_endpoints.DatabaseManager.fetchall", fetchall):
        result = asyncio.run(api_improvement_log(since_id=42))
    assert result == {"status": "ok", "entries": []}
    assert fetchall.await_args.args[1][0] == 42


# ── planner wiring (source-level, matching the suite's pattern for the
#    heavy execution path) ───────────────────────────────────────────────────

def test_planner_tool_loop_records_skill_outcomes():
    from app.core import planner
    src = inspect.getsource(planner)
    assert "SkillOutcomeTracker.record" in src


def test_planner_injects_vault_context():
    from app.core import planner
    src = inspect.getsource(planner)
    assert "get_vault_context" in src
    assert "VAULT BRAIN" in src


def test_ddl_defines_the_three_new_tables():
    from app.core import _db_base
    src = inspect.getsource(_db_base)
    for table in ("skill_versions", "skill_outcomes", "improvement_log"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in src


# ── vault_pull helpers ──────────────────────────────────────────────────────

def _load_vault_pull():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("vault_pull", root / "scripts" / "vault_pull.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_health_markdown_has_frontmatter_and_rows():
    vp = _load_vault_pull()
    md = vp._skill_health_markdown([
        {"skill_name": "find_leads", "version_id": "find_leads.builtin",
         "n": 40, "win_rate": 0.75, "wilson": 0.6, "avg_latency_ms": 850.0,
         "last_used": "2026-07-10"},
    ])
    assert md.startswith("---")
    assert "name: skill-health" in md
    assert "| find_leads |" in md
    assert "75.0%" in md


def test_append_improvement_entries_is_idempotent_by_id(tmp_path):
    vp = _load_vault_pull()
    note = tmp_path / "improvement-log.md"
    entries = [
        {"id": 1, "subject_type": "strategy", "subject_name": "email_framework:aida",
         "action": "retired", "rationale": "Wilson 0.05 vs 0.30", "created_at": "2026-07-10 12:00:00"},
        {"id": 2, "subject_type": "skill", "subject_name": "find_leads",
         "action": "promoted", "rationale": "", "created_at": "2026-07-10 13:00:00"},
    ]
    assert vp._append_improvement_entries(note, entries) == 2
    assert vp._append_improvement_entries(note, entries) == 0  # same ids: no dupes
    later = entries + [{"id": 3, "subject_type": "strategy", "subject_name": "send_timing:9",
                        "action": "retired", "rationale": "r", "created_at": "2026-07-11 09:00:00"}]
    assert vp._append_improvement_entries(note, later) == 1
    content = note.read_text(encoding="utf-8")
    assert content.count("`#1`") == 1 and content.count("`#3`") == 1
    assert "name: improvement-log" in content
