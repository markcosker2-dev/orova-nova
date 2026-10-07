---
name: 2026-10-02-learning-truth-and-telegram-continuation
description: Continuation fixes for false learning, recurring pruning and misleading dashboard results
type: session
created: 2026-10-02
status: locally-tested-not-deployed
---

# October 2 — truthful Nova reports and lead preservation

## Verified state and scope

Mark asked to continue using GPT-6.1 Sol's capabilities and benchmarks. Public
model scores cannot be transplanted onto OROVA; the verification is actual
project regression checks. Budget remains $0; no provider switch, purchase,
prospect message, call, post, lead archive or deployment was performed.

Read AGENTS, zero-budget handoff, active context and the complete owner playbook.
The existing draft PR #201 is OPEN on codex/zero-budget-repair; pre-change
GitHub CI/CodeQL is green on 0e1248d, not on these new changes yet.

GET-only October 2 checks around 23:34–23:36 Singapore:
- Render /health returns 200, build bd33ab8ffbab, db/memory ok. The repair is
  not merged/deployed. Capability metadata is not proof that a lane executed.
- @orovaNOVA_bot's public profile still has the reported unrelated-ad markers.
  The locally configured token returns getMe 401; authenticated identity is
  not verified. No ad destination was opened and no token/profile was changed.
  Bot ownership was confirmed by Mark September 30; cause/access route unknown.
- Full database backup/restore was not freshly verified. Last complete-backup
  evidence remains September 28 invalid_grant; do not restart/deploy blindly.

## Changes prepared locally

- self_improvement: replace free-form LLM report embellishment with bounded,
  client-scoped real-ledger counts; ignore candidate strings as proof.
  State missing data as unavailable and avoid claims of opens/clicks, winning
  niche/framework/time, quantified lifts or a campaign rollout.
- Reports differentiate email ledger records from manual DMs and independently
  verified delivery. Baseline/default values never become results.
- A manual $0 cycle cannot seed/promote strategies; direct worker and lane-8
  API calls cannot bypass the scheduled $0 guard. Funded rankers exclude
  unconfirmed attempts; aggregate thresholds still are not experimental proof.
- Atomic learning_notice checkpoints in existing state_store suppress
  unchanged/concurrent reports across event loops and restarts. Confirm actual
  Telegram acknowledgement before marking sent. Uncertain delivery/checkpoint
  stays held instead of repeatedly retrying; owner review is necessary.
- Telegram alert receipt validation now rejects HTTP/API failures and omits
  credential-bearing exception URLs from logs.
- Age-only pruning and its legacy approvals are disabled in Telegram and HTTP.
  No lead was removed or reclassified; untouched prospects are preserved.
- Dashboard displays stored candidates, not fake wins/ROI. Failed reads clear
  stale cards; action notices separate observation from held/unverified delivery.
- Added isolated synthetic regressions and included them in the focused
  benchmark profile. See [[0022-learning-observations-and-no-age-only-pruning]].

Files: app/core/self_improvement.py, router.py, hermesclaw_endpoints.py;
app/worker.py; app/skills/agentmail_skill.py; scripts/nova.py;
mission-control/index.html and js/app.js; tests/test_learning_report_truth.py,
dashboard_contract.test.cjs and test_nova_cli_quality.py.

## Verification

Three initial regression tests reproduced the old LLM-report failure safely
with a mocked writer. An intermediate focused run passed 116 tests. The
complete benchmark then passed 1,741 Python tests (28 warnings), 9 dashboard
tests, secret scan, canonical knowledge check and narrow security lint.

The final complete rerun including the explicit held-lane API regression passed
**1,742 Python tests, 28 warnings in 109.10 seconds**, all **9 dashboard tests**,
secret scan, canonical knowledge and narrow security lint. This adds 31 Python
cases and 3 dashboard cases over the previous complete suite. The warnings are
existing deprecation warnings, not silently skipped failures.
Bounded machine measurements are in ignored .unlazy/benchmark-2026-10-02.json,
not raw production logs. Local tests do not certify merge, deploy, model
quality, backup restoration or customer outcomes.

## Single next action

Obtain explicit controlled bot-recovery authorization and secure replacement
credentials without putting tokens in chat, Git or the vault. Fresh full
backup/restore and owner-approved rollout remain required before these fixes
can change live behavior. Mark controls merge and commercial terms. Do not
approve the old age-based prune list or share the held demo number.

Linked: [[active-context]] · [[2026-09-30-telegram-reply-nvidia-and-profile-incident]]
