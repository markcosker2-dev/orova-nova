---
name: business-model
description: What OROVA sells, to whom, at what price — the commercial source of truth
type: brain
created: 2026-07-03
status: active
---

# OROVA Business Model

**OROVA is a marketing agency that runs Meta ads (Facebook + Instagram) for luxury/premium businesses in the US — West Coast only for now.** Goal: a 1–2 person, AI-operated agency. Machine-readable twin of this note: `app/core/business_context.json` (keep both in sync).

## Packages

| | Package 1 — $4,000/mo | Package 2 — $5,000/mo |
|---|---|---|
| Meta lead gen (FB + IG) | ✅ | ✅ |
| Ad creatives via **Higgsfield** AI | ✅ | ✅ |
| Lead handling | Client handles their own leads | ✅ OROVA handles it |
| AI cold-call qualification (**Retell.ai**) | — | ✅ every lead called & qualified |
| Client CRM kept current (Google Sheets or client's CRM via **Make.com**) | — | ✅ |
| Appointment booking | — | ✅ when the business monetizes via appointments |
| Ad spend (client-paid, separate) | $2,000–$2,500/mo recommended | $2,000–$2,500/mo recommended |

### Term pricing

New clients start on a **1-month trial**, then choose 1 / 3 / 6 months. Payment
by invoice via **Wise transfer or ACH**. Ad spend is paid by the client **directly
to Meta**.

> **Always quote and think ALL-IN: ~$6,500–7,500/mo** (retainer + recommended ad
> spend). The client writes checks totalling that number and asks "what do I get
> for $6,500?" — never "what do I get for $4,000?". *"The ad spend is separate"* is
> an accounting fact, not a buying fact; using it makes the ask sound 60–85%
> smaller than it is. (ADR-0012)

### Client #1 — pilot pricing (ADR-0012)

**Client #1 buys proof, not revenue.** With zero case studies, offer
**$1,500–2,000/mo for a 60-day pilot** (or performance-tied) in exchange for a
testimonial, case-study rights, and permission to quote results. Standard P1/P2
pricing resumes at **client #2**, once a real case study replaces the placeholder
and does the selling. Holding the line at $4K with nothing to show is how
pre-revenue agencies stay at $0. *(Canonical package prices above are unchanged.)*

| Term | Package 1 | Package 2 |
|---|---|---|
| 1 month | $4,000 | $5,000 |
| 3 months | $10,000 | $13,000 |
| 6 months | $18,000 | $24,000 |

(6-month corrected 2026-07-04 so longer = cheaper per month: P1 $3,000/mo, P2 $4,000/mo.)

Full operating detail — sales funnel, delivery, automation/approval split — is in
[[orova-playbook]].

## ICP

**Re-ranked 2026-07-24 by deal economics ([[0012-icp-rerank-and-pilot-pricing|ADR-0012]]).**
The filter that decides everything:

> **Does ONE extra closed deal per month more than cover the ~$6,500–7,500 all-in
> monthly cost?** If no, disqualify — the price objection can't be closed.

West Coast (CA, OR, WA, NV, AZ), ranked:

| # | Vertical | Gross/deal | Deals needed | Why |
|---|---|---|---|---|
| **1** | **Custom home builders / high-end remodelers** — LEAD | $20–50K on a $100K+ job | ~0.2 | One extra job pays 4–7 months of retainer. Owner-operated, already buys marketing, proven Meta lead-gen. |
| **2** | Med spas / aesthetics / high-ticket elective medical | $3–15K per patient | 1–2 | The most-proven Meta lead-gen vertical; the doctor/owner decides alone. |
| **3** | Luxury real estate — **top producers only** | commission | ~1 | Score for production volume first; $4K/mo is a big bite of a solo agent's P&L. |

**Opportunistic only:** exotic/luxury automotive — the unit economics work
(~$10–25K gross/car) but a $200K buyer rarely starts on a Meta lead form. Work
inbound and existing leads; don't lead the hunt with it. (Was the #1 vertical and
50% of the hunt rotation before ADR-0012.) Private aviation & yacht charter remain
opportunistic — decision-makers are family offices/brokerages, not owners reading
cold email.

**Disqualify on sight:** general auto repair / transmission / oil-change (~$400
gross → ~16 extra jobs/mo to break even, and no $6.5K budget) · franchised new-car
dealers (OEM co-op + corporate marketing mandates) · anyone already under agency
contract who hasn't volunteered dissatisfaction.

> ⚠️ This ranking is reasoning from deal economics, **not** from customer
> conversations — zero have happened. ~20 calls with remodelers could overturn it
> (a common answer is "we're booked 9 months out"). Validate before scaling on it.

## Economics of the first client

- One Package 2 client = $5K MRR → funds better tooling (Anthropic subscriptions, paid enrichment/verification, Render paid tier).
- Nova's own pipeline (this repo) is the demo: "you're testing the product right now" is the signature move on cold calls.

## Positioning line

> "We run the Meta ads that bring the leads in, our AI makes the creatives, calls every lead within minutes to qualify it, keeps your CRM current, and books the serious ones onto your calendar. You only talk to buyers."

## Linked

- [[active-context]] — current operational state
- [[0001-adopt-obsidian|ADR-0001]] — knowledge layer
