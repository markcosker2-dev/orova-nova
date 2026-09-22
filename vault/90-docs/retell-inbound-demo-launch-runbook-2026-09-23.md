---
name: retell-inbound-demo-launch-runbook-2026-09-23
description: Fail-closed sequence for moving OROVA's prospect-initiated demo from canonical prompt to a tested Retell production version.
type: runbook
created: 2026-09-23
status: active
tags: [retell, cal, inbound-demo, deployment, consent]
---

# Retell inbound-demo launch runbook — 2026-09-23

The live number remains attached to published V0, the reviewed unchanged
baseline, and demo traffic is on **HOLD**. Cal event type `2804866` is
live-verified at 15 minutes. Draft V1 contains the consent-first capture-only
prompt, current Cal functions, safer retention/disclosure settings and guarded
booking extraction. The V1 read-only gate now finds one blocker: both legacy
Cal functions are still attached alongside the current replacements.

## Pre-change evidence

1. Run `python scripts/retell_inbound_readiness.py`; save only its redacted
   result, never raw API bodies.
2. **Done 2026-09-23:** export the exact live number, agent version, LLM version, prompt, tools and
   settings to a private encrypted backup outside Git. A redacted summary is
   evidence, not a rollback payload. The current snapshot is DPAPI-encrypted
   and decrypt-verified under the Windows account.
3. Record the current `prod` tag and number binding. Do not edit the production
   version in place.

## Cal migration first

1. **Done 2026-09-23:** change event type `2804866` from 30 to the canonical
   **15 minutes** and verify the live editor/public booking page.
2. **Prepared:** Retell's current Cal.com availability and booking functions
   target event `2804866`; the availability test passed. Delete the legacy
   `check_availability_cal` / `book_appointment_cal` tools. Retell says legacy
   tools stop accepting edits on **2026-09-30** and must migrate before
   **2026-10-31**.
3. Confirm availability returns only Mark-compatible early-morning or
   late-afternoon Pacific slots. Confirm US midday is unavailable.
4. Run a test booking, verify the calendar event is exactly 15 minutes, then
   remove the test event.

> [!warning] Current action-time gate
> Deleting the two legacy Draft V1 functions, consuming Retell test balance,
> and creating/deleting a real Cal test appointment require Mark's confirmation
> immediately before those actions. V1 must stay unpublished until they pass.

## Draft and test

1. Render the fail-closed review package:
   `python scripts/render_retell_inbound_prompt.py --format text`.
2. **Done:** published V0 unchanged as the rollback baseline and created Draft
   V1 from it.
3. **Done:** pasted the generated begin message and general prompt. Keep capture-only mode
   until the Cal tests above pass; only then render `--booking-mode verified`.
4. **Done:** attached the current availability and booking tools to the reviewed
   event; do not enable booking behavior until the end-to-end test passes.
5. Run simulations for: consent yes/no; invited demo; explicit end of
   simulation; lead-volume diagnosis; qualification diagnosis; booked-solid
   disqualification; price question; opt-out; wrong number; tool failure; and
   no fabricated booking.
6. Run a browser/web-call test. Then ask Mark before any paid phone test.

## Publish and rollback

1. Publish only the tested draft and move the `prod` tag to it.
2. Bind the inbound number through the reviewed production version/tag.
3. Re-run the readiness gate. It must exit 0 before the number appears in a DM.
4. Send one owner-reviewed DM, then inspect one real inbound call before scaling
   to the remaining four.
5. If any gate fails, restore the previous production tag/version and stop
   traffic. Do not improvise a prompt hotfix on the live version.

## Sources

- [Retell agent versions](https://docs.retellai.com/agent/version)
- [Retell Get Phone Number](https://docs.retellai.com/api-references/get-phone-number)
- [Retell privacy/data storage](https://docs.retellai.com/accounts/privacy-disable)
- [Retell Cal.com integration](https://docs.retellai.com/integrations/cal-com-functions)
- [Retell testing pricing](https://docs.retellai.com/test/testing-pricing)

Linked: [[0018-the-prospect-initiates-the-demo-call]] · [[active-context]]
