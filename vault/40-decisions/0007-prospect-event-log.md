---
name: 0007-prospect-event-log
description: "Append-only unified event log as the SDR pipeline's ground truth; additive first, existing tables migrate later"
type: decision
created: 2026-07-15
status: active
---

# ADR-0007 — The unified SDR event log (the pipeline's spine)

## Context

The Pipeline Blackboard design (ADR-0006 / 2026-07-15 session) needs one
ground-truth record of everything that happens to a prospect. Today outcomes
are scattered: `outreach_outcomes` (sends), `execution_traces`, lane logs, and
per-feature tables. Stage-conversion metrics (sent→reply→booked — the SDR's
north-star math) cannot be computed from one place, and the Coach/learning
loop has no single input.

Owner approval condition: "build the unified Prospect state machine and event
log **if it simplifies the architecture without breaking production**."

## Decision

**Additive first.** A single append-only `events` table
(`prospect_id, campaign_id, agent, event_type, variant_id, payload, ts`)
created idempotently at startup and re-ensured after a Drive restore
(restored snapshots may predate it). All logging is **fail-open** — a broken
event log can never block a send.

M1 wiring (this change): `lead_discovered` at both Scout sources (hunt + CSV
import), `outreach_sent` inside `send_outreach` itself — ONE wiring point that
covers every email path (hunt, escalation, drip). Existing tables keep
working unchanged.

Migration path (later, each as its own change): `reply_received` and
`meeting_booked` events; the Coach reads events instead of
`outreach_outcomes`; the state machine's transitions become event-emitting;
`outreach_outcomes` becomes a view or is retired. The full Prospect state
machine arrives incrementally on this spine — never as a rewrite.

## Consequences

**Easier:** booked-rate math is one query; the Coach gets one input; new
agents log without new tables; debugging is "read the prospect's event
stream."

**Harder / accepted:** double-writing sends (events + outreach_outcomes)
until the migration completes — deliberate, so nothing breaks while the spine
proves itself.

## Linked

- [[0006-sdr-refocus-and-subtraction]] (the Blackboard target architecture)
- [[0004-obsidian-brain-and-skill-improvement]] (the learning systems that
  will consume this)
