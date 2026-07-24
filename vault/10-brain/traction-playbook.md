---
name: traction-playbook
description: How to find and convert the first 10 customers manually, and the 2-week MVP that tests whether OROVA can actually deliver
type: brain
created: 2026-07-24
status: active
---

# Traction Playbook — first 10 customers + the MVP

Companion to [[0012-icp-rerank-and-pilot-pricing]] and
[[0013-painkiller-positioning-and-real-competition]]. Target customer: **"Mike R."**
— 6-10 person CA high-end remodeler, $1.5-3M/yr, $80-150K jobs, runs his own
estimates, backlog <8 weeks, W-2 crew, already paying Angi and resents it.

## Constraint that shapes everything
Mark is in the **Philippines (UTC+8), 15h ahead of California**, and cannot
economically dial US numbers. So "do things that don't scale" **cannot mean the
phone**. It means channels where he has zero geographic disadvantage:
**Instagram DMs, Loom videos, email.** Retell owns all cold dialling in parallel.

---

## 1. Where the first 10 are

### 🔑 Meta Ad Library — start here
`facebook.com/ads/library` → Country: US → search "remodel", "kitchen remodel",
"home builder" + target cities. Shows **exactly which remodelers are paying to run
Facebook ads right now**, plus their actual creative.

That single fact satisfies the ICP qualifier (*already paying for leads*), proves
budget and channel fit, and gives a concrete thing to talk about. **A remodeler
running BAD Facebook ads is the warmest cold prospect available.**

