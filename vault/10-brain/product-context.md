---
name: product-context
description: What OROVA is as a product and how Nova's own pipeline is the demo
type: brain
created: 2026-07-03
status: active
---

# Product Context

## What OROVA sells

OROVA is a **marketing agency** — it sells done-for-you Meta (Facebook + Instagram)
lead-gen to luxury/premium West Coast businesses. The commercial terms (packages,
pricing, ICP) are the source of truth in [[business-model]] and its machine-readable
twin `app/core/business_context.json`. Do not restate pricing here — link there.

> Earlier drafts of this note said "revenue comes from what OROVA does for the
> business, not from selling the tool," with automotive dealers as the target.
> That was wrong. OROVA charges a monthly retainer ($4K / $5K) to run ads for
> clients. Kept here as a correction so the mistake isn't repeated.

## Nova — the agent that runs the agency

"Nova" is the autonomous system in this repo (`app/`). It's two things at once:

1. **The delivery engine** — for a signed client it will hunt/qualify leads, run
   outreach, cold-call via Retell, keep their CRM current, and book appointments.
2. **The sales demo** — Nova runs its *own* outbound to find OROVA's first client.
   The pitch writes itself: "you're testing the product right now." That dual use
   is the whole strategy — the tool sells itself by working.

## What Nova actually does (pipeline)

- **Lead discovery** — Google Maps + DuckDuckGo, enriched with free web scraping,
  WHOIS, state business registries, BBB, and DNS/MX email inference. No paid data.
- **Outreach** — AgentMail-hosted inbox, personalized emails (champion/challenger
  framework), A/B subjects, learned send-timing, daily send cap.
- **Voice** — Retell.ai cold-calls cold/qualified leads, books meetings.
- **Booking** — Google Calendar event on a confirmed appointment.
- **Pipeline** — lead scoring, follow-up state machine, drip sequences.

## Key metrics (dashboard)

Leads found · emails sent · replies · meetings booked · calls made · pipeline
health (0–100) · reply/meeting conversion · win rate · best send timing. These
feed the self-improvement loop — see [[claude-brain]] and [[strategy-snapshot]].

## Linked

- [[business-model]] — packages, pricing, ICP (source of truth)
- [[system-patterns]] — how the lanes and agents fit together
