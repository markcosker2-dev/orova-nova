---
name: 0015-med-spas-are-not-and-never-were-the-icp
description: Supersedes ADR-0012's ICP ranking — med spas are removed from the ICP, and Nova may never switch verticals on its own
type: decision
created: 2026-08-09
status: active
supersedes: 0012-icp-rerank-and-pilot-pricing
tags: [icp, adr, owner-mandate]
---

# ADR-0015 — Med spas are not, and never were, the ICP

**Status:** Accepted · **Date:** 2026-08-09 · **Supersedes:** the ICP *ranking*
in [[0012-icp-rerank-and-pilot-pricing]] (that ADR's pricing and qualifying-test
reasoning are untouched).

## Context

ADR-0012 ranked med spas / aesthetics as ICP vertical **#2**, on the strength of
a genuinely sound argument: 1–2 extra patients a month covers the retainer, the
owner-doctor decides alone, and it is the most-proven Meta lead-gen vertical in
the market.

That reasoning was never wrong *as vertical economics*. It was answering the
wrong question. It asked **"which verticals could a Meta-ads agency profitably
serve?"** and treated the answer as OROVA's ICP. Those are not the same thing —
the second requires the founder's intent, and that was never supplied.

Asked directly on 2026-08-09, Mark's answer was unambiguous:

> **"our ICP was never med spas."**

So this is not a change of direction based on new evidence. It is a correction
of a ranking that encoded an inference nobody had made.

### What it was actually costing

Not a stale document — live behaviour in three places:

1. **`app/core/business_context.json` (validation_bar)** instructed the agents:
   `"<=3 = wrong vertical, switch the lead vertical to med spas"`. Nova reads
   this. A weak first 20 calls would have **autonomously moved the company into
   a vertical the owner does not sell to**, and nothing in the loop required a
   human to agree.
2. **`app/worker.py` hunt rotation** carried 3 of 12 niches as med spa /
   cosmetic surgery. Since the hunt picks uniformly with `random.choice()`,
   **~25% of all discovery budget** was spent there — while the real pipeline
   stood at 5 contractors ([[2026-08-09-the-durability-mystery-was-a-duplicate-problem]]).
3. `business_context.json` `primary_verticals`, plus the brain docs and the
   sales-intelligence skill description, all repeated the #2 ranking.

## Decision

1. **Med spas are removed from the ICP.** Not deferred, not "later" — they were
   never it. Custom home builders / high-end remodelers are the lead vertical;
   luxury real-estate top producers remain secondary.
2. **Remove the med spa niches from the hunt rotation.** This is the automotive
   removal of 2026-08-02 repeated for the same reason: the ICP gate is a filter,
   but the cheapest control is not to search for it in the first place. Still
   reachable via an explicit `TARGET_NICHE` override if this is ever revisited.
3. **Nova may never switch the lead vertical autonomously.** The validation_bar
   now escalates to Mark with the transcripts instead of pivoting. The ICP is an
   owner decision, not an agent one. This is the general rule, not a med-spa
   patch — the same prohibition applies to any future vertical.
4. **ADR-0012 is superseded, not deleted.** Its deal-economics framing and the
   qualifying test ("does ONE extra closed deal per month cover the all-in
   cost?") remain the right lens and stay in force.

## Consequences

- ~25% of hunt discovery budget redirects to the lead vertical.
- One autonomous-pivot path into an unwanted market is closed.
- **A future session cannot re-derive med spas from vertical economics alone**,
  which is exactly what ADR-0012 did. The record now says the economics were
  never the deciding input. This ADR exists primarily to stop that re-derivation
  — a silent delete would have guaranteed it.

> [!note] What is NOT decided here
> This says nothing about **pricing**. `commercial_terms` remains UNRESOLVED and
> no figure in this ADR should be read as setting one.

### Deliberately left alone: the scorer

`lead_validator._ICP_VERTICAL_KEYWORDS` still rewards `"med spa"` and
`"medspa"` with +10 on `vertical_match` — and still rewards the automotive
terms that ADR-0012 demoted in 2026-07. It was **not** changed here, because
`lead_validator.py:127` records a standing owner rule: *do not rush the
scorer.*

The exposure is small now that the hunt no longer searches for med spas — the
keyword can only fire on a lead arriving from elsewhere (CSV import, a stray
result). It is logged here so the inconsistency is a known open item rather
than a thing a future session discovers and quietly "fixes" mid-task.

## Linked

[[0012-icp-rerank-and-pilot-pricing]] · [[0014-licence-registries-as-the-discovery-source]] ·
[[handoff-2026-08-09]] · [[2026-08-09-the-durability-mystery-was-a-duplicate-problem]]
