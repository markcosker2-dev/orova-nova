---
name: session-2026-07-04-wp4-booking-funnel
description: Claude Code session — WP4 remainder, the reply→qualify→booking funnel
type: session
created: 2026-07-04
status: done
---

# Session: WP4 remainder — reply → qualify → booking funnel (2026-07-04)

Continued from [[session-2026-07-04-full-buildout-handoff]] / [[roadmap]]. WP4
part 1 (approval gates) was already merged; this session built the funnel
middle-mile so a HOT reply auto-progresses instead of stopping at a Telegram alert.

## What changed

- **Reply classification** (`app/skills/agentmail_skill.py`) — new
  `classify_reply_intent()` (single-reply HOT/WARM/COLD, same taxonomy as the
  batch categorizer) with a **keyword fallback** so it works with no live LLM key,
  and an **opt-out hard-stop** to COLD (never auto-book someone who said "stop").
- **Reply monitor** (`app/worker.py`) — `run_reply_monitor` now classifies every
  reply, qualifies it against the lead DB, alerts Mark with the temperature, and
  **queues HOT replies** to a durable state-store queue (`pending_booking_replies`).
  New `process_pending_booking_replies()` drains that queue: gated on the new
  `reply` approval kind, it sends a booking-link reply in-thread via
  `reply_to_email`, updates lead status, and alerts Mark. Per-client monitors run
  **sequentially** (not `gather`) so the shared-queue write can't race.
- **Approval gate** (`app/core/approval_gate.py`) — added the `reply` kind reading
  `REPLIES_AUTOPILOT` (default OFF; its own flag because auto-replying to a warm
  inbound is lower-risk than cold outreach).
- **Cal.com webhook** — fleshed out `_handle_booking_created` (`app/skills/cal_booking.py`)
  to actually create the Google Calendar event (mirrors the Retell booking path)
  and alert Mark; added the missing route `POST /api/cal/webhook` in `app/main.py`
  (HMAC-verified when `CAL_WEBHOOK_SECRET` is set).
- **Tests** — `tests/test_reply_booking.py` (12 tests). Suite: **124 passing**.

## Why

The roadmap's #1 Claude task. Speed-to-lead matters: when a prospect replies HOT,
Nova should immediately offer a booking link and put the meeting on Mark's calendar
when they book — the funnel's middle-mile was the missing link between outreach and
a booked call. Kept fail-closed and approval-gated per WP4's "prove it first" rule.

## Design notes (for future me)

- The reply monitor advances a checkpoint and never re-reads a message, so the
  outreach lane's "re-scan pending each cycle" approval pattern doesn't apply —
  hence the **durable queue** (survives Render restarts) with attempts/TTL caps.
- Everything degrades gracefully against the current blockers: no LLM key → keyword
  classifier; no `CALENDLY_LINK`/`CAL_COM_EVENT_SLUG` → the reply asks for times;
  no Google Calendar OAuth → Mark gets a "add it manually" alert.

## Follow-ups

- [ ] Mark: set a booking link (`CALENDLY_LINK` / `CAL_COM_EVENT_SLUG`) + point
      Cal.com webhook at `/api/cal/webhook` with `CAL_WEBHOOK_SECRET`; add Google
      Calendar OAuth token for real event creation.
- [ ] Verify the funnel end-to-end once a free LLM key + booking link exist.
- [ ] Optional: send the prospect a booking confirmation email on the Cal.com
      webhook (text is already returned as `confirmation_email`, not yet sent).
- [ ] Not committed/PR'd yet — Mark to review the working tree, then commit.
