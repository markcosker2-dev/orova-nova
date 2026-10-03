---
name: partial-recovery-release-plan-2026-10-03
description: Tested quarantined recovery preparation; owner credential and live cutover handoffs remain
type: doc
created: 2026-10-03
status: prepared-not-deployed
---

# Controlled partial recovery — release plan

## Authorization and loss boundary

Mark explicitly accepted possible loss of unbacked conversations, approvals,
opt-out records and event history, in response to a question about preparing
and testing a partial-recovery rollout. This authorizes preparation, not an
immediate Render restart, credential replacement, merge or deployment.

The normal complete-backup release rule still applies unless Mark approves
the exact incomplete-state cutover as an exception after reviewing this plan.
Do not ask him to accept the same preparation risk again. Obtain only the
remaining specific authority or private owner action.

## Prepared and tested

- scripts/prepare_partial_recovery.py reads a pinned, SHA-256-verified API
  projection without importing Nova, loading dotenv or contacting a provider.
- It builds a new private SQLite candidate from the existing schema constants.
  Lead IDs and available fields are retained. Every lead becomes Recovery Hold;
  exported email addresses and phone numbers enter the existing suppression
  lists as precautionary holds, not as claims of real prospect opt-outs.
- Missing activity timestamps and call counters remain unknown. Phone
  verification is reset. Original status labels are retained privately.
- Dashboard-memory and strategy projections are quarantined in existing
  state_store, not activated as chat history, approvals or proven learning.
- Integrity, foreign keys, all IDs and contact holds are checked. A second
  SQLite hot-copy restore must have identical logical database contents.
- No original source, historical backup or live DB is overwritten.
- Backup retention is disabled unless BACKUP_PRUNE_ENABLED=1. An explicit
  opt-in moves excess snapshots to Trash, never permanently deletes them.
  Leave it disabled through this recovery.

This is a valid SQLite container of INCOMPLETE recovered data, not a complete
snapshot of the old production database. It does not itself authorize a deploy.
The live API projection is bounded and nontransactional; unexposed state is
unknown, not measured empty.

## Staging and transport gate

Stage only inside the existing owner-only Drive backup folder, with a name
that DOES NOT contain nova_backup_. Such a file is excluded from the current
automatic restore and retention queries. Keep its ID, source checksum,
candidate checksum and private paths in the local dated recovery note.

Connector upload/metadata access is not proof that Nova's own OAuth client can
download that file. Before promotion, use the intended Google client/token to
read the exact staged file, independently verify its bytes/checksum and its
private permissions. drive.file access must be tested, not assumed from folder
membership or a different connector's success.

The current running Google credential returns invalid_grant. The earlier
replacement was temporary while the app remained Testing, and a client secret
was exposed in diagnostics. Owner-only secure credential replacement is still
required. Never paste credentials into chat, notes, Git or logs. Save new Render
values with Save only; that must not restart or deploy the current service.
Do not claim durable renewal until the Testing expiry issue is resolved and
the approved credential path is verified.

## Exact cutover — NOT executed

1. Refresh the bounded source export immediately before the reviewed change
   window, rebuild the candidate and repeat offline checks. Preserve all prior
   files. Stage it under a non-auto-restore name.
2. Complete the owner credential handoff and exact-file OAuth read/checksum
   gate. Verify ZERO_BUDGET_MODE=1, CEO_AUTO_EXECUTE=0, CALLS_AUTOPILOT=0 and
   BACKUP_PRUNE_ENABLED disabled. Cold AgentMail stays blocked by code.
3. Review the exact repair head and fresh CI. Mark merges under the standing
   rule, unless he separately delegates that merge. Coordinate Render's actual
   auto-deploy setting before merging; a merge may otherwise begin the cutover.
4. Obtain action-time approval naming the release head, incomplete-state loss,
   candidate and target Render service. No upload receipt replaces this gate.
5. Only then promote the verified staged name into the nova_backup_ selection
   set and deploy the approved repair. Promotion can affect a future old-service
   cold start, so it is part of the authorized cutover, not preparation.
6. Verify exact deployed /health build, actual selected snapshot, restored lead
   IDs/holds, absence of recovered approvals, and safe real Telegram commands.
   Local tests and a healthy old build are not live-release verification.

## Rollback and stop conditions

Stop if OAuth, exact-file checksum, permissions, restore, operator identity,
build or action gates fail. Do not silently accept an older July snapshot,
Sheets-only fallback, blank DB or successful deployment label.

Retain the old full historical fallback and every partial export. A code
rollback cannot recreate lost current state. Any recovery-failed cutover needs
owner-reviewed action; do not cycle restarts or activate unverified contacts.
Unknown suppression/approval history never creates contact consent.

## Single next action

Complete secure owner Google credential setup, then verify exact candidate
access using Nova's intended OAuth identity before requesting live cutover.
