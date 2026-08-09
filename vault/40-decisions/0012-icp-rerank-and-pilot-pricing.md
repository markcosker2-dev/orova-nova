---
name: 0012-icp-rerank-and-pilot-pricing
description: Re-rank the ICP by deal economics (homes/remodel leads, exotic auto demoted), add a qualifying test and disqualifiers, and price client #1 as a proof-buying pilot
type: decision
created: 2026-07-24
status: accepted
---

# ADR-0012 — ICP re-rank + first-client pilot pricing

## Status
Accepted (owner directive 2026-07-24, following a Paul-Graham-style pressure test
of the business). Supersedes the 2026-07-13 "ICP stays MIXED" call in
[[active-context]] — the mix is now **ranked**, not flat, and exotic auto is
demoted to opportunistic.

> [!warning] The ICP ranking below is SUPERSEDED (2026-08-09)
> [[0015-med-spas-are-not-and-never-were-the-icp|ADR-0015]] removes med spas
> from the ICP entirely — owner: *"our ICP was never med spas."* Everything
> else here still stands: the all-in framing, the qualifying test, the
> disqualifiers and the pricing reasoning are unchanged and still in force.
> Read the med spa passages below as **history**, not as instruction.

## Context — what the pressure test surfaced

1. **The real ask is the all-in number.** Retainer $4-5K + recommended ad spend
   $2-2.5K = **~$6,500-7,500/mo leaving the client's account.** "Ad spend is
   separate" is an accounting fact, not a buying fact; the prospect asks "what do
   I get for $6,500?", never "what do I get for $4,000?". Framing the ask as $4K
   understates it by 60-85%.

2. **The pipeline was full of businesses that can never afford it.** Live leads
   included Fort Bragg Transmission, Keith's Auto Repair, Now Auto Care —
   ~$400 gross per job, so **~16 extra jobs/month** just to break even, and they
   don't have $6,500/mo regardless. Not near-misses; impossible.

3. **The affordability squeeze.** Businesses small enough to lack an agency often
   can't afford the all-in; businesses big enough to afford it (franchised luxury
   dealers) have OEM co-op budgets and corporate marketing mandates that block an
   independent agency.

4. **Exotic autos is the weakest *channel* fit on our own list.** The unit
   economics work (~$10-25K gross per car), but a $200K buyer rarely begins on a
   Meta lead form — that journey runs through reputation, referral, and
   marketplaces. The Meta-auto case studies we cited were tint/detail shops,
   which are exactly the businesses that can't pay $6,500/mo.

## Decision

### 1. The qualifying test (the filter that ranks everything)
> **Does ONE extra closed deal per month more than cover the ~$6,500-7,500 all-in
> monthly cost?**

If no, disqualify — the price objection cannot be closed and outreach is wasted.
If yes, the pitch becomes arithmetic rather than persuasion.

| Vertical | Gross per deal | Deals needed/mo | Verdict |
|---|---|---|---|
| Custom home builder / high-end remodel | $20-50K on a $100K+ job | ~0.2 | **LEAD** |
| Med spa / aesthetics | $3-15K per patient | 1-2 | **Second** |
| Luxury RE top producers | varies; commission-based | ~1 | Third |
| Exotic / luxury auto | $10-25K per car | ~0.5 | Opportunistic (channel risk) |
| General auto repair | ~$400 | ~16 | **Disqualified** |

### 2. Primary verticals, re-ranked (`app/core/business_context.json`)
1. **Custom home builders / high-end remodelers — LEAD.** Owner-operated, already
   buys marketing, proven Meta lead-gen, and one extra job pays 4-7 months of
   retainer.
2. **Med spas / aesthetics / high-ticket elective medical.** The most-proven Meta
   lead-gen vertical; the doctor/owner decides alone.
3. **Luxury real estate agents — individual top producers only** (score for
   production volume first; $4K/mo is a large bite of a solo agent's P&L).

Exotic/luxury automotive moves to **secondary_verticals, opportunistic only** —
work inbound and existing leads (e.g. West Coast Exotic Cars), don't lead the hunt.

### 3. Explicit disqualifiers (new)
General auto repair/transmission/oil-change shops · franchised new-car dealerships
(OEM co-op + corporate mandates) · anyone already under agency contract who hasn't
volunteered dissatisfaction.

### 4. Hunt rotation re-weighted (`app/worker.py`)
`DEFAULT_HUNT_NICHES` is sampled with `random.choice()` — **uniformly** — so the
*number of entries per vertical IS the weighting*. Re-composed from 50% auto to:
**homes 7/14 (~50%) · med spa 3/14 (~21%) · luxury RE + design 2/14 (~14%) ·
auto 2/14 (~14%)**.

### 5. First-client pilot pricing (`commercial_terms.first_client_pilot`)
**Client #1 buys proof, not revenue.** Offer **$1,500-2,000/mo for a 60-day pilot**
(or performance-tied) in exchange for a testimonial, case-study rights, and
permission to quote results. Standard P1/P2 pricing resumes at client #2, when a
real case study replaces the placeholder and does the selling. Holding $4K with
zero case studies is how pre-revenue agencies stay at $0. Canonical package
prices are unchanged, so the knowledge-compiler pricing lint still passes.

## The honest caveat — this is inference, not evidence
**Zero prospect conversations have happened.** This re-rank is reasoning from deal
economics, not from anything a customer said. It is explicitly **provisional**:
~20 real conversations with remodelers could overturn it in an afternoon (a common
answer is "we're booked 9 months out" — which would kill the lead vertical outright
and promote med spas).

**This ADR is not a substitute for making calls.** The pressure test's primary
finding was that the system has sent zero emails while the engineering compounds.
Re-ranking the ICP is cheap; validating it requires the phone. Next action is
conversations, not more configuration.

## Consequences
- Hunts now fill with businesses whose economics can actually carry the ask.
- Outreach stops being spent on ~$400-ticket repair shops.
- The pitch can lead with arithmetic ("one extra job pays for 4 months").
- Accepted risk: we may be wrong about remodelers' demand — first 20 calls settle it.

## Linked
- [[0006-sdr-refocus-and-subtraction]] · [[0010-consolidation-before-features]] · [[business-model]] · [[profitability-plan]] · [[active-context]]
