---
name: session-2026-08-06-security-offer-and-the-open-channel
description: Leaked key scrubbed and CI-gated, the unauthorised free pilot removed, both state owner-lookups fixed after measuring them, and the Instagram research lane built
type: session
created: 2026-08-06
status: active
tags: [session, security, offer, owner-finder, instagram]
---

# Session — 2026-08-06 · security, the offer, and the open channel

> [!abstract] Continuous session, owner instruction "work until done"
> Six PRs shipped ([#136](https://github.com/markcosker2-dev/orova-nova/pull/136)
> · [#137](https://github.com/markcosker2-dev/orova-nova/pull/137)
> · [#138](https://github.com/markcosker2-dev/orova-nova/pull/138)
> · [#139](https://github.com/markcosker2-dev/orova-nova/pull/139)
> · [#140](https://github.com/markcosker2-dev/orova-nova/pull/140)
> · [#141](https://github.com/markcosker2-dev/orova-nova/pull/141)),
> on top of the three from 2026-08-05. **Nothing merged — merging remains the
> owner's action.**

---

## 1. The pattern that repeated all day

**Every single thing I built was wrong the first time, and measuring caught it.**
Recording this because it is the transferable part:

| What I believed | What measuring showed |
|---|---|
| Free domain-guessing resolves websites | 87% "resolved", **7% correct** — the rest were same-named firms in other states |
| A name+city rule would fix that | It accepted the **Pennsylvania** Cedar Creek for an Oregon lead |
| A name+"city, ST" rule would fix *that* | Fired on **0 of 20** real leads — a rule that never fires is noise |
| A name-based secret scanner is fine | Flagged 4 inert lines (`MAX_TOKENS`, a Google URL, two storage-key names) |
| The OR SoS scrape works, just weakly | **0/10** on real contractors; the host doesn't answer at all |
| The WA lookup works | **2/14** on names containing `&` — it could not find owners in its own registry |

Not one of these was visible by reading the code. All six needed a live run
against real rows.

---

## 2. Security — the leak is closed ([#137](https://github.com/markcosker2-dev/orova-nova/pull/137))

The incident write-up's one open item — *"the old key remains in those 7 files.
Nobody has done this"* — is done.

Verified first: **16 occurrences, exactly 7 tracked files, 24 commits.** The
local `.env` still holds the same value, which is the direct cause of every
authenticated production check returning 403.

One was worse than documentation. `check_auth.py` used the burned key as a
**runtime fallback credential** — `os.getenv("DASHBOARD_API_KEY", <burned>)` —
so it was a live default, not an example.

**The gate matters more than the scrub.** `scripts/check_secrets.py` now runs in
CI *before* the tests. Version 1 keyed on variable names and cried wolf four
times; a scanner that does that gets disabled, and a disabled scanner is how the
first incident happens. Rebuilt around what a credential *is*: burned literals
(exact), provider formats (Stripe/AWS/GitHub/Slack/Google/PEM), and
secret-shaped names bound to values that also *look* random.

> [!success] Two independent confirmations
> Adding the test file to the index made the scanner **flag its own PEM
> fixture**. And **GitHub's own push protection rejected the first push**,
> correctly identifying the Stripe and Slack fixtures as real keys. I did not
> click the "allow this secret" bypass — that trains the repo to wave pushes
> through. The fixtures are now assembled at runtime.

---

## 3. The unauthorised offer is gone ([#138](https://github.com/markcosker2-dev/orova-nova/pull/138))

The free two-week pilot was in **five** prospect-facing places, not the three a
grep for "free" finds — `i_already_pay_angi` and `too_expensive_price_anchor`
leaned on it implicitly ("what the two weeks would show you").

**Why it reached production silently is the real finding: nothing in the
codebase reads `retell_pitch` or `retell_inbound`.** They are the
human-maintained source of truth pasted into Retell's dashboard, so an edit
becomes production speech with no test, no review and no deploy.

Now: a hard `_offer_rule` (**NOVA DOES NOT MAKE OFFERS. AT ALL.**), `never_say`
leading with the ban, `what_does_it_cost` deflecting with an escalation path,
`step_3_the_offer` renamed `step_3_describe_the_painkiller` (a key called
*the_offer* is how an offer ends up living there), and `"usually free first
thing"` → `"usually around"`.

**No replacement pricing invented — that is the owner's decision and stays
open.** `first_client_pilot` is preserved but marked INTERNAL THINKING ONLY;
deleting the owner's commercial reasoning is not mine to do, but presenting it
as an *instruction to offer* was the bug.

`tests/test_no_unauthorised_offer.py` matches **affirmative** constructions
("for free", "owe nothing", "$750") rather than the bare word, because the file
legitimately contains prohibitions — a test that cannot tell a ban from an offer
gets deleted the first time it cries wolf. Reinstating the original line
verbatim makes the suite fail; removing it makes it pass.

---

## 4. Both owner lookups were broken ([#139](https://github.com/markcosker2-dev/orova-nova/pull/139), [#140](https://github.com/markcosker2-dev/orova-nova/pull/140))

**Oregon** scraped the Secretary of State registry. Wrong twice over: it
returned an owner for **0 of 10** real contractors (the host does not answer —
a full connect timeout), and even working it returned a **Registered Agent**,
frequently a law firm, at confidence 0.7 — outranking a website scrape.
Repointed at CCB's Responsible Managing Individual: **13/14**, 0 fabrications.

**Washington** — found while fixing Oregon, and worse because WA is the state
actually running in production. The Socrata prefix was built from the
*normalized* name but matched against the *raw* one, so any stripped character
in the middle made a name permanently unmatchable:

```
"168 KITCHEN & BATH CORP"  →  normalizes to "168 KITCHEN BATH"
                           →  NOT a prefix of the stored name  →  missed
```

On real ACTIVE licences containing `&`, `.` or `,`: **2/14 → 14/14**. `&` is
everywhere in contractor names (`KITCHEN & BATH`, `DESIGN & BUILD`), so this was
never an edge case. Plain names: 14/14, no regression. Acceptance unchanged — a
looser search window does not loosen what is accepted.

---

## 5. The channel — what is and is not now possible

[[instagram-outreach-plan-2026-07-30]] settled that IG DMs **cannot** be
automated: the API physically cannot initiate a thread. That has not changed and
is not a permissions problem.

What was missing was a repeatable way to get **handles**, since a registry lead
has none. [#141](https://github.com/markcosker2-dev/orova-nova/pull/141) adds
`social_finder` — research only, **7/10** on real contractor sites, with the 3
misses verified as genuinely having no Instagram linked at all.

> [!danger] The dependency that makes or breaks it
> `social_finder` attributes a handle to **the page it is handed** and cannot
> tell whether that page is the right company. Given "CEDAR CREEK CONSTRUCTION
> LLC" and a naively-guessed domain it returned `@cedarcreekconstruction.llc`
> with a perfect name match — **from the Pennsylvania firm**. Callers must pass
> a website verified by `website_resolver`'s phone check, never a guess.

---

## 6. Where the system actually stands

**Ready:** discovery. Registry sourcing from legal records, owner + phone at
~100% fill in two states, an ICP filter measured at real signal, server-side
scoring, compliance gates, and now a secret gate in CI.

**Not ready, and not a code problem:**

1. **No open automated first-touch channel.** Verified against the gate itself —
   a registry lead is `ready=True` but **only** via `callable`; `emailable` is
   `False` on every one because licence data carries no email. Email is closed
   by ToS, the phone lane is shelved, IG DM #1 is manual. The pipeline ends in a
   lead nobody may automatically contact.
2. **The offer is undefined.** Removed the unauthorised one; the real one is the
   owner's call and blocks nothing else until a conversation exists.
3. **Fifteen PRs open, none merged.** That is now the binding constraint by a
   wide margin.
4. **Zero conversations, ever.** Nothing here — including everything I built
   today — has met a real prospect.

**The lead engine is close to ready; the business around it is not.** Nova can
find the right people and has no lawful automated way to say hello.

## Linked

[[session-2026-08-05-registry-by-state-and-or-ccb]] ·
[[0014-licence-registries-as-the-discovery-source]] ·
[[instagram-outreach-plan-2026-07-30]] · [[handoff-2026-08-05]]
