---
name: audit-2026-07-26-phase1
description: Phase 1 system audit — read-only classification of every module into working / broken / dead / unclear
type: doc
created: 2026-07-26
status: active
---

# Phase 1 Audit — Orova Nova (2026-07-26)

Read-only. **No code changed.** Branch `chore/system-audit-2026-07-26`.
Baseline: `main` @ `fc3bfdd`, production `/health` = `fc3bfddf706c`, `db: ok`, `memory: ok`.

## Scope actually measured

| | |
|---|---|
| Tracked Python files | 156 (88 in `app/`, 53 in `tests/`) |
| `app/` LOC | 29,491 (`core/` 11,035 · `skills/` 15,264) |
| Declared dependencies | 29 |
| Entry point (deployed) | `uvicorn app.main:app` — Dockerfile + render.yaml, single free-tier web service |
| Scheduler | hand-rolled `threading.Thread` loop in `worker.py`, started from the FastAPI lifespan |

## Tooling run — all green

```
pytest tests            563 passed, 15 warnings
compile_knowledge --check   OK — canonical facts valid, no drift
compileall app scripts      exit 0 (no syntax errors)
```

**Gap: there is no linter and no type checker.** No `pyproject.toml`, `setup.cfg`,
`.flake8`, `.ruff.toml` or `mypy.ini` exists, and CI (`.github/workflows/ci.yml`)
runs only `pytest tests/ --maxfail=3 -q`. So "clean build" currently means
"tests pass" and nothing more.

---

## ✅ Working — verified, not assumed

Each of these was exercised against something real, not just imported:

- **Test suite + knowledge gate + compile** — above.
- **Ad-signal detector** (`light_enrich.detect_ad_signals`) — run against 9 live
  California remodeler homepages; ranks 2 hot / 2 warm / 5 cold.
- **Off-ICP hygiene gate** — verified in production logs: 6 rows quarantined on
  the `fc3bfdd` boot (`adolfoalsina.gov.ar`, `infobae.com`, `automotiveworld.com`,
  `autonews.com`, `bar.ca.gov`, `beta-cc.de`); visible leads 47 → 42.
- **WA L&I owner registry** (`owner_finder._wa_registry_lookup`) — validated
  against the live `data.wa.gov` Socrata API (75,515 ACTIVE rows, 100% owner +
  phone fill on a 1,000-row sample).
- **Retell outbound + inbound agents** — confirmed live via the Retell API:
  correct LLM version bound, webhook pointing at production.
- **Opt-out → DNC** — tested both call directions; suppression gate confirmed to
  block a suppressed number before dialling.
- **Dependency hygiene** — 29 deps, only 1 genuinely unused (below). Prior
  sessions already stripped ~150–250MB of heavy deps.

---

## 🔴 Broken — exists, intended to work, currently doesn't

Ranked by consequence.

### B1 · `app/core/semaphore.py` — OOM guard that nothing uses (56 LOC)
Its own docstring: *"Single source of truth for all RAM-heavy skill concurrency
control. Ensures Render (512MB RAM) is protected from OOM kills."*
**It is imported by nothing.** Meanwhile `lead_gen_v3.py:1252` and
`light_enrich.py:1178` each hand-roll a local `asyncio.Semaphore`.

Why this matters: there is live history of an OOM kill wiping the disk mid-run
(a limit-10 re-enrich). The module written to prevent exactly that is inert, and
the divergent local copies are the same pattern that previously produced three
drifting copies of a name check where the weakest let bad data through.

### B2 · `app/core/compliance.py` — CAN-SPAM/GDPR/CASL/PECR, never wired (374 LOC)
6 classes/functions, imported by nothing. `active-context` lists "CAN-SPAM
footer" as *next in queue*, so this is unfinished rather than abandoned.
The system sends cold email and makes cold calls today.
**Touches legal/compliance — do not delete. Needs wiring or an explicit deferral.**

### B3 · `app/config.py` — fails to import (135 LOC)
```
pydantic_core.ValidationError: secret_key
  Field required [type=missing]
```
Any module importing it would crash at import time. Nothing does, so it is dead
*and* broken. `pydantic-settings==2.14.2` is declared solely for this module.

### B4 · Root `test_free_orova.py` — 2 failing tests, invisible to CI
`test_free_ai` and `test_parallel_execution` fail with *"async def functions are
not natively supported"* (missing asyncio marker). CI runs `pytest tests/`, so
these never run there — but a bare `pytest` at the repo root collects and fails
them. Root `test_auth.py` collects 0 tests.

### B5 · Neither Retell agent can book a meeting
No booking tool configured on either LLM. A "yes" is captured as email + two
preferred times and flagged for manual handling. **Needs your Cal.com event —
I won't guess at a config that books real meetings.**

### B6 · SerpAPI exhausted — 250/250, 0 left (operational, not code)
Verified against SerpAPI's own account API. Automated discovery cannot run until
the monthly reset. This is the single biggest blocker on the system doing its
job, and no code change fixes it. Path forward is
[[0014-licence-registries-as-the-discovery-source|ADR-0014]].

---

## 🗑 Dead / unused

