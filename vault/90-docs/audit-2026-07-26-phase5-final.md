---
name: audit-2026-07-26-phase5-final
description: Phase 5 final report — what was fixed, what was decided, what was removed, what is still uncertain
type: doc
created: 2026-07-26
status: active
---

# Phase 5 Final Report — Orova Nova overhaul (2026-07-26)

Branch `chore/system-audit-2026-07-26`. Phase 1 audit: [[audit-2026-07-26-phase1]].

## 🔴 Read this first

**The system has never completed a full prospect-conversation loop end-to-end.
Zero prospect conversations have ever happened.**

Nothing in this overhaul moves that number. What gates it is **B6** (SerpAPI
exhausted, so no leads can be discovered) and **B5** (no booking tool, so a
"yes" cannot become a meeting) — and neither is a code fix. Every item below
made the system more reliable or cheaper to maintain. None of them made it
*sell anything*.

## Clean-run confirmation

```
pytest tests                609 passed, 15 warnings      (was 563)
compile_knowledge --check   OK — canonical facts valid, no drift
compileall app scripts      exit 0
```

`pytest` with no arguments now collects the same scope CI does.

---

## What was broken and how it was fixed

### B1 · Concurrency guard that guarded nothing (the urgent one)
`app/core/semaphore.py` declared itself *"the single source of truth for all
RAM-heavy skill concurrency control. Ensures Render (512MB RAM) is protected
from OOM kills"* — and **was imported by nothing**, while three call sites each
hard-coded their own magic number. There is live history of an OOM kill wiping
the disk mid-run, so the guard meant to prevent a repeat was inert.

**Root cause was not "duplicate copies".** My first framing was wrong and I
corrected it before acting: the four semaphores do *different jobs* — the global
one would serialise whole operations, the local three bound fan-out *inside* one
operation. They were never duplicates.

Fixed by **deleting** the global module (see the architecture decision below) and
centralising the fan-out caps in `hardening.py` beside `memory_monitor`.

**Second bug found while in there:** the crawl semaphore was `Semaphore(10)`
while `light_enrich` builds a page list of at most 5 (7 on the fallback path) —
so it never blocked and guarded nothing at all. Now 4, which actually binds. A
test fails if any `app/skills` module hard-codes `Semaphore(<literal>)` again.

### B4 · Two "failing tests" — fixed at root cause, not symptom
`test_free_orova.py` and `test_auth.py` are **manual smoke scripts misnamed
`test_*.py`**. The first has a `main()` runner and `async def` checks with no
marker; the second has *no test functions at all* — it fires httpx requests at
`http://127.0.0.1:18790` as module-level side effects, so merely **collecting**
it attempts live network calls. Neither was ever meant to be collected, and CI
runs `pytest tests/`, so both rotted invisibly.

Adding asyncio markers would have treated the symptom. Added `pytest.ini` with
`testpaths = tests` instead, so a bare `pytest` matches CI. This also closes the
Phase 1 finding that **no pytest config existed anywhere**.

### B2 · Email opt-outs were detected but never honoured
**I got this finding wrong in Phase 1 and corrected it.** I reported the system
sends cold email with *"zero CAN-SPAM logic live."* False —
`agentmail_skill._apply_compliance_footer` already appends an idempotent CAN-SPAM
footer with an opt-out line, called from `send_outreach`.

So `compliance.py` was **not** wired in. Doing so would have created a *third*
owner of CAN-SPAM validation beside working live code — the exact divergence this
repo has been bitten by before.

The real gap was narrower and on the other channel: the reply classifier
**detected** opt-out language and marked the thread COLD (so nothing auto-replied)
but nothing **persisted** it, and `send_outreach` had no pre-send check. A later
drip cycle could therefore email someone who had explicitly asked to be left
alone — breaking the promise the footer itself makes, and the same defect already
fixed for the phone channel.

Fixed both halves: `is_email_suppressed` / `add_email_suppression` in `dnc.py`
beside the phone gate (fail-closed), a pre-send gate in `send_outreach`, and
recording on an opt-out reply. `is_optout_reply` is now public so the reply lane
reads the **same** keyword list rather than a second copy.

### Q4 · Procfile `worker:` line
Declared a process that exits 1 by design (`worker.py:1148` guards the
duplicate-scheduler bug), so it could never start. Removed.

---

## Architectural decisions

### B1 — global semaphore vs local fan-out caps → **delete the global one**
| Option | Verdict |
|---|---|
| Adopt `ram_guarded` (limit 1) globally | **Rejected.** Serialises whole lanes past Render's 30s request kill, and **deadlocks** wherever one guarded coroutine awaits another (`enrich_lead_lite` → `_fetch_page`). |
| Delete it, keep locals untouched | Rejected — leaves a no-op guard and fixes nothing real. |
| **Delete it; `memory_monitor` is canonical; centralise the caps; make the crawl cap bind** | **Chosen.** |

`memory_monitor` already existed, was already used, measures real RSS, and is
what the re-enrich lane checks after the OOM incident. Extension-first says
extend the abstraction that exists and works rather than adopt a parallel one
that never ran.

