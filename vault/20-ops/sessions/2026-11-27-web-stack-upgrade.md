---
name: session-2026-11-27-web-stack-upgrade
description: Claude Code session — fastapi/starlette/anyio security upgrade, pool-reset deadlock fix, SIGTERM hijack fix
type: session
created: 2026-11-27
status: done
---

# Session: web stack upgrade (2026-11-27)

Status of everything below: **local/tested → committed** (branch
`claude/epic-pasteur-1oinda`, draft PR). **Not merged, not deployed, not
live-verified.** Deploy needs Mark's approval and a verified backup first.

## What changed

1. **Security upgrade.** `requirements.txt` pins `fastapi==0.165.0`,
   `starlette==1.10.0`, `anyio==4.16.0` (was 0.104.1 / 0.27.0 / 3.7.1).
   `pip-audit -r requirements.txt -s pypi`: **17 known vulns → 0** (14
   starlette, 2 anyio, 1 fastapi). `httpx` stays `0.27.2` for mcp/ollama; its
   comment now says the starlette-0.27 TestClient reason is gone.
   `pip check` clean.
2. **Pool-reset deadlock (the boot hang).** `_init_sqlite_fallback` refilled
   the *same* bounded queue with blocking `put()`. After
   `_close_all_connections` drained it, threads still holding connections
   returned them, so the 10th `put()` blocked forever in the failed-restore
   branch of the lifespan. Reproduced: **2 of 8** clean credential-less boots
   hung on the new stack. Fix in `app/core/_db_base.py`: build a fresh queue
   and swap it in, and track the current generation's connections
   (`_live_conns`). A connection checked out before a reset or Drive swap is
   now **closed on return**, not pooled. It points at a deleted file; the old
   code silently re-pooled it. After the fix: **28 of 28** boots healthy.
3. **SIGTERM was hijacked. Pre-existing, reproduced on the old stack too.**
   `DatabaseManager.register_sigterm_handler` called
   `loop.add_signal_handler(SIGTERM, _close_all_connections)` on uvicorn's
   loop. That **replaces uvicorn's handler**. SIGTERM only closed the pool
   under the running app. uvicorn never shut down, and the lifespan shutdown
   (including the **shutdown Drive backup**) never ran, so Render SIGKILLs it
   after the grace period. Removed. The pool is now closed explicitly at the
   end of the lifespan, *after* the shutdown backup. (uvicorn re-raises SIGTERM
   after a graceful shutdown, which skips `atexit`, and exits with 143.) This
   is very likely why the shutdown backup was **"still not firing after two
   fixes"** (the `exec uvicorn` Dockerfile fix was necessary but not
   sufficient). That is a hypothesis until a live redeploy shows
   `💾 Shutdown backup: True` in Render logs.

## Verification (local, credential-less boot, no `.env`)

- `/health` 200 (db ok); `/` serves "OROVA Mission Control". `/api/leads` is
  403 with no key and with a wrong key. Static-mount traversal probes
  (`../`, `%2e%2e`, `..%2f`, `..%5c`) all return 404, with no file content.
- SIGTERM → exits in ~2 s; log order: shutdown backup attempted (False, no
  creds) → pool closed → "graceful shutdown complete".
- Full suite **1,838 passed, 1 skipped**. 5 new tests in
  `tests/test_db_pool_reset_deadlock.py`; the two deadlock tests fail on the
  old pool code. `compile_knowledge --check`, `check_secrets`, and the CI ruff
  security lint all pass.

## Follow-ups

- [ ] Mark: review/merge the PR; deploy only after a verified Drive backup.
- [ ] After deploy: check Render logs on the *next* redeploy for
      `Shutdown backup: True` and "graceful shutdown complete". That confirms
      or refutes item 3 as the shutdown-backup root cause.
- [ ] Telegram `/restore` swaps the DB at runtime but never re-inits the pool,
      so the app runs on overflow connections until the restart its reply
      promises. Not a regression (it used to re-pool stale connections to the
      deleted file, which is worse). The restart itself is not automated.
