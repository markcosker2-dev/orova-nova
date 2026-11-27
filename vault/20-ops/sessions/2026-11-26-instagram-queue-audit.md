---
name: 2026-11-26-instagram-queue-audit
description: Read-only audit of the IG publish queue and post log; live posts with unsupported claims need archiving
type: session
created: 2026-11-26
status: active
---

# 2026-11-26 — Instagram queue and post-log audit (read-only)

Source: Google Sheet "OROVA IG Post Log", tabs `OROVA IG Publish Queue` and the untitled post-log tab. Nothing was changed. The live Instagram account was **not** checked: there's no Meta/Instagram access from the cloud session.

## Publish queue: safe
- 3 `test_claimed` rows (Sept connectivity tests, "never publish").
- 5 `draft` text concepts (30 Sep – 9 Oct): builder fit-check, creative fit, consent handoff, decline reasons, one-variable test. All have media intentionally blank, and none are `ready`. The copy is claim-safe.
- **Nothing is queued to publish.**
- **The last draft is 9 Oct**, and its note says the Make Instagram connections were "reported expiring on 2026-10-09". There have been no drafts since, so the M/W/F cloud social manager has apparently stopped producing. Reconnect Meta in Make and check the scheduled task before resuming.

## Post log: 26 posts marked `posted` (22 Jul – 23 Sep)
The log records no deletions or archives. Unless Mark already removed them, these are live and conflict with the operating brief (no invented clients, results, metrics or urgency):

| Priority | Post (log name, date) | Problem |
|---|---|---|
| **Archive now** | `carousel_9_client_result`, 27 Aug | "One OROVA client booked 47 qualified calls in 21 days". OROVA has no clients; the result is fabricated. |
| Archive | `carousel_6_pov_3000_v2_punchy`, 6 Aug | "$3,000… Here's EXACTLY what happened": a hypothetical presented as a real result |
| Archive | `carousel_8_not_a_chatbot_v2_punchy`, 7 Aug | "8% vs 60%+… on the same cold Meta leads": unsupported comparison |
| Archive | `carousel_11_inside_a_call`, 31 Aug | "a real conversation": implies a real client call (flagged 21 Sep) |
| Archive | `carousel_10_why_we_built`, 29 Aug | "every agency we talked to": unsupported history (flagged 21 Sep) |
| Review | `carousel_4_how_orova_works` (22 Jul) + `_v2` (8 Aug), `static_lead_ring` (25 Aug), `carousel_2_…` (4 Aug) | "booked call in under 60 seconds" speed promises for a product not yet delivered to anyone |
| Review | `carousel_7_the_9pm_lead` (9 Aug), `static_always_on` (30 Aug) | "50% of leads opt in after hours": unsourced statistic |
| Tidy | `static_speed_window` (19 + 21 Aug), `static_crm_or_calendar` (19 + 21 Aug) | duplicate posts |

The claim-safe later posts (e.g. `carousel_13_two_jobs`, 23 Sep) can stay.

**Action (Mark, in the Instagram app):** open each post above → ••• → **Archive**. Archiving hides a post but keeps it recoverable, unlike delete. Do the 27 Aug "47 calls" carousel first: a prospect checking OROVA's profile before a call would see a client claim that isn't true.
