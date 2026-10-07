---
name: learning-observations-and-no-age-only-pruning
description: Deterministic outcome reports, safe notification receipts and preservation of untouched prospects
type: decision
created: 2026-10-02
status: accepted-local
---

# ADR-0022 — Learning observations are not proven winners

Prepared locally for review; this decision does not certify deployment.

## Context

Nova's supplied Telegram examples repeatedly claimed unmeasured email lifts,
winning send times and immediate campaign rollouts. The old report supplied
only candidate strings to an LLM, not comparison evidence. The same loop
proposed bulk archiving from record age, including untouched New prospects.
Its legacy approval list had no scope, expiry or reviewed disposition and
claimed CRM success before background sync was verified.

## Decision

- Generate operational learning summaries deterministically from the existing
  outreach_outcomes ledger, scoped to client and a 30-day UTC window. Count
  successful-send/reply/meeting records separately from other results.
  These are logged records, not unique prospects or independently verified
  delivery. Missing data is unavailable, not a measured zero.
- Do not infer open/click lifts, statistical significance or proven strategy/
  niche winners from those aggregates, defaults, seeded priors or candidate
  names. Manual DMs are not measured by this email summary. The summary
  neither authorizes nor performs a campaign rollout.
- Keep strategy mutation/tool-learning lanes paused in $0 mode, including
  direct worker/API invocations. An explicit manual Check Learning is
  observational apart from its notification checkpoint. Existing funded
  rankers exclude failed/blocked/pending attempts; a 20-success-record floor
  does not establish causal performance, valid experiments or contact consent.
  Funded ranking is not currently authorized or certified for launch.
- Disable age-only archive proposals and reject legacy /approve_pruning
  lists through both Telegram and the API. Preserve all prospects/history.
  A legitimate archive needs an individual reviewed disposition and owner
  authorization; a stale timestamp alone is not disqualification.
- Claim a learning notice atomically in existing state_store before sending.
  Unchanged or overlapping notices do not replay. Mark sent only after both
  Telegram HTTP success and an explicit Bot API acknowledgement.
  A timeout, crash or failed checkpoint leaves a hold, including changed
  reports. After owner verification of delivery/access, review the claimed
  notice deliberately; do not automatically clear/retry it.
- Label dashboard rankings as stored candidates, not measured wins/financial
  ROI. Reset cards when a read fails. Distinguish observed data, held notice
  delivery and unavailable results in API responses and UI notices.
- Never log credential-bearing Telegram request URLs or exception details.

## Consequences and verification

No new LLM, paid dependency, queue or database table. Notifications reuse
state_store and its existing complete-backup/restore requirement; Sheets
alone cannot preserve that state on Render's ephemeral disk.

Use tests/test_learning_report_truth.py and tests/dashboard_contract.test.cjs,
then python scripts/nova.py benchmark. Tests are isolated, synthetic project
regressions, not GPT-6.1 Sol public scores or proof of live Telegram behavior.
Before launch, recover/verify the bot's access and full durable backup, obtain
merge/deployment authorization, and verify real replies on the exact build.
