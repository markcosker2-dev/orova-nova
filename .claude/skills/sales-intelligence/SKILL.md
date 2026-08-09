---
name: sales-intelligence
description: OROVA's sales craft layer for outbound to custom home builders and high-end remodelers (ADR-0012, ICP narrowed by ADR-0015) — cold calls, objection handling, follow-up cadence, and message QA. Phone is the live channel; cold email is deferred (ADR-0014 / 2026-07-30). Use when writing, reviewing, or improving any outreach (Retell call script, post-call follow-up, break-up note), when handling an objection or reply, or when tuning business_context.json / the Retell prompt. Triggers: "cold call", "call script", "outreach", "follow-up", "objection", "book a meeting", "sales script", "personalize", "QA this message".
---

# OROVA Sales Intelligence

> ⚠️ **ICP MOVED — body rewrite pending (2026-07-30, narrowed 2026-08-09).**
> ADR-0012 re-ranked the ICP to **custom home builders / high-end remodelers**
> (lead), then luxury RE, and **disqualifies general auto repair and franchised
> dealers on sight**. **ADR-0015 removed med spas entirely** — owner: *"our ICP
> was never med spas."* Any med spa guidance still in the body below is dead
> and must not be applied. PRs #119 and #120 now enforce that in code. The channel also moved:
> **phone (Retell) is live; cold email is deferred** (ADR-0014 — 0 of 8 providers
> permit cold outreach).
>
> Everything below still describes the **luxury-automotive** era, including
> `references/luxury-automotive.md`. Treat the *craft* (structure, objection
> handling, QA gate, follow-up cadence) as still valid and the *vertical
> specifics* as historical. Exotic/luxury auto remains "opportunistic only" per
> ADR-0012, so the automotive reference is not deleted — it is deprioritised.
> **Do not use the automotive hooks for a remodeler.**

The craft layer for OROVA's outbound to **luxury automotive** businesses (dealers,
exotic rentals, detailers, wrap/PPF, performance, restoration). This skill makes
Claude-family agents write and review outreach the way Mark would — consistently,
on-brand, and tuned to book qualified conversations.

> [!important] Sources of truth — do not contradict these
> - **Machine truth (what Nova sends):** `app/core/business_context.json`
>   (`email_rules`, `outreach`, `retell_pitch`, `value_propositions`, `services`).
> - **Voice & cadence law:** `vault/hermesclaw-orova/playbook/outreach-voice.md`
>   and the rest of `vault/hermesclaw-orova/playbook/`.
> This skill is the *technique* layer on top of those. When they conflict with a
> reference here, the playbook/business_context win, and you fix the reference.

## The six non-negotiables (know these without loading anything)

1. **We sell premium revenue growth, not "lead generation."** Never generic
   agency-speak ("we generate leads", "grow your business", "boost sales").
2. **Lead with the system promise / differentiator:** *"every lead is called and
   qualified within minutes — you only talk to people ready to buy,"* and *"you've
   already seen it work — that's how we reached you."* The product demos itself.
3. **The past is closed.** Zero past-client claims, names, numbers, or verticals.
   Never mention Mark's previous agency, any channel, ever. If asked "am I your
   first?": *"No — I've signed and worked with clients before."*
4. **Cadence is a hard cap:** 1 email → up to 3 follow-ups (different days) → 1
   cold call → mark cold, never contact again. **Five touches, ever.** The
   break-up email must be true.
5. **Price is the price.** P1 $4k/mo, P2 $5k/mo (tiers in business_context). No
   discounts, no freebies, no fake urgency, no spam-trigger words.
6. **Compliance:** business lines only (TCPA); the voice agent discloses AI when
   asked; ad spend / signing / publishing are always human-approved.

## Routing — load one reference only when the task needs it

| Task | Load |
|---|---|
| Write/review a cold email | `references/cold-email.md` |
| Write/review a call script (human or Retell) | `references/cold-calling.md` |
| Handle a reply, objection, or hard question | `references/objection-handling.md` |
| Build/adjust the follow-up sequence or break-up | `references/follow-up-sequencing.md` |
| Score a message before it sends (the QA gate) | `references/qa-checklist.md` |
| Get the exact positioning / what we sell / forbidden language | `references/positioning.md` |
| Vertical hooks for exotic/luxury AUTO only — historical, opportunistic per ADR-0012. No remodeler/med-spa reference file exists yet; use `references/positioning.md` for those. | `references/luxury-automotive.md` |
| Push changes into Nova/Retell, or wire A/B + learning | `references/integration.md` |

Keep outputs tight: a cold email is ≤75 words, a call opener is two sentences.
Personalize on **their** business first, ask second. When unsure, escalate — see
`vault/hermesclaw-orova/playbook/escalation.md`.
