---
name: session-2026-09-23-cal-correction-retell-access-and-telegram-autonomy
description: Corrected Cal, preserved Retell V0, prepared consent-first V1 with current Cal tools, and made Telegram Nova more autonomous without widening external authority.
type: session
created: 2026-09-23
status: active
---

# Session: Cal correction, Retell access and Telegram autonomy (2026-09-23)

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

- Correct owning workspace **Mark B. Cosker's** and reviewed inbound agent were
  visibly confirmed.
- V0 was published unchanged as
  `Baseline before inbound demo migration — 2026-09-23`; it remains bound to
  the inbound number and is the exact pre-migration baseline.
- Draft V1 `Consent-first inbound demo + Cal migration` was created from V0.
  It is not published or phone-bound.
- V1 now has the consent-first capture-only prompt, labelled simulation,
  two-path diagnosis, canonical 15-minute handoff and the hard boundary
  `no price, no trial, no pilot`.
- Retell's AI-disclosure handbook control is enabled. Storage changed from
  Everything/forever to Everything except PII with 30-day retention.
- Current Cal.com availability and booking functions both target event type
  `2804866`. A read-only availability test succeeded. Direct booking remains
  disabled in the prompt until an end-to-end booking test passes.
- Post-call `appointment date and time` and `appointment booked` fields now
  remain empty unless a booking succeeds or Mark explicitly confirms it;
  preferred times alone cannot become a booked appointment.
- The tightened V1 gate passes every prompt, privacy, extraction, event and
  duration check. It correctly holds on one blocker: the two legacy Cal
  functions are still attached alongside the current functions.

Pending action-time approval: delete only the two legacy functions from Draft
V1, spend Retell balance on simulations/a short browser call, and create then
delete one real 15-minute Cal test appointment. Do not publish V1, move the
phone binding or expose the number until those tests pass.

## Telegram autonomy — local only

- Nova now speaks as a decisive operating partner, chooses instead of listing
  equivalent options, asks at most one material question, names exact gates and
  never describes preparation as business progress.
- `/focus` and `/next` select and prepare the highest-ranked eligible untouched
  lead. “What should I do?” and “find our next prospect” use that deterministic
  route.
- The unrestricted agentic planner remains off. External sending, calls,
  booking, spend, publishing and deployment retain their gates.
- Combined Retell/Telegram regression suite: **96 passed** before the latest
  readiness-gate tests; the focused readiness suite is now **9 passed**.

## Verification

- Full repository suite: **1,541 passed**, 26 dependency deprecation warnings.
- Canonical knowledge compilation: current, no drift.
- Repository secret scan: clean.
- Git whitespace validation: clean.

## Single next action

After Mark's action-time approval, delete the two legacy Cal functions from
Draft V1, run the billable simulation/browser tests, and create/verify/delete
one test booking. Only then render verified-booking mode, retest, publish and
move the inbound binding through a reviewed rollback tag.

Linked: [[0020-telegram-autonomy-is-safe-preparation-first]] ·
[[retell-inbound-demo-launch-runbook-2026-09-23]] · [[active-context]]
