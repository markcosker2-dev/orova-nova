---
name: 0013-painkiller-positioning-and-real-competition
description: Sell the painkiller not the vitamin, diagnose the pain before prescribing the package (P2-first for wasted-estimate pain), and treat inertia + the Angi price anchor as the real competitors
type: decision
created: 2026-07-24
status: accepted
---

# ADR-0013 — Painkiller positioning + the real competition

## Status
Accepted (owner directive 2026-07-24, from a customer-discovery pass and a
competitive map run the same day). Builds directly on
[[0012-icp-rerank-and-pilot-pricing]]. **Supersedes `profitability-plan` §2.2's
"lead with Package 1" guidance** — see Decision 2.

## Context
Two analyses, one conclusion: **the product is the same but the pitch was aimed at
the wrong thing.**

- Customer discovery named **two distinct pains** in the remodeler ICP, and they
  demand *opposite* products.
- The competitive map found the dangerous competitors are not agencies at all —
  they are a **habit** (doing nothing) and a **reference price** (Angi at ~$400/mo
  against our ~$6,500 all-in ask, a 16x anchor).

## Decision

### 1. Lead with the painkiller, never growth
Growth framing ("we'll get you more leads") is a **vitamin**, and it competes
head-on with Angi's price anchor — a fight we lose at 16x. Painkiller framing:

- **Pain A — The Gap:** *"When your crew finishes the job they're on, what's next?"*
  The job wraps in 3 weeks, nothing is signed, six guys on W-2 payroll (~$30-40K/mo)
  burning. Episodic but **existential** — this is what creates urgency and closes.
- **Pain B — The Wasted Saturday:** *"You'll never drive 40 minutes to a tire-kicker
  again."* Drove out, measured, wrote the proposal at night, homeowner ghosted —
  six times last month. Felt **weekly**, which makes it the wedge.

### 2. Diagnose before prescribing (supersedes profitability-plan §2.2)
| Pain found on the call | Prescribe |
|---|---|
| Empty pipeline (Pain A) | Package 1 **or** Package 2 — he needs volume |
| Drowning in bad leads (Pain B) | ~~Package 2 ONLY~~ → **Package 3** (see below) |
| Both | Package 2 |

**P1 makes Pain B worse** — more leads means more wasted Saturdays. The prior
"always lead with P1 because it's the lower-friction yes" guidance is wrong when
the pain is qualification, not volume. Ask first; prescribe second.

> [!important] Amended 2026-08-22 — Pain B is now Package 3
> "Package 2 ONLY" was correct while P1 and P2 were the only options: *not P1*
> then meant *therefore P2*. **Package 3** — the AI qualification caller sold
> standalone at $3,000/mo — makes that inference false.
>
> A man drowning in bad leads is **not short of leads**. Prescribing P2 sells
> him $5,000/mo *plus* $2,000–2,500 of ad spend to fix a pipeline that is not
> empty. P3 is $3,000, no media, and is exactly his problem — cheaper for him
> and a cleaner fit.
>
> **The reasoning above is untouched and still right.** P1 still makes Pain B
> worse; a painkiller still beats a vitamin. Only the prescription moved,
> because a third door opened.
>
> This matters more than a copy tweak: Pain B is the diagnosis the
> [[0017-the-sample-is-the-proof|ADR-0017]] demo call produces most often. A
> contractor who has just let an AI qualify him has, by definition, leads worth
> qualifying — so the prescription that fires hardest after a successful demo
> was the one pointing at the wrong package.

### 3. Timing qualifies harder than vertical
Four qualifiers, **all four must be true**:
1. **Backlog under ~8 weeks** — THE qualifier. Booked solid = zero pain = disqualify.
2. **W-2 crew on payroll** — fixed cost is the urgency engine; a solo operator coasts.
3. **Owner runs his own estimates** — so the wasted time is *his*.
4. **Already paying for leads and unhappy** — the wallet already opens for this.

The same business is a vitamin or a painkiller **depending only on when you catch
it**. Pain is a property of the *moment*, not the vertical.

### 4. The real enemy is inertia, then the price anchor
- **Enemy #1 — doing nothing and waiting.** Awareness MAX, switching cost ZERO,
  satisfaction "acceptable." Costs $0, needs no decision, has worked 15 years.
  *"Let me think about it"* means *"I'll wait and see if referrals cover it."*
  **Only a deadline he already feels beats it** — hence qualifier #1 and #2.
- **Enemy #2 — the Angi anchor.** He pays ~$400/mo; we ask ~$6,500. He does not
  compare us to an agency, he compares us to *the number he already pays for what
  he thinks we sell*. **Never argue the price down — change the unit**: from
  cost-per-lead to **cost-per-idle-week-of-payroll** or **cost-per-wasted-Saturday**.
  If the conversation stays on "leads," Angi wins on price.

### 5. One differentiator; three forbidden pitches
✅ **Use:** every lead is phoned and qualified by AI within minutes, so he only ever
drives to a real buyer. Angi sells the same lead to four competitors and hangs up;
Houzz gives a profile; a local agency hands over a form fill. **None of them call
the homeowner in five minutes.**

❌ **Never pitch:** "we're AI-operated so our margins are better" (he doesn't care
about our P&L) · "you're talking to our AI right now" (a party trick — he's buying
kitchen leads) · "AI-generated creatives" (commodity claim in 2026).

### 6. Hunt the signal, not the vertical
We cannot tell from Google Maps whether a builder's backlog is 6 weeks or 9 months.
Future Nova capability: hunt **pipeline-gap signals** — actively running
Angi/Thumbtack ads, hiring posts for carpenters, "now accepting new projects"
language, a recently-completed flagship job. This converges with the 2026 research
in [[session-2026-07-22-improvement-research]]: **signal-based outreach replies at
5-18% vs 1-3% generic.**

## Consequences
- `business_context.json` now carries `icp.pains`, `icp.early_adopter_qualifiers`,
  `discovery_questions`, `competition`, a rewritten `differentiator`, and a
  painkiller-first `outreach.initial_email_framework.value`.
- Nova's outreach should stop selling growth and start naming the deadline.
- Accepted risk: **P2-first raises the price of the first yes** ($5K vs $4K). The
  first-client pilot ([[0012-icp-rerank-and-pilot-pricing]]) absorbs that.

## The honest caveat (unchanged from ADR-0012)
**Still zero prospect conversations.** Both pains, the early-adopter profile, and
the competitive weighting are *inference* — well-reasoned, unvalidated. The
discovery questions and the >=8-of-20 validation bar exist precisely because this
needs to be tested, not believed. **No further positioning work should happen
before 20 calls.**

## Linked
- [[0012-icp-rerank-and-pilot-pricing]] · [[business-model]] · [[orova-playbook]] · [[profitability-plan]] · [[session-2026-07-22-improvement-research]]
