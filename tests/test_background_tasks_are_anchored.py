"""A fire-and-forget task must be anchored, and its death must be audible.

asyncio holds only a WEAK reference to a running task. A task whose sole other
reference is a local in a request handler becomes collectable the moment that
handler returns, and the interpreter may destroy it mid-flight — the work never
happens.

Observed in production 2026-08-14: `POST /api/actions/hunt-leads` returned
`{"status":"ok","message":"Lead hunt job initiated"}` and produced **zero** log
lines. Not a traceback, not a warning — nothing, over six minutes, while the
root-logger buffer captured every other lane's heartbeat. The error callback
skipped it because a task torn down this way surfaces as CANCELLED, and the
callback read `if not t.cancelled() and t.exception()`.

So the endpoint reported success, did nothing, and said nothing about it.

Two guarantees pinned here:

1. the task is anchored for its whole life, then released (no leak)
2. cancellation is LOGGED rather than swallowed — the property whose absence
   made a silent no-op look like a working feature
"""
import asyncio

import pytest

from app import main as m


def test_a_kept_task_is_anchored_until_it_finishes():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def work():
            started.set()
            await release.wait()
            return "done"

        task = m._keep(asyncio.create_task(work()), "TEST")
        await started.wait()
        assert task in m._BACKGROUND_TASKS, "a running task must stay referenced"

        release.set()
        assert await task == "done"
        await asyncio.sleep(0)
        assert task not in m._BACKGROUND_TASKS, "a finished task must be released"

    asyncio.run(scenario())


def test_cancellation_is_logged_not_swallowed(caplog):
    """The property whose absence hid the bug."""
    async def scenario():
        async def work():
            await asyncio.sleep(30)

        task = m._keep(asyncio.create_task(work()), "HUNT")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    with caplog.at_level("ERROR"):
        asyncio.run(scenario())

    assert any("CANCELLED" in r.message for r in caplog.records), (
        "a cancelled background task must say so — silence is what cost six "
        "minutes of a hunt that never ran"
    )


def test_a_raising_task_still_reports(caplog):
    async def scenario():
        async def work():
            raise RuntimeError("boom")

        task = m._keep(asyncio.create_task(work()), "HUNT")
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

    with caplog.at_level("ERROR"):
        asyncio.run(scenario())

    assert any("boom" in r.message for r in caplog.records)


def test_the_anchor_set_does_not_leak_across_many_tasks():
    async def scenario():
        async def work():
            return 1

        tasks = [m._keep(asyncio.create_task(work()), "TEST") for _ in range(50)]
        await asyncio.gather(*tasks)
        await asyncio.sleep(0)
        assert not any(t in m._BACKGROUND_TASKS for t in tasks)

    asyncio.run(scenario())