> Nova cannot query this programmatically — see [[#Why Nova can't scrape the Ad Library]].
> Mark browses it manually and CSV-imports the names (`POST /api/leads/import-csv`).

### The rest
- **Instagram** — `#kitchenremodel` + city, `#customhomebuilder`, geotags. They post
  compulsively and they read DMs.
- **Facebook local groups** — "[City] Home Improvement", neighbourhood groups where
  homeowners ask *"who should I hire?"*. **The contractors racing to answer are
  hunting work** = the thin-backlog signal, visible free.
- **Google Local Services Ads** — anyone in the LSA block is paying per lead.
- **Houzz / Angi / Thumbtack pro listings** — already buying leads.
- **NARI / NAHB local chapter directories** — public member lists.

## 2. Manual outreach approach

**Centrepiece: a 2-3 minute personalised Loom.** Screen-record *their* Facebook page
or Ad Library entry: "here's your ad, here's what I'd change, here's what the shop
two towns over does differently."

Why it fits Mark exactly: works from the Philippines, async, $0, and it
**demonstrates competence instead of claiming it** — which directly attacks the
biggest weakness (zero case studies). Unscalable, therefore high-signal.

**Order:** Instagram DM → Loom link → email follow-up. **5-10 per day maximum**, each
researched. If you can do 50/day you're doing it wrong.

## 3. The first message (asks for nothing)

```
Hey {name} — saw the {specific project} you posted. Genuinely clean work.

Not pitching you anything. I run Facebook ads for remodelers and I'm trying to
understand what actually works in the {city} market before I have anything useful
to say. Are most of your jobs coming from referrals, or are you running ads too?
```

Follow-up once he replies (this is where the Loom goes):
```
That's really helpful, thanks. I pulled your page up in Meta's ad library and
recorded a quick 2-min video of what I'd change — no strings: {loom link}
```

**Never in message one:** pricing · "quick call?" · a Calendly link · "I help
remodelers get more leads."

## 4. Success criteria — the "devastated" test

| Signal | Meaning |
|---|---|
| Replies to a cold DM with a real answer | Message worked |
| Responds to the Loom's *content* | You have credibility |
| **Gives ad-account access** | 🔥 Major commitment |
| Shows up to the appointments booked | The leads are real |
| **Asks unprompted "when's the next batch?"** | 🔥🔥 The devastation proxy |
| **Refers another contractor** | 🔥🔥🔥 Strongest signal in the business |
| Pays after the free pilot | PMF |

**Not success:** "looks interesting" · "send me info" · "touch base next quarter."

---

## 5. The MVP — what it actually tests

Two unvalidated assumptions. Separate them:

| Assumption | Tested by | Cost |
|---|---|---|
| **Acquisition** — a remodeler will engage/pay | The outreach + Retell calls | $0 |
| **Delivery** — *can OROVA actually produce qualified appointments* | **THIS MVP** | ~$750 |

**The MVP tests DELIVERY:** *can OROVA produce qualified, showed-up estimate
appointments for a remodeler from Meta ads, at a cost that makes $6,500/mo obviously
worth it?* Zero evidence exists — no client campaign has ever been run. **If it's
false, there is no product to sell.**

### Minimum feature set — SIX things, zero code
1. One remodeler who says yes (free pilot, they cover ~$750 ad spend direct to Meta)
2. One Meta lead-gen campaign — ONE audience, ONE offer, 3 creatives
3. Meta instant form — 4 questions: project type · timeline · budget · zip
4. **A human calling every lead within 5 minutes** (this IS the "AI qualification"
   for the MVP — deliver it by hand first)
5. A calendar link
6. One spreadsheet: lead → minutes-to-call → qualified → booked → **showed up**

### What gets cut for the duration
Nova's SDR loop, the waterfall, enrichment, dashboard, CRM/Make.com, drip
sequences. **Cut ≠ delete** — don't touch the repo for 14 days. It's built for client
#10, not client #1.

### Pass criteria (from ~$750 ad spend / 14 days)
≥15 leads · ≥8 reached within 5 min · ≥5 qualified · ≥3 booked ·
**≥2 appointments the remodeler ATTENDED** · **cost per showed-up appointment <$350**

**The signal that matters most:** on day 13 show him the numbers, ask *"do you want
me to keep this running?"*, then stay silent.

---

## 6. Weekly milestones

10 *paying* clients at $6.5K/mo is a 6-12 month goal (funnel math: 100-200 on-ICP
leads per client). The 10 here are **10 real relationships**.

| Week | Actions | Milestone |
|---|---|---|
| 1 | 50-name list from Ad Library + IG. 10 Looms, 10 DMs. Retell dials in parallel. | 3 replies |
| 2 | 15 more DMs+Looms. Take calls in the 9pm-midnight PH window. | 5 conversations, 1 pilot agreed |
| 3 | Launch pilot #1. Call every lead in 5 min. | Pilot live, first appointments |
| 4 | Deliver obsessively. 2 more pilots agreed. | 2 appointments HELD |
| 5-6 | Convert #1 to paid. **Write the case study with real numbers.** | 1 paying + case study |
| 7-8 | Case study replaces the placeholder. Ask client #1 for 2 referrals. | 3 paying |
| 9-12 | Referrals compound. **Now** automate what demonstrably worked. | 10 relationships, 5+ paying |

**Week 5's case study is the hinge.** Before it you push the boulder; after it the
boulder pushes you. Client #1 isn't revenue — it's the artifact that makes clients
#2-10 cheap.

---

## Why Nova can't scrape the Ad Library
1. The **Ad Library API covers political/issue ads only** — commercial remodeler ads
   aren't served by it.
2. The UI is a heavy React app needing **Playwright/Chromium, which Render's free
   tier cannot run** (same reason `browser_ops` was removed).
3. 🔴 **Decisive:** scraping Meta risks the **Meta account the entire business
   depends on**. Tiny upside (a lead list), catastrophic downside (no ad account =
   no product). Not a close call.

**Instead — capture the same signal free:** see the ad-signal detector spec in
[[session-2026-07-24-handoff]]. A Meta Pixel in their homepage HTML proves they run
Meta ads; an Angi/HomeAdvisor badge proves they pay for leads *and* names the
competitor. Nova already fetches that HTML.

## Linked
- [[0012-icp-rerank-and-pilot-pricing]] · [[0013-painkiller-positioning-and-real-competition]] · [[business-model]] · [[active-context]]
