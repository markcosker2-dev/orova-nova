"""Legacy disconnected controls must not report started, sent or rejected work."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.parametrize("handler", ["run_pipeline_action", "approve_email", "deny_email"])
def test_disconnected_dashboard_controls_fail_honestly_without_writes(handler, tmp_path, monkeypatch):
    with patch("dotenv.load_dotenv", return_value=False):
        from app import main
    monkeypatch.setattr(main, "root_path", str(tmp_path))
    content = tmp_path / "content.json"
    original = '[{"id":"synthetic-email","status":"draft"}]'
    content.write_text(original, encoding="utf-8")
    request = SimpleNamespace(json=AsyncMock(return_value={"id": "synthetic-email", "pipeline": "full_outreach"}))

    result = asyncio.run(getattr(main, handler)(request, authorized=True))
    assert result["status"] == "blocked"
    assert "not connected" in result["message"]
    assert content.read_text(encoding="utf-8") == original
