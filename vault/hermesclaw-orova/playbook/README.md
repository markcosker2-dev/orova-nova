---
name: owner-playbook
description: How Mark decides — rules, judgment calls, red lines. Any AI acting for Mark reads this first.
type: doc
created: 2026-07-11
status: active
---

# Owner Playbook — How Mark Decides

> Built from the 2026-07-11 decision interview (11 questions, complete).
> Each file is a self-contained "skill" any future AI chat loads to act as
> Mark would. For anything not covered here, apply [[judgment-calls]]; if
> still unsure — that IS the answer: escalate to Mark.

## Skill files

- [[client-acceptance]] — dealbreakers + the educate-first pattern
- [[pricing-and-negotiation]] — price is the price; refund stance
- [[outreach-voice]] — cadence spec, promise ceiling, social-proof scripts
- [[red-lines]] — the 10 never-dos (absolute, above all other rules)
- [[judgment-calls]] — the tie-breaker ranking: revenue > certainty >
  reputation > speed, INSIDE the red lines
- [[escalation]] — the always-Mark list, forever

Machine twin: the enforcement-relevant rules are mirrored in
`app/core/business_context.json` (`case_studies`, `outreach.cadence_policy`)
so Nova's runtime obeys them too. Keep both in sync.

## Already codified elsewhere (don't duplicate)

- Approval gates + automation split → `business_context.json` /
  [[orova-playbook]] §5
- TCPA calling policy → [[decision]] #7
- Commercial terms (pricing, refunds) → [[business-model]]
