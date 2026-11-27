"""The container must deliver Render's SIGTERM to uvicorn (2026-11-26).

The lifespan shutdown hook uploads a DB snapshot before Render's ephemeral disk
is discarded. With `CMD ["sh", "-c", "uvicorn ..."]` dash stays PID 1 and never
forwards SIGTERM, so that hook silently never ran on deploys.
"""
import json
import re
from pathlib import Path


def _cmd():
    text = Path(__file__).resolve().parent.parent.joinpath("Dockerfile").read_text()
    lines = [line for line in text.splitlines() if line.startswith("CMD ")]
    assert len(lines) == 1, "expected exactly one CMD"
    return json.loads(lines[0][4:])


def test_uvicorn_is_execed_so_it_receives_sigterm():
    cmd = _cmd()
    if cmd[:2] == ["sh", "-c"]:
        assert re.match(r"\s*exec\s+uvicorn\b", cmd[2]), cmd
    else:
        assert cmd[0] == "uvicorn", cmd


def test_graceful_shutdown_is_bounded_inside_renders_grace_window():
    """Unbounded, uvicorn waits for every open request before the lifespan
    shutdown backup runs, and Render kills it at ~30s (2026-11-27)."""
    cmd = " ".join(_cmd())
    m = re.search(r"--timeout-graceful-shutdown\s+(\d+)", cmd)
    assert m, "uvicorn must bound its graceful shutdown"
    backup_cap = 20  # asyncio.wait_for(backup_database(), timeout=20) in app/main.py
    assert int(m.group(1)) + backup_cap < 30, "must finish inside Render's ~30s SIGTERM grace"