### B3 — `app/config.py` → **Option C** (owner-approved)
The stated premise ("one missing field, 135 LOC") did not survive measurement:

- `secret_key` crashes the import and **nothing reads `SECRET_KEY`**
- 39 declared fields vs **62 env vars actually used**; **55 absent** from it
- stale LLM defaults (a Cerebras `scheduler_llm` that is not the live chain)
- adopting it means migrating **106 `os.getenv` call sites** through the
  revenue-pipeline core, where a boot failure costs a SQLite wipe

Decisive argument: **typing would not have prevented a single config failure this
system has had.** All three were config that *silently did nothing* —
`BUSINESS_POSTAL_ADDRESS` unset, `enable_voicemail_detection` retired by Retell,
`WA_SOS_ENABLED` gating a dead endpoint.

So `config.py` and `pydantic-settings` are gone, replaced by an
`ENV_CAPABILITIES` contract in `hardening.py` that names the **capability** each
var gates and reports at boot which are switched off. Absent *optional* config
never marks the system unhealthy — on a $0 stack that would peg `/health`
unhealthy forever and make the signal worthless.

**It paid for itself immediately.** Run against the real environment it reports
**7/13 capabilities live** and independently rediscovered the
`BUSINESS_POSTAL_ADDRESS` gap that previously took manual code reading, plus the
missing booking link (B5), CALICO, Verifalia and the national DNC scrub.

---

## What was removed, and why it was safe

| Removed | Evidence |
|---|---|
| `app/core/semaphore.py` (56 LOC) | Imported by nothing; its design would deadlock if adopted. Replaced by `CONCURRENCY_LIMITS` + the already-used `memory_monitor`. |
| `app/config.py` (135 LOC) | Raised on import, so nothing *could* use it. Covered 39 of 62 vars. Replaced by the capability contract. |
| `pydantic-settings==2.14.2` | Sole consumer was `app/config.py`. |
| `Procfile` `worker:` line | Declared a process that exits 1 by design. |
| `tenacity==8.3.0` | **Not yet removed** — flagged safe in Phase 1 (unused; `hardening.py:53` provides `async_retry`) but left in place to keep this branch's dependency change to the one tied to a deleted module. |

Two tests assert the deletions stay deleted, so a future session cannot quietly
reintroduce the divergence.

**Nothing touching auth, payments or user data was removed.** Related positive
finding: `require_dashboard_api_key` **fails closed** — an unset
`DASHBOARD_API_KEY` returns 503, never open access.

---

## Still uncertain / needs your input

### ⛔ Q2 — unanswered twice, so 9 root scripts were left untouched
`diagnose_ai.py`, `cleanup_db.py`, `sanity_check_sheets.py`, `check_auth.py`,
`hunt_leads.py`, `health_check.py`, `test_auth.py`, `test_free_orova.py`,
`claude-desktop-prompt.txt`, `start_nova*.bat`, `orova_worker.service`.

Zero references from `app/`, `scripts/`, `tests/`, Dockerfile, Procfile or CI —
but **a script you run by hand looks identical to dead code from a grep**. Per
your own guidance ("leaving them alone costs nothing; deleting a script you
needed does") they stay. They are now harmless: `pytest.ini` stops the two
misnamed test files being collected.

### B5 — no booking tool on either Retell agent
Needs a Cal.com event from you. **I will not guess at a config that books real
meetings.** Current behaviour is correct meanwhile: a "yes" is captured as email
+ two preferred times and flagged.

### B6 — SerpAPI exhausted (250/250, 0 left)
Verified against SerpAPI's account API. **No reset date is exposed** by that API
— it reports usage but no reset timestamp, so assume the 1st of the month. The
durable fix is [[0014-licence-registries-as-the-discovery-source|ADR-0014]].

### `BUSINESS_POSTAL_ADDRESS` — owner action, now loudly reported
Cold email currently ships an opt-out but **no physical postal address**, which
15 U.S.C. §7704 requires. One env var.

### `compliance.py` and `warmup.py` — kept, not wired, not deleted
`compliance.py` (374 LOC) is a richer CAN-SPAM/GDPR/CASL/PECR library that
duplicates the live footer; wiring it would create a second owner, and its
GDPR/CASL/PECR parts are not needed for US-only outreach. `warmup.py` (462 LOC)
stays deferred until a sending domain exists, per your instruction. Neither is
deleted; both are now documented so a future session does not mistake them for
cruft.

### Not audited at all
This was static analysis plus targeted live verification, **not a security
review**. Still unexamined: XSS in `mission-control/` (lead data is scraped from
the public web and rendered in the dashboard), unauthenticated mutating
endpoints, and blocking I/O inside `async def` handlers. Two attempts at a
parallel agent audit failed on session limits. **Do not read "609 tests passing"
as "no bugs" — six real bugs were found today in code that was already shipped
and green.**

## Linked
- [[audit-2026-07-26-phase1]] · [[0014-licence-registries-as-the-discovery-source]] · [[session-2026-07-26-merge-and-discovery-wall]] · [[active-context]]
