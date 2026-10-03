---
name: quarantined-partial-recovery-and-preserved-backups
description: Incomplete recovery keeps contacts held and historical backups intact
type: decision
created: 2026-10-03
status: accepted-for-preparation
---

# ADR-0023 — Partial recovery does not restore permission

## Context

A complete current SQLite snapshot is unavailable. Mark accepted the stated
incomplete-state loss risk for preparation and testing of a partial recovery.
This is not an immediate merge, credential or production-cutover instruction.

## Decision

- Build an isolated, checksummed SQLite candidate from the reviewed API export
  without importing or starting Nova. Reuse current schema and state_store.
- Preserve IDs and available data, but hold every recovered lead. Put available
  email/phone identifiers on precautionary suppression holds. These are not
  assertions that the prospect opted out; missing history must not imply consent.
- Keep original status labels and other projections private and quarantined.
  Do not activate old strategy priors, summaries, drip state, approvals or chat.
- Missing timestamps/call counters remain unknown. Reset phone verification.
- Require integrity, foreign-key, identity/hold and full logical-content
  equivalence checks on an isolated SQLite restore.
- Stage privately under a name excluded from automatic snapshot selection.
  Independently verify Nova's intended OAuth client's exact-file access before
  promotion. A connector identity and metadata receipt are not that proof.
- Preserve historical backups by default. Retention requires explicit opt-in
  and uses Trash rather than permanent deletion.
- Keep $0, consent, suppression, provider and offer gates. An incomplete-state
  production exception still needs an exact reviewed plan, owner credentials
  and specific merge/cutover authority.

## Verification and consequences

scripts/prepare_partial_recovery.py has no network, dotenv or app imports.
tests/test_partial_recovery.py uses synthetic inputs and private temporary DBs.
Backup-retention tests mock Drive and perform no real deletion or API call.
The full local benchmark is required. No paid dependency or new live queue is
introduced. Recovered contacts cannot be treated as untouched/approved solely
because old event or opt-out records are missing.

See [[partial-recovery-release-plan-2026-10-03]].
