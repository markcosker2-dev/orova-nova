"""Deploy verification gate — /health reports the serving build SHA
(ADR-0010 step 1, 2026-07-21).

The incident that forced this: after the #88 merge, Render's deploy failed
silently and the OLD image kept serving HTTP 200 for hours. 200 alone is
never proof of a deploy; the SHA in /health is. Render injects
RENDER_GIT_COMMIT at runtime; BUILD_SHA is the manual fallback; "unknown"
means neither is set (local/dev).
"""
import os
from unittest.mock import patch

from tests.test_dashboard_api import _make_test_client


def _get_health(client):
    return client.get("/health").json()


def test_health_reports_render_git_commit():
    with patch.dict(os.environ, {"RENDER_GIT_COMMIT": "f5bb899deadbeefcafe1234"}):
        with _make_test_client() as client:
            body = _get_health(client)
    assert body["build"] == "f5bb899deadb"  # truncated to 12


def test_health_falls_back_to_build_sha_then_unknown():
    env = {k: v for k, v in os.environ.items()
           if k not in ("RENDER_GIT_COMMIT", "BUILD_SHA")}
    with patch.dict(os.environ, {**env, "BUILD_SHA": "abc123"}, clear=True):
        with _make_test_client() as client:
            assert _get_health(client)["build"] == "abc123"
    with patch.dict(os.environ, env, clear=True):
        with _make_test_client() as client:
            assert _get_health(client)["build"] == "unknown"
