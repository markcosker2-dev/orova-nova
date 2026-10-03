---
name: 2026-09-30-project-benchmarks-and-safety-fixes
description: Whole-project evaluation, measured local fixes and remaining live launch gates.
type: session
created: 2026-09-30
status: complete-local
tags: [nova, engineering, zero-budget, verification]
---

# Project benchmarks and safety fixes — September 30, 2026

Mark asked the current Codex model to evaluate and improve the entire project.
Published model benchmarks cannot be enabled as switches. Independent Nova,
reliability and business reviews were followed by regression-first corrections,
driver source review and integrated project checks. The Unlazy skill organized
ownership and independent verification; the OROVA operator skill preserved the
$0 budget, launch gates and this Obsidian closeout.

## Measured local result

At 21:04 Singapore time the corrected complete profile passed:

- **1,711 Python tests**, 28 warnings, 146.95 seconds reported by pytest.
- **6 dashboard JavaScript behavior/syntax tests**.
- Canonical knowledge compilation, secret scan and narrow security lint passed.
- Six audit/fix leaves were independently reverified (12 leaf gates).

Run `python scripts/nova.py benchmark` for the full suite, or add `--focused`
for iterations and `--report .unlazy/benchmark.json` for bounded measurements.
The report deliberately contains no raw provider data. Missing required tools
fail closed. These are project checks, not public model benchmark scores,
browser end-to-end tests, production restore evidence or customer results.

## Material corrections

Approval expiry, replay, persistence failures and concurrent initialization now
fail safely. Outcomes require an existing OROVA lead and confirmed event write.
Med spas remain excluded under ADR-0015. Telegram and dashboard no longer turn
unavailable counts into observed zero leads. Dashboard shows configured agents
rather than invented work, and disconnected buttons cannot claim sends/launches.

Sheets lookup/allocation/write is serialized in-process, including cancellation
and separate-loop coverage. Backup workers own unique WAL-safe snapshots and
close upload streams before cleanup. Learning DDL now initializes real SQLite
tables/indexes; both restore branches bootstrap auxiliary schemas without
erasing a valid restored database on auxiliary failure. These are not a
distributed lock or a repair of live Drive authorization.

Retell readiness now requires exact published production agent/LLM bindings,
assigned tags and every active phone route; a good draft cannot clear traffic.
Verified prompts use current Cal functions. Consumed business context removes
unsupported speed guarantees and the cold-email/cold-call funnel. Caption
instructions use the active Sheets queue, not retired Make data-store records.

Two full-suite integration failures exposed legacy route tests entering real
startup/shutdown and CSV durability, plus cross-test logging/worker interference.
Fixtures now bypass production lifespan, block dotenv loading during collection
and mock CSV durability. Outcome mocking is module-local; cancellation tests
wait for their own real backup worker and preserve strict cleanup/content
assertions. Earlier runs cannot certify absence of background/live attempts.
The corrected isolated run is the final evidence; failures were not waived.

## Prepared source is not the live service

Changes are on `codex/zero-budget-repair` in existing draft
[PR #201](https://github.com/markcosker2-dev/orova-nova/pull/201).
No merge or Render deployment is authorized by these test results. Live public
health around 18:44 Singapore reported build `bd33ab8ffbab`, not the repair branch.

September 30 GET-only production Retell inspection returned **HOLD: five hard
blocks**: production version binding, missing production tag, unpublished agent,
unpublished LLM and legacy Cal functions. Draft inspection is useful but always
holds phone traffic. No Retell settings were changed. No demo-number DMs until
machine checks, booking/simulation/web/phone tests, actual funding and owner's
action-time approval pass.

The last full-backup evidence (September 28) was `invalid_grant`, not a fresh
successful backup. Sheets lead parity is a partial fallback, not approvals,
events, suppressions, conversations or learning-state recovery. Do not deploy
until a fresh complete backup and restore proof exist. Do not delete OAuth
variables as a workaround.

The latest supplied cloud-task report uses the Sheets publish queue and the
M/W/F 21:00 Asia/Singapore schedule. It was not independently run or changed in
this evaluation. Local ChatCut does not prove cloud tool availability with the
laptop off; unavailable tools or unverified commercial media/voice rights mean
draft-only Reels. No Instagram post, queue promotion, prospect message, booking,
paid model switch or purchase was deliberately performed by this review.

## Next operating action

OROVA sells Meta lead generation plus consent-based qualification/follow-up.
Primary ICP: custom home builders/high-end remodelers; secondary luxury real
estate. Med spas are excluded. Mark still owns approved commercial scope,
price, term, payment and closing; catalog values do not approve an offer.

Prepare one fact-checked builder DM for Mark's review/manual send, without the
held demo number or invented client results. Log actual sends/replies in the
existing tracker. A passing engineering suite is not evidence of a first client.

Linked: [[active-context]]
