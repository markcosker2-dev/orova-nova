---
name: session-2026-07-24-strategy-pressure-test
description: Full record of the PG-style pressure test, customer-discovery pass, and competitive map — the analysis behind ADR-0012 and ADR-0013
type: session
created: 2026-07-24
status: active
---

# Strategy pressure test — startup evaluation, discovery, competition (2026-07-24)

Three analyses run back-to-back. Decisions extracted into
[[0012-icp-rerank-and-pilot-pricing]] and
[[0013-painkiller-positioning-and-real-competition]]; this note is the reasoning.

---

## Part 1 — Startup evaluation (Paul Graham style)

### Core assumption
> A California business owner who has never heard of OROVA will pay **$4,000-5,000/mo
> plus $2,000-2,500 ad spend** off a cold approach, with **zero case studies and zero
> referrals.**

Everything else is downstream. **Testable in a week for $0:** 100 hand-written
touches; if it can't produce 2 conversations, no amount of AI repairs it.

### Three fatal flaws (ranked)
1. **Built a sales robot instead of making sales.** Vault states plainly: *"Nothing
   has been emailed."* Three weeks of engineering, 12 PRs on 07-23/24 alone, **zero
   emails ever sent.** The system is never "ready" — today names, tomorrow
   deliverability, then warmup, then the CALICO key. **Automating a process never
   once performed manually.**
2. **The affordability squeeze.** All-in ask is $6,500-7,500/mo. Businesses small
   enough to lack an agency often can't afford it; businesses big enough (franchised
   luxury dealers) have OEM co-op budgets and corporate marketing mandates. The
   viable band is far narrower than the funnel math assumed.
3. **Selling a service never delivered, and the margin math hides that the founder
   IS the delivery.** No client campaign ever run; `case_studies` is a placeholder.
   The 97% margin assumes AI does delivery — but Mark runs every call, strategy,
   creative approval, and escalation. Bottleneck at ~3 clients.

### Problem validation
**Pain is real; the wedge is not.** Businesses demonstrably pay agencies $3-10K/mo —
proven market, not invented demand. But **zero conversations** means zero evidence
anyone will pay *OROVA*. The "you're talking to our AI right now" differentiator is
a founder's differentiator, not a buyer's.

### Founder-market fit
**Strong builder, weak fit for the chosen business.** Genuinely impressive execution
(multi-lane autonomous system on a 512MB free tier, ADRs, per-field provenance,
never-fabricate discipline). But no evidence of: running Meta ads profitably for a
client, agency/sales experience, or relationships in any target vertical. *The asset
is the machine; the chosen business is ad buying.* (Note: pivoting to selling the
SDR tool is **not** the escape — that market is Clay/Apollo/Instantly/Artisan/11x,
several well-funded and still grinding.)

### Verdict
**WEAK — would not be funded in current form.** Not because the market is wrong, but
because a month was spent proving he can *build* and zero days proving anyone will
*buy*. The fix is not a pivot; it's **inverting the order of operations**: sell by
hand first, automate what worked.

---

## Part 2 — Customer discovery

### The two pains (they demand opposite products)
- **Pain A — The Gap** (episodic, existential): job wraps in 3 weeks, nothing
  signed, six W-2 guys (~$30-40K/mo) burning. Next step is laying off a lead
  carpenter. → **creates urgency, closes deals.**
- **Pain B — The Wasted Saturday** (weekly, chronic): 40-minute drive, 3 hours
  writing the proposal that night, homeowner ghosted / wanted $60K work for $22K /
  was collecting a third quote. **Six times last month.** → **the wedge** (clears
  the weekly bar).

**More leads (P1) worsens Pain B.** Only qualification (P2) fixes it.

### Early adopter — a person, not a demographic
> **"Mike R., 44.** 6-10 person high-end remodeler in **Sacramento or the Inland
> Empire** (not LA/Bay — saturated, expensive CPMs). **$1.5-3M/yr**, average job
> **$80-150K**. Runs **every estimate himself**, nights and weekends. ~70% of work
> from referrals + an **Angi subscription he resents**. Backlog **~6 weeks, not 9
> months**. **W-2 crew on payroll.** Never hired an agency; pitched by five."

Four qualifiers, all required: backlog <8 weeks · W-2 payroll · owner runs estimates ·
already paying for leads and unhappy.

### The 5 discovery questions
1. Walk me through how you got your last three jobs.
2. Tell me about the last estimate you drove out to that didn't close. What happened?
3. What does your schedule look like past [two months out]?
4. What have you tried to get more of the right kind of job, and how did that go?
5. What happens if the next job isn't signed when the current one wraps?

*Past behaviour only. Never yes/no. Never mention Meta, AI, or OROVA.*

