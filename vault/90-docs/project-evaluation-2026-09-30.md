---
name: project-evaluation-2026-09-30
description: Measured project regressions and material OROVA corrections; local readiness is not live delivery.
type: audit
created: 2026-09-30
status: active
tags: [nova, engineering, evaluation, zero-budget]
---

# OROVA project evaluation — September 30, 2026

Mark requested a whole-project review using the newly selected Codex model.
Model benchmarks are not settings to enable. The practical evaluation is
repeatable project tests, meaningful failure controls, independent source review
and an explicit boundary between prepared source and operating services.

Work is on `codex/zero-budget-repair`, carried in existing draft
[PR #201](https://github.com/markcosker2-dev/orova-nova/pull/201). No merge,
Render deployment, live Retell edit, booking, prospect contact or Instagram
publication is part of this evaluation. The $0 constraint is unchanged; Nova's
provider configuration has not been switched to a paid OpenAI API.

## Corrections

| Area | Reproduced defect and local correction |
|---|---|
| Permissions | Expired and consumed approvals could be reopened. Enforce one creation-time 24-hour lifetime, terminal responses and persisted single-use consumption. Failed state reads/writes block permission; serialized initialization avoids duplicate IDs and overwritten requests. |
| Outcome truth | `/outcome` acknowledged failed writes and accepted invalid/other-client IDs. Require a positive existing OROVA lead and confirmed canonical event insertion; report a failed status projection separately. |
| Prospect fit and counts | Explicit med spas passed the canonical gate; database outages appeared as zero leads. Enforce ADR-0015 in canonical eligibility and expose metric availability in Telegram, AI context and dashboard. |
| Sheets | Concurrent lookups could allocate the same new row. Serialize lookup, allocation and write across supported in-process scheduler/API loops; cancellation cannot release an active write. This is not a distributed lock. |
| Backup | Overlapping backups shared/deleted scratch snapshots. Use unique worker-owned snapshots, a read-only existing source, WAL-safe SQLite backup and closed upload streams, with failure/cancellation cleanup tests. This does not repair live OAuth. |
| Learning and recovery | Multi-statement SQLite DDL silently failed. Execute trusted statements separately and expose errors. Both restore branches ensure event/learning schemas; auxiliary failures do not erase a valid restored snapshot. |
| Retell contract | Verified mode named retired Cal functions, and a healthy draft could clear stale/mixed phone routes. Use current Cal tool names and validate exact published production agent/LLM pins, tags and every active weighted route. Draft inspection always holds traffic. |
| Dashboard | Fake activity, obsolete cron events, fallback zero counts and disconnected controls could appear operational. Show recorded/configured/unverified states honestly, fetch calendar tasks once, escape saved titles and block false launch/send/approval acknowledgements. |
| Business/social instructions | Remove unsupported response-time guarantees and the cold-email/cold-call funnel from consumed business context. Preserve internal prices and owner offer control. Caption validation now rereads the active Sheets queue, not the retired Make data store. |
| Repeatable evaluation | Add full/focused CLI checks and bounded JSON timings/results; missing tools fail closed and current environment values override stale local values. Dashboard behavior/syntax now runs in CI without npm dependencies. |
| Test isolation | Full-suite failures exposed legacy route fixtures entering real startup/shutdown and CSV persistence. Disable dotenv loading before collection, bypass production lifespan and mock CSV durability. A module-local outcome facade and explicit backup-worker completion avoid cross-test logging/work contamination without weakening failure assertions. |

## Verification

The corrected complete run at 21:04 Singapore time passed **1,711 Python tests**
(28 warnings; pytest 146.95 seconds), **six dashboard tests**, canonical facts,
secret scan and narrow security lint. Twelve audit/fix leaf gates were
independently reverified. Independent audit and fix gates were authored before work,
reviewed by the driver and reverified. New safety cases include positive controls
and failures observed against original source; selected existing tests were
corrected where they wrongly required med-spa targeting or an unmeasured speed
promise. The duration-linter test now uses isolated synthetic copy and proves
both the latency exception and real duration drift.

Earlier full runs used the old route fixtures and cannot certify absence of
background/live attempts. Their two reproducible integration failures were
investigated rather than waived; only the corrected isolated run is final
verification evidence. No deliberate live launch, send, publication or deployment
was requested/performed by the review workflow.

Use `python scripts/nova.py benchmark` for the full local suite; `--focused`
is the iteration profile. Add `--report .unlazy/benchmark.json` for bounded
measurements. Reports exclude raw provider data and test logs. These checks are
not model benchmark scores, end-to-end browser testing, proof of live deployment,
a full production restore or customer conversion evidence.

## Fresh live evidence and remaining gates

- Public `/health` at about 18:44 Singapore time reported build `bd33ab8ffbab`,
  database/memory OK. That build is not this repair branch.
- September 30 GET-only Retell production inspection returned **HOLD: five
  hard blocks**: exact production binding, missing production tag, unpublished
  returned agent, unpublished returned LLM and remaining legacy Cal tools.
  Default `prod` can pass only exact machine traffic checks; `--version 1` or
  `staging` can inspect a draft but always returns exit 2 and holds traffic.
  Simulations, booking/web/phone tests and actual funding/owner approval remain
  separate launch requirements. No Retell setting changed.
- Last complete-backup evidence (September 28) was `invalid_grant`; it was not
  refreshed or repaired here. Sheets represents selected lead fields, not
  approvals, events, suppressions, conversations and learning state. Deployment
  remains held until a fresh complete backup and restore evidence are verified.
- Work cloud access to ChatCut is not established by this laptop's installation.
  No schedule or queue changed here. Reels with unavailable cloud tooling or
  unverified commercial media/voice rights remain drafts.
- Commercial scope, price, term and payment need Mark's actual decision before
  a paying client is closed. Tests and internal catalog values are not proof of
  an approved offer, prospect reply, booked meeting or first client.

Next business action: prepare one individual, fact-checked builder DM for Mark's
review and manual send, without the held demo number or invented proof. Record
the actual send/reply in the existing tracker and diagnose the bottleneck.

Linked: [[2026-09-30-project-benchmarks-and-safety-fixes]] · [[active-context]]
