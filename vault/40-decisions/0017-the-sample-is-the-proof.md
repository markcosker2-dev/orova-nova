---
name: 0017-the-sample-is-the-proof
description: Outreach leads with a live AI demo call instead of testimonials or results — and asking permission for it is also the legal cure. Owner decision 2026-08-22.
type: decision
created: 2026-08-22
status: active
tags: [decision, outreach, strategy, consent, tcpa]
---

# ADR-0017 — The sample is the proof

## Status

Accepted — owner decision, 2026-08-22.

## Context

OROVA has **no testimonials, no case studies and no prior results**, and
fabricating them is forbidden (`never fabricate`, business_context
`case_studies._note`). For cold outreach that is normally fatal: every
credibility device available to a new agency is one OROVA cannot use.

Zero prospect conversations have ever happened. The proof problem and the
conversation problem are the same problem.

## Decision

**Lead with a sample, not a claim.** The pitch is:

> *"We've already built the AI lead qualifier. Can I have it call you?"*

The prospect experiences the product by being qualified by it. The call opens
as a demonstration and transitions into booking a meeting with Mark. No free
trial, no results claim, no testimonial — the artefact does the persuading.

The statement is **true**: the qualifier exists and is deployed (Retell agent
`Nova` v19). This is honesty used as a sales asset, not a workaround.

## Why this also solves the legal problem

Asking *"can I have it call you?"* on a live human call, and getting a yes, is
**prior express consent** — the cure §227(b) requires for an artificial-voice
call to a wireless number. It removes the exposure that made the phone lane
untouchable, which was that a licence-registry number cannot be shown to be a
landline.

More striking: **CA PUC §2874 requires a live operator to obtain consent
before an automated system may play.** The method arrived at that structure
from sales instinct, not statute-reading.

**What it does NOT settle:** RCW 80.36.400 (WA) appears to bar automated
commercial solicitation with no consent cure. 93% of the lead inventory is WA
(77 of 82 on 2026-08-22).

So the lawyer question is now much narrower and far more valuable:

> **Does live-operator-obtained prior consent satisfy RCW 80.36.400 and
> CA PUC §2874?**

That answer decides whether 93% of the pipeline is machine-callable. It is the
highest-value hour available to buy.

## Consequences

- Consent must be **recorded and durable**. #194 adds `nova.py consent`, which
  writes `call_consent.py`'s ledger — a gate that had existed for weeks with
  **no path that could ever grant it**. The record is mirrored to a `Consent`
  sheet tab because the ledger lives on an ephemeral disk.
- **Targeting follows jurisdiction, not the other way round.**
  `AI_CALL_ALLOWED_STATES` starts EMPTY. No state is permitted until someone
  qualified says so. Never compile a guessed list of permitted states into
  code: a wrong entry is $500–1,500 per call.
- **Mark calling by hand is unaffected and always was.** He is not an ADAD.
  All 77 WA leads are workable today.
- Consent arrives through `ig_dm_reply`, `email_reply`, `manual` and
  `inbound_call` — so the same gate serves Instagram DMs and email replies
  without change.
- The demo must still never state a price (`commercial_terms` UNRESOLVED).

## Linked

[[0013-painkiller-positioning-and-real-competition|ADR-0013]] ·
[[0016-the-repo-stays-public|ADR-0016]] · [[active-context]]