### Validation criteria
**Real if observed:** already paying for leads *and* complaining · a cobbled-together
system (lead spreadsheet, self-run Instagram, 9pm callbacks, nephew's website) ·
names the street and the drive · volunteers backlog anxiety unprompted · visible
annoyance about Angi.

**Kill signals:** "booked into next spring" · all referral and happy · can't recall a
wasted estimate · no payroll.

**Bar:** ≥8 of 20 hitting (not booked) + (paying for leads) + (specific wasted
estimate in last 2 weeks) → real, proceed. ≤3 of 20 → wrong vertical, switch to med
spas. **Only real validation: ≥2 agree to a PAID pilot.**

### Vitamin or painkiller — VERDICT
**Both — determined entirely by *when* you catch him.**
- 9-month backlog → **VITAMIN.** Won't pay $6,500. Most established remodelers in a
  hot market are here, and this is the most likely way 20 calls come back negative.
- Crew on payroll + <8 weeks backlog → **PAINKILLER.** Idle crew bleeds $30-40K/mo;
  $6,500 to stop it is arithmetic, not a marketing decision.

**Consequence:** the targeting problem is a **timing** problem, not a vertical
problem → hunt pipeline-gap *signals* (running Angi ads, hiring carpenters, "now
accepting projects," recent flagship job), not just the vertical.

---

## Part 3 — Competitive map

### What he does today (the incumbent)
Referrals + past clients + yard signs (**50-80% of his work**) · Angi/HomeAdvisor/
Thumbtack (~$300-800/mo) · architect/designer referral partners · Houzz · Google
Local Services Ads · Nextdoor · his own Instagram · **and most often: nothing, he
waits.** Note what's absent: an agency. Most remodelers this size have never hired one.

### Direct
Remodeler-only agencies (30+ case studies — **they beat us on PROOF**) · local
generalist at $1.5-3K/mo · Upwork freelancer at $500-1.5K/mo · exclusive per-lead
vendors ($50-200/lead, no retainer).

### Indirect (assessed: awareness / switching cost / satisfaction)
| Alternative | A | S | Sat | Note |
|---|---|---|---|---|
| Angi/HomeAdvisor/Thumbtack | MAX | LOW | **LOW** | 🟢 **best beachhead** — paying, unhappy, easy to leave |
| Google Local Services Ads | MED-HIGH | LOW | **MED-HIGH** | 🔴 **threatens the premise** — search intent beats interruption here |
| Houzz Pro ($65-400/mo) | HIGH | LOW-MED | MED | cheaper *and* bundles estimating + PM |
| **Hiring a person** ($4-5K/mo) | MAX | HIGH | MED | 🔴 **$6,500/mo IS a salary** — founders always miss this |
| CRM/follow-up SaaS ($100-400) | MED | LOW | MED | solves lead leakage at 3% of our price |
| Answering service ($200-500) | MED | LOW | MED | solves "I miss calls on the job site" |
| Raise prices / better jobs | HIGH | ZERO | — | fixes margin with no leads at all |
| **Meta Advantage+** | LOW | — | — | 🔴 structural: platform automation erodes "you need an expert" |

### The real enemy
1. **Inertia** — doing nothing. Zero switching cost, 15 years of working. Beaten
   only by a deadline he already feels.
2. **The Angi price anchor** — ~$400 vs our ~$6,500 = **16x**. Never argue price;
   **change the unit** (cost-per-idle-week-of-payroll / cost-per-wasted-Saturday).

### Genuine differentiation
**One real differentiator:** every lead phoned and AI-qualified within minutes → he
only drives to real buyers. Nobody else in the stack does this.

**Three weaknesses, stated honestly:** can't prove it (zero case studies — this is
what the pilot buys) · copyable in ~a month (Retell/Vapi/Bland are commodity APIs —
a timing lead, not a moat) · irrelevant to Pain A prospects (they need volume).

**Only durable moat:** proof in one narrow niche. Five kitchen-remodeler case studies
makes us the obvious call for the sixth.

---

## Decisions on the Eric Curran call
**Do NOT drop him.** ADR-0012 demoted exotic auto for *hunt quota*, explicitly
keeping "work inbound and existing leads." He is the **only contactable lead that
exists right now** (remodeler pipeline is empty until the next hunt), he's the
**free practice rep** before burning lead-vertical prospects, and one call tests the
Meta-channel-fit hypothesis for exotic autos. Run it as **discovery, not a pitch**
(his Pain A equivalent is **inventory aging** — floor-plan interest + depreciation
on a $200K car sitting 6 months).

**Also:** the 20 remodeler calls do **not** depend on the pipeline. Google Maps,
20 minutes, start dialing. The system is for scale later.

## What shipped today
12 PRs, all deploy-verified: memory reclaim (#98-#100, ~150-250MB + jemalloc) ·
`outreach_ready` bar (#101) · name-engine foundation (#102) · LinkedIn source
(#103) + SerpAPI fix (#104, produced the **first lead to clear the bar** — Eric
Curran, conf 40→83 via cross-source agreement) · ICP re-rank (#105) ·
ADR-0011/0012/0013.

## Linked
- [[0012-icp-rerank-and-pilot-pricing]] · [[0013-painkiller-positioning-and-real-competition]] · [[0011-advanced-ai-technique-fit]] · [[session-2026-07-22-improvement-research]] · [[business-model]] · [[active-context]]
