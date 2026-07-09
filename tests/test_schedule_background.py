"""Regression tests for app.main._schedule_background.

The old implementation had two defects, both live-observed as the
`RuntimeWarning: coroutine '_StateRepo.set_state' was never awaited` noise in
every pytest run:

1. When no event loop was available, the caller's already-created coroutine
   was silently dropped un-awaited — the state write never happened and the
   warning fired at GC time.
2. `loop.create_task(coro)` was called from whatever thread invoked
   `_append_log` (logging handlers run on worker threads), but create_task is
   only legal from the loop's own thread — the thread-safe
   `run_coroutine_threadsafe` branch was unreachable while the loop ran.

These tests pin the fixed contract: dispose cleanly when unschedulable,
create_task only on the loop's own thread, threadsafe hand-off otherwise.
"""
import asyncio
import inspect
import threading
import concurrent.futures

from app import main as app_main


async def _noop_marker(flag: dict):
    flag["ran"] = True


def _restore_background_loop(original):
    app_main.BACKGROUND_LOOP = original


def test_no_loop_closes_coroutine_instead_of_leaking():
    original = app_main.BACKGROUND_LOOP
    app_main.BACKGROUND_LOOP = None
    try:
        flag = {}
        coro = _noop_marker(flag)
        result = app_main._schedule_background(coro)
        assert result is None
        # The fix's contract: an unschedulable coroutine is close()d, which is
        # what suppresses the 'never awaited' RuntimeWarning at GC time.
        assert inspect.getcoroutinestate(coro) == "CORO_CLOSED"
        assert "ran" not in flag  # nothing to run it on — skipped, not half-run
    finally:
        _restore_background_loop(original)


def test_same_thread_running_loop_uses_create_task():
    original = app_main.BACKGROUND_LOOP

    async def run():
        app_main.BACKGROUND_LOOP = asyncio.get_running_loop()
        flag = {}
        handle = app_main._schedule_background(_noop_marker(flag))
        assert isinstance(handle, asyncio.Task)
        await handle
        assert flag.get("ran") is True

    try:
        asyncio.run(run())
    finally:
        _restore_background_loop(original)


def test_foreign_thread_routes_through_run_coroutine_threadsafe():
    """A caller on a different thread than the loop's must get a
    concurrent.futures.Future (the threadsafe path), and the coroutine must
    actually execute on the loop."""
    original = app_main.BACKGROUND_LOOP
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    try:
        app_main.BACKGROUND_LOOP = loop
        flag = {}
        handle = app_main._schedule_background(_noop_marker(flag))
        assert isinstance(handle, concurrent.futures.Future)
        handle.result(timeout=5)
        assert flag.get("ran") is True
    finally:
        _restore_background_loop(original)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()


def test_stopped_loop_closes_coroutine():
    """A loop that exists but isn't running is unschedulable — the old code
    would hand it to run_coroutine_threadsafe and the write would hang
    forever; the fix disposes the coroutine instead."""
    original = app_main.BACKGROUND_LOOP
    loop = asyncio.new_event_loop()
    try:
        app_main.BACKGROUND_LOOP = loop
        coro = _noop_marker({})
        assert app_main._schedule_background(coro) is None
        assert inspect.getcoroutinestate(coro) == "CORO_CLOSED"
    finally:
        _restore_background_loop(original)
        loop.close()
