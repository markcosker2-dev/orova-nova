"""Tests for real sub-agent delegation via dispatch_task (WP3)."""
import asyncio
from unittest.mock import patch, AsyncMock

from app.core import agent_router


def test_unknown_agent_is_rejected():
    res = asyncio.run(agent_router.dispatch_task("do something", "bogus"))
    assert res["status"] == "error"
    assert "bogus" in res["response"]


def test_empty_task_is_rejected():
    res = asyncio.run(agent_router.dispatch_task("", "hawk"))
    assert res["status"] == "error"


def test_known_agent_runs_scoped_planner_with_agent_id():
    fake_planner = AsyncMock()
    fake_planner.execute = AsyncMock(return_value={"status": "ok", "agent": "hawk", "response": "done"})
    with patch("app.core.planner.TaskPlanner", return_value=fake_planner), \
         patch("app.core.ai_client.UnifiedAIClient", return_value=object()):
        res = asyncio.run(agent_router.dispatch_task("find 3 luxury dealers", "hawk"))
    fake_planner.execute.assert_awaited_once()
    args, kwargs = fake_planner.execute.call_args
    assert args[0] == "find 3 luxury dealers"      # task passed through
    assert kwargs.get("agent_id") == "hawk"         # persona/scope keyed on this
    assert res["agent"] == "hawk"                    # real result, not a hardcoded string


def test_task_description_alias_is_accepted():
    fake_planner = AsyncMock()
    fake_planner.execute = AsyncMock(return_value={"status": "ok"})
    with patch("app.core.planner.TaskPlanner", return_value=fake_planner), \
         patch("app.core.ai_client.UnifiedAIClient", return_value=object()):
        asyncio.run(agent_router.dispatch_task(task_description="hunt dealers", agent="quill"))
    args, _ = fake_planner.execute.call_args
    assert "hunt dealers" in args[0]