### Safe to remove — obvious, no approval needed
| Item | Size | Evidence |
|---|---|---|
| `app/core/hf_keep_awake.py` | 45 LOC | Hugging Face Spaces keep-awake pinger. Deployed on **Render**, not HF. No references anywhere. |
| `tenacity==8.3.0` | dep | Never imported. `hardening.py:53` provides `async_retry` instead. |

### ⚠️ Requires your go-ahead — config or non-obvious
| Item | Why flagged |
|---|---|
| `Procfile` line `worker: python app/worker.py` | **Config.** Declares a process that can never start — `worker.py:1148` exits 1 with *"re-introduces the duplicate-scheduler bug"*. Harmless today (free tier runs only `web`) but actively misleading. |
| `pydantic-settings==2.14.2` | Only consumer is the broken `app/config.py`. Removal depends on B3's outcome. |
| `python-multipart==0.0.31` | No `UploadFile`/`Form`/`File` usage in `app/`. Starlette imports it for form parsing regardless, so removal may be unsafe. **Unclear — left alone.** |
| 11 orphaned root scripts | `check_auth.py`, `cleanup_db.py`, `diagnose_ai.py`, `hunt_leads.py`, `sanity_check_sheets.py`, `health_check.py`, `test_auth.py`, `test_free_orova.py`, `claude-desktop-prompt.txt`, `start_nova.bat`, `start_nova_local.bat`, `orova_worker.service`. Zero references from `app/`, `scripts/`, `tests/`, Dockerfile, Procfile or CI. **But an operator script you run by hand looks identical to dead code from a grep** — see Unclear U2. Note `health_check.py` appeared referenced; that was a name collision with `health_check_job` / the `/health` endpoint, not an import. |
| `vault/90-docs/` stale docs | `FULL_CODE_EXPORT.md` (39KB code dump, 2026-07-04), `AUDIT_REPORT_2026.md`, `FINAL_AUDIT_REPORT.md`, `DEPLOYMENT_COMPLETE.md` — all pre-date the last three weeks of changes and will mislead. Documentation, so your call. |

### Not dead — checked and cleared
- `apscheduler==3.10.4` — **is** used (`app/main.py:114`, `AsyncIOScheduler`), despite `worker.py` hand-rolling its own loop.
- `requirements-mega.txt` — referenced only in `requirements.txt` comments as a deliberate parking lot for heavy optional deps. Intentional.
- `node_modules/` (5.4MB), `.claude/worktrees/` (983MB), `.kilo/` (75MB) — all gitignored and **untracked**. Local disk only; not in the repo or Docker image.

---

## ❓ Unclear — needs your input before I act

**U1 · `compliance.py` and `warmup.py` (836 LOC combined) — deferred or abandoned?**
Both are complete-looking, unwired features. `warmup.py` (email warmup /
deliverability) matches a documented deferral: *"build when a sending domain
exists."* `compliance.py` matches *"next in queue: CAN-SPAM footer."*
If deferred → leave, and I'll note them so no future session deletes them.
If abandoned → removal is 836 LOC, but compliance code touches legal exposure
and I will not delete it without you saying so explicitly.

**U2 · The 11 root scripts — do you run any by hand?**
`diagnose_ai.py`, `cleanup_db.py`, `sanity_check_sheets.py` and `check_auth.py`
read like operator tools. A grep cannot distinguish "manual tool" from "dead".
Tell me which you use and I'll remove the rest.

**U3 · `app/config.py` — repair or delete?**
It is a pydantic-settings central config that nothing uses and that crashes on
import. Two options: delete it (plus `pydantic-settings`), or fix it and adopt it
as the config layer. Current config is read ad-hoc via `os.getenv` throughout.
This is a genuine architecture question → Phase 3 candidate, not a bug fix.

**U4 · `Procfile` worker line — remove, or is a separate worker process planned?**
Only matters if you ever move off the single free-tier service.

---

## Phase 1 stop condition

Per the brief I am stopping here rather than proceeding to Phase 2, because both
triggers are met:

1. **Unclear items exist** (U1–U4).
2. **The dead list includes config** (`Procfile`, two dependencies) **and code
   touching compliance** (`compliance.py`).

## What Phase 2 would do on your go-ahead

Bounded, in this order, each its own PR with tests:

1. **B1** wire `semaphore.py` in, or delete it and keep the local semaphores —
   architecture call, so Phase 3 applies (see below).
2. **B4** move/fix or delete the root test files (smallest real bug).
3. **B3** per your U3 answer.
4. **B2** per your U1 answer — wiring compliance is a feature, not a fix.

**Phase 3 (architecture, not bug) applies to exactly two items:** B1 (global
concurrency control vs per-module semaphores) and B3/U3 (central typed config vs
ad-hoc `os.getenv`). Everything else is a straightforward bug or a deletion.
No comparison will be run on working modules.

## Honest limits of this audit

- It is **static analysis plus targeted live verification**, not a security
  review. I did not audit for XSS in `mission-control/`, unauthenticated
  mutating endpoints, or blocking I/O inside `async def` handlers. Those need a
  dedicated pass; two attempts at a parallel agent audit failed on session
  limits.
- "Working" above means *exercised*, not *proven correct*. Today alone, six real
  bugs were found in code that was already shipped and passing tests.
- The system has **never completed its core loop end-to-end** — zero prospect
  conversations have ever happened. No amount of code auditing changes that
  number, and it remains the only metric that matters.
