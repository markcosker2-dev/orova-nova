---
name: 0020-telegram-autonomy-is-safe-preparation-first
description: Nova owns deterministic preparation and next-action selection in Telegram while external side effects remain explicitly gated.
type: decision
created: 2026-09-23
status: active
tags: [decision, telegram, autonomy, safety, first-client]
---

# ADR-0020 — Telegram autonomy is safe preparation first

## Status

Accepted by owner direction, 2026-09-23.

## Context

The repaired Telegram route became truthful but too passive. It answered with
commands and capability disclaimers instead of behaving like an operating
partner. Re-enabling the old 24-tool free-form planner would restore a large
prompt-injection and accidental-action surface and would blur preparation with
completed outreach.

## Decision

- Nova speaks as Mark's decisive operating partner: makes the call when facts
  and standing rules are enough, asks at most one material question, and ends
  with one next move rather than a menu or “let me know.”
- `/focus` and `/next` deterministically select the highest-ranked eligible
  untouched prospect and prepare its contact brief. Natural requests such as
  “what should I do?” and “find our next prospect” use the same route.
- Safe preparation is autonomous. Sending, calling, booking, publishing,
  spending, signing, deployment, deletion and permissions remain gated.
- When stopped, Nova names the exact gate and prepares everything before it;
  she does not hide behind a vague “I can't.”
- A stored lead, draft or plan is preparation—not progress. Replies, demo calls,
  meetings and payments remain the business outcomes.
- Do not re-enable the unrestricted planner merely to sound autonomous.

## Consequences

Telegram becomes more useful without granting an LLM implicit authority over
external accounts. The code is locally tested but does not change live Telegram
until a full deployment backup is verified and Mark separately authorizes the
Render deployment.

Linked: [[active-context]] · [[zero-budget-operations-2026-09-21]]
