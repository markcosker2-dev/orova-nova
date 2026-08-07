---
name: session-2026-08-07-retell-tool-hallucination-and-the-reverse-landmine
description: Both live Retell agents were told to call calendar tools that do not exist; fixed live. And main's business_context.json still contains the unauthorised free pilot, so the documented deploy step would re-arm it.
type: session
created: 2026-08-07
status: done
tags: [retell, calls, compliance, verification]
---

# Session: Retell tool hallucination, and the landmine pointing the other way (2026-08-07)

## Verified production state

`/health` → build `9df7400b43de`, `db ok`, `memory ok`. `origin/main` →
`9df7400b43de`. **No drift.**

`/api/metrics` → `leads_found 45` · `calls_made 0` · `emails_sent 0` ·
`replies 0` · `meetings_booked 0` · `cost $0.00`.

Leads moved 26 → 41 → 45 across this session. **The hunting lane is the only
part of the funnel that works.** Everything downstream is still zero.

`python -m pytest tests -q` on main: **821 passed**, 204s.

### Corrections to the 2026-08-06 handoff

| claim | actual |
|---|---|
| 26 leads | **45** |
| 12 PRs open | **18** (#127–#144), all MERGEABLE, all green |
| 23 queued numbers (20 unknown, 3 toll-free) | **41** — 38 geographic, 3 toll-free |
| `orova.io` is ours | **NOT in Mark's Cloudflare account** (he checked) |
| free pilot may be live in the agents | **already removed from both live agents** |

`orova.io` RDAP: registered **2025-09-28** via **Cloudflare Registrar**,
expires **2026-09-28**, `client transfer prohibited`. Cloudflare Registrar
sells only to its own account holders and does not park or resell — so it is
very likely under a second login of Mark's rather than a stranger's. It cannot
be "bought" as the Cowork agent suggested; it is already registered.
Confirmed available instead: `orova.agency`, `getorova.com`, `orovamedia.com`.

## What changed — applied live to Retell

**Both agents instructed the model to call `check_availability_cal` and
`book_appointment_cal`. Neither LLM had a `general_tools` field.** The inbound
prompt asserted *"You HAVE calendar tools."* Both gated their fallback on
*"only if the booking tool errors"* — and a tool that does not exist never
errors, so the fallback could never fire.

Failure mode: at the single highest-value second of the call — the prospect
saying "Tuesday mornings" — `gpt-4.1-mini` holds an unexecutable instruction.
The likeliest behaviour is inventing a slot, which the same prompt forbids two
lines later. That is a builder writing down an appointment that exists nowhere.

Fixed on both (`llm_56da0e89…c51256f` v19, `llm_2e8ffc46…bdd5` v0), updated in
place so the agents pick it up with no version repoint:

1. Verbal capture is now the **primary** path, not a fallback. Nova captures
   name, email (confirmed letter by letter) and **two preferred windows in
   their own words**, then says Mark confirms by email. Nothing is ever
   described as "booked".
2. Explicit "you have NO calendar tool, you cannot see availability, never say
   *let me check*" in both, plus a line in each **NEVER** list.
3. `"He's usually **free** first thing in the morning"` → `"usually **around**"`.
   Live in both agents, and exactly what #138 warned about — a builder
   half-hearing "free" on a cold call is how an offer nobody made gets inferred.
4. Inbound agent's post-call analyser scored `lead temperature` as *"Hot if
   they want **the pilot**"*. Rewritten. Field **names** left untouched so the
   `/api/retell/webhook` parser is unaffected.

## The landmine points the other way

`business_context.json` on **main** still contains the unauthorised offer, in
full, with a dollar figure:

> `step_3_the_offer.the_pilot`: *"Mark's taking on one or two builders to run
> this for free for two weeks… you'd cover the ad budget, around seven hundred
> and fifty dollars"* — and the same in `step_5_voicemail.message`.

And `_HOW_TO_DEPLOY` says: *"This script is the SOURCE OF TRUTH… Re-paste
whenever this changes."*

**So the live agents are the clean artifact and the repo is the dirty one.**
Following the documented process today would re-arm the unauthorised free
pilot into a live agent. This is only fixed on the **unmerged** #138 branch.

The repo is also now *thinner* than live in both directions — the live prompt
has the twenty-seven-second opener, the NO-NAME path, and the honest
"your licence is on the public state register" answer to *how did you get my
number*; none of that exists in `business_context.json`. After #138 merges,
the repo should be synced to the live prompt verbatim, not the other way round.

Deliberately **not** edited here: `business_context.json` has an open PR
against it (#138), and a competing edit on another branch would conflict.

## Call history — Retell is the system of record, not `/api/metrics`

20 calls total, lifetime:

- **19 web calls** — browser tests, 24–25 Jan 2026.
- **1 real phone call** — **2026-07-27 21:48 UTC, INBOUND** to
  `+17166703920`. Nova greeted, the caller said nothing, hung up at 22s.

So **0 outbound calls have ever been placed** (matching `calls_made: 0`), and
the one inbound call was silence — not a prospect conversation.

Lifetime Retell `combined_cost` ≈ **306 units (~$3.06)**, almost all from the
January web tests. Production reports `cost $0.00`, so **the cost counter does
not track Retell spend.** Worth knowing before the meter starts running.

Also found: **a phone number already exists** — `+17166703920`, type `custom`
(BYO/SIP, not Retell-purchased), nicknamed *"OROVA main - outbound Nova v19 /
inbound callback"*. It is a **716 (Buffalo, NY)** area code dialling
CA/OR/WA contractors, which is a local-presence problem for answer rates.

## Follow-ups

- [ ] **Merge the stack** — 18 green PRs; #129 first. Also un-strands 7 vault docs.
- [ ] **Merge #138 before ever re-pasting the script into Retell.** Until it
      lands, `business_context.json` on main will re-arm the free pilot.
- [ ] After the stack merges, **sync `retell_pitch`/`retell_inbound` to the
      live prompt verbatim** — the repo is currently the stale copy.
- [ ] **Approve the line-type lookup** (<$1): 38 geographic numbers; skip the
      3 toll-free, they are consent-required regardless.
- [ ] **Find the Cloudflare account holding `orova.io`** before it lapses on
      **2026-09-28**.
- [ ] **Rotate `nova_2026`.**
- [ ] Consider a local-presence caller ID; 716 dialling the West Coast is a
      measurable answer-rate drag.
- [ ] The offer — Mark's decision, but **not** on the critical path: both live
      scripts are offer-free by design and deflect every commercial question.
      It blocks Mark's meeting, not Nova's dial.
