# Discovery (technique — the questions live elsewhere)

Assumes `cold-calling.md`. That file owns the **arc**; this one owns **how to
use** the questions.

> [!important] The questions are machine truth, not craft
> They live in `app/core/business_context.json > discovery_questions` and that
> is the only place they are written down. Do not restate them here, in a
> persona, or in an agent file — three copies that drift are worse than one
> that's wrong, because at least the wrong one can be fixed in one place.
>
> Its `_rules` field is the constraint that governs everything below:
> **"Open-ended only. Ask about PAST behaviour, never a hypothetical purchase.
> Do not mention Meta, AI, or OROVA. Diagnose, do not pitch."**

## Why "past behaviour, never hypothetical" beats textbook SPIN

Classic SPIN implication questions are future-conditional — *"if this continues
for another six months, what does it cost you?"* They are the most-taught tool
in discovery and **they violate the rule above.** A hypothetical invites a
hypothetical answer; a contractor can imagine a bad spring cheaply and commit to
nothing.

The canonical questions do the same job with evidence: *"Tell me about the last
estimate you drove out to that didn't close. What happened?"* He has to retrieve
a real event, with a real drive, a real hour, and a real number. That is what
creates urgency — not a projection he can wave away.

**So: use the canonical questions. Where you need to go deeper, go deeper into
what already happened, not into what might.**

## Rule 1 — never ask what the licence record already told you

Before the call you have: business name, principal name, trade, years licensed,
principal count, insurance cover. Asking "so what do you guys do?" spends the
only credibility a cold call has. Research before, discover during.

## Rule 2 — 60/40, in their favour

If you are talking more than 40% of the time you are pitching. On a Retell call
this is measurable after the fact; check it on any call that didn't book.

## Rule 3 — silence is a tool

After a hard question, wait. The first answer is the surface answer; the one
after the pause is the real one. The agent must not fill a two-second gap.

## Rule 4 — go for root cause, not symptom

"Leads are slow" creates nothing. "I'm the only one who answers the phone and
I'm on a roof until 4" creates a meeting. Keep going until you have the
mechanism.

Then ask the disqualifying question: **can they close this gap without us?** If
yes, there is no deal — say so and end cleanly.

## Rule 5 — branch on crew status, never guess it

`crew_status` arrives as `solo` / `has_crew` / `unknown` from
`lead_validator.crew_status`, derived from the licence registry's named
principals. It is a first-class variable on every Retell call.

| Status | Their pain | Do not |
|---|---|---|
| `solo` | Being estimator, foreman, and the person returning calls at 9pm | Use crew-scale or payroll language |
| `has_crew` | Keeping people busy — payroll is an external deadline | Assume they answer their own phone |
| `unknown` | Don't guess — 58.9% are single-principal, so it's a coin flip | Open on either pain |

> **Solo is a discount, not a disqualification.** 126 of 300 contractors above
> the $1M minimum (42%) are sole operators — they can pay; the urgency is
> personal rather than payroll-driven.
>
> `kill_signals` used to carry *"No payroll (solo operator) - no urgency"*,
> which disqualified exactly that segment. Removed 2026-08-12 and pinned by
> `tests/test_solo_is_not_a_kill_signal.py`. The remaining kill signals are
> evidence-based — they kill on what he *said*, not on how many principals are
> on his licence, and they already catch a solo owner who genuinely has no pain.

## Objections — Acknowledge, Empathize, Clarify, Reframe

Full bridges live in `objection-handling.md`. The skipped step is **Clarify** —
you cannot handle an objection you haven't diagnosed: *"When you say the timing's
off — is that a workload thing or a money thing?"*

> **Value objections cannot be answered with price.** `commercial_terms` is
> UNRESOLVED — there is no number to quote and nothing to discount. If discovery
> was thorough, the answer is the gap he described in his own words.

## Qualify out fast

`discovery_questions.kill_signals` is the canonical list. No pain, no authority,
no timeline is not a lead — it's a forecast lie, and ending cleanly protects the
five-touch cap for someone who deserves it.

## Read the call afterwards

**Landed it:** he pauses before answering · he tells you something unplanned ·
he asks "so how would that actually work?" · you restate his situation and he
says "exactly".

**Rushed it:** pitched inside the first minute · one-word answers · you can't say
why this is a priority now versus six months ago.

The honest scoreboard is `validation_bar` in `discovery_questions`: of 20 calls,
≥8 hitting all three signals means the problem is real; ≤3 means the pitch or
the vertical is wrong — stop and escalate to Mark with transcripts.

---

*Technique framing (SPIN, Gap Selling, Sandler) adapted from
[`sales/sales-discovery-coach.md`](https://github.com/msitarzewski/agency-agents)
(MIT, © 2025 AgentLand Contributors). Question content deliberately not copied
here — `business_context.json` owns it.*
