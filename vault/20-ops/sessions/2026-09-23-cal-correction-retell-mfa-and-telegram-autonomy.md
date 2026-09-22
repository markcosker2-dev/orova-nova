---
name: session-2026-09-23-cal-correction-retell-mfa-and-telegram-autonomy
description: Corrected the live Cal duration, secured an exact Retell rollback snapshot, and made Telegram Nova more autonomously useful without widening external authority.
type: session
created: 2026-09-23
status: active
---

# Session: Cal correction, Retell MFA and Telegram autonomy (2026-09-23)

## Verified live changes

- Cal event type `2804866` (`OROVA Calls`) changed from 30 to **15 minutes**.
  Cal displayed “updated successfully,” the event editor and preview both show
  15 minutes, and the public booking page independently embeds length 15.
- Before any Retell mutation, an exact snapshot of the inbound phone resource,
  agent prod/V0 and LLM V0 was encrypted with Windows current-user DPAPI and
  written outside the repository under the local OROVA private-backup folder.
  A separate decrypt-and-schema verification passed. No raw response, prompt,
  phone number, tool credential or caller data was printed or committed.

## Retell state

The rerun gate now passes Cal duration. It still holds demo traffic on four
prompt blockers: recording consent, labelled simulation, post-demo diagnosis
and the 15-minute handoff. Both existing Cal tools still point to the correct
event, but they are legacy and untested. The inbound number is directly bound
to unpublished V0 rather than a production tag.

The OROVA Google login reached Retell's mandatory MFA-enrollment screen. No
phone number, authenticator secret or security setting was entered. Creating a
persistent MFA method requires Mark's action-time choice. The dashboard tab was
left ready for handoff; the live Retell prompt and tools were not changed.

## Telegram autonomy — local only

- Nova now speaks as a decisive operating partner, chooses instead of listing
  equivalent options, asks at most one material question, names exact gates and
  never describes preparation as business progress.
- `/focus` and `/next` select and prepare the highest-ranked eligible untouched
  lead. “What should I do?” and “find our next prospect” use that deterministic
  route.
- The unrestricted agentic planner remains off. External sending, calls,
  booking, spend, publishing and deployment retain their gates.
- Combined Retell/Telegram regression suite: **96 passed**.

## Verification

- Full repository suite: **1,537 passed**, 26 dependency deprecation warnings.
- Canonical knowledge compilation: current, no drift.
- Repository secret scan: clean.
- Git whitespace validation: clean.

## Single next action

Mark completes Retell MFA enrollment using either SMS or an authenticator. Then
resume in the same dashboard: create a draft from V0, migrate both Cal tools,
paste the generated capture-only prompt, run simulations/web call, publish and
move the number only after the gate passes.

Linked: [[0020-telegram-autonomy-is-safe-preparation-first]] ·
[[retell-inbound-demo-launch-runbook-2026-09-23]] · [[active-context]]
