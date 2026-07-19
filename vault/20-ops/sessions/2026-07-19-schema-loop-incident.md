---
name: session-2026-07-19-schema-loop-incident
description: Prod incident found on Sunday return — restored old-schema snapshot wedged the scheduler in a 1 Hz loop, starving all lanes including backups
type: session
created: 2026-07-19
status: active
---

# 2026-07-19 — Schema-mismatch scheduler loop (found + fixed)

## What was observed

Step 0 of the [[session-2026-07-17-sunday-return-plan|Sunday return plan]]
(prod health check) found `/health` returning 200/Operational but `/api/logs`
showing a tight loop, repeating **every second**:

```
[LANE 7] Triggering Pipeline Health Check...
[+] Groq AI Client — READY
[+] Native Google Gemini Client — READY
[CEO_BRAIN] Running pipeline health check...
[DB] get_metrics failed: no such column: metric_key
[SCHED] Scheduler error: no such column: updated_at
```

This is a fresh proof of the standing rule: **a 200 on `/health` is not proof
of a healthy instance.** The loop had been burning the free-tier CPU and — much
worse — **starving every other lane, including Lane 5 (3-hourly Drive
backups)**, because the failing job aborts the whole `run_pending()` pass.

## Root cause (two compounding defects, mirroring the #61/#65 pattern)

1. **The restored Drive snapshot predates several columns**
   (`leads.updated_at`, `metrics.metric_key`, `metrics.recorded_at`,
   `state_store.updated_at`). `CREATE TABLE IF NOT EXISTS` leaves existing
   tables untouched, and the hand-maintained migration list in
   `_db_base.py::_migrate_columns` (a) was missing the metrics/state_store
   entries entirely, and (b) used `DEFAULT CURRENT_TIMESTAMP` in
   `ALTER TABLE ... ADD COLUMN`, which **SQLite rejects** (constant defaults
   only) — silently, because of a bare `except: pass`. So old snapshots could
   *never* converge to the current schema, and each 3-hourly backup re-saved
   the old shape: a permanently poisoned lineage.
2. **The `schedule` library advances a job's `next_run` only after the job
   function returns.** The Lane-7 health check raised on
   `datetime(updated_at)` (`ceo_brain.py:587`), so the lane stayed perpetually
   due → re-fired every 1-second tick → its raise aborted `run_pending()` so
   later-due lanes never ran.

Why nobody saw it on 07-15: Lane 7 first fires **2 hours after boot** — after
every post-deploy verification window closed.

## The fix (PR: `fix/restored-snapshot-schema-parity`)

- **Generic schema reconciler** replaces the hand list: the canonical schema
  now lives in one constant (`CANONICAL_SCHEMA_SQL`); `_migrate_columns`
  builds an in-memory reference DB from it and diffs `PRAGMA table_info` per
  table, ALTER-adding any missing column (falling back to no-DEFAULT when
  SQLite rejects a non-constant default, warning instead of silently passing).
  Migration-only columns (leads.email_status/owner_title/linkedin_url,
  memories.embedding, learned_strategies.wilson_score) were folded into the
  canonical CREATEs, so the schema has exactly one definition. Runs at boot
  AND after a Drive restore (both paths go through `_init_tables`).
- **`_safe_job` wrapper** around all 9 lane registrations in `worker.py`: a
  raising lane is contained and logged, `schedule` advances `next_run`, and
  one broken lane can no longer starve the rest.
- **7 regression tests** (`tests/test_schema_reconciler.py`) reproduce the
  exact prod-failing statements against an old-schema DB. Suite: 329 passing.
- Council cross-check (Gemini, sole configured provider): endorsed the
  desired-state reconciler; flagged only the known SQLite ALTER limits (no
  DROP/MODIFY — out of scope here). Response truncated on quota, per usual.

## Post-deploy verification (ADDITIONS to the standard checklist)

1. Standard: `Restored database snapshot` + `NOVA Gateway Online`, zero
   `malformed`.
2. **New:** boot logs should show `[DB MIGRATION] Added metrics.metric_key`,
   `Added state_store.updated_at`, `Added leads.updated_at` (first boot only —
   after the next 3h backup cycle the snapshot lineage is finally healed).
3. **New:** check logs again ≥2h after boot — Lane 7 must fire ONCE per 2h,
   no `[SCHED]` errors. The 07-15-era 5-minute check window is not enough.

## Consequences to note

- Backups very likely have NOT run since the loop began (window unknown; the
  restored data is the pre-existing 7 junk leads, so no real data is at risk
  this time — but this is why the fix precedes the first campaign).
- Batch this merge with PR #64 (scrapling/spacy pin) and PR #11 (jinja2
  security bump) per the Sunday plan — one merge window, one redeploy.

## Linked

- [[session-2026-07-17-sunday-return-plan]] · [[session-2026-07-15-sdr-refocus-handoff]]
- [[hermesclaw-orova-master]] §6 (deploy/restore history: #61, #65)
