# Integration — how this reaches production & improves over time

The skill is the **source of sales craft**. Production systems are **projections**
of it. This file is how they stay connected so the skill is never dead docs.

## Who consumes what (be honest about the boundary)

| Consumer | Loads this skill directly? | How it actually gets the knowledge |
|---|---|---|
| **Claude Code** (repo work, drafting, review) | ✅ yes (`.claude/skills/`) | Native skill load |
| **Future Claude-based sales agents** | ✅ yes | Native skill load |
| **Nova** (Python, Render) | ❌ no | Reads `app/core/business_context.json` — must be **projected** there |
| **Retell AI** | ❌ no | Reads its dashboard/API agent prompt — **projected** there |
| **Email composer / reply lanes** | ❌ no | Same as Nova (business_context + composer prompts) |

So a change to a reference here changes Claude's behavior immediately, but changes
**Nova/Retell only after you project it**. Do not assume editing this skill alters
what production sends.

## The projection workflow (skill → production)

1. Improve a reference here (e.g. a better objection line, tighter positioning).
2. Project it to the machine source of truth:
   - **Email/reply behavior** → edit `app/core/business_context.json`
     (`email_rules`, `outreach`, `value_propositions`, `retell_pitch`).
   - **Call behavior** → update the Retell agent prompt (dashboard/API).
   - **Automated QA** → mirror new gates into `app/skills/email_proofreader.py`.
3. Ship via PR; the change deploys with Nova. Keep the skill and business_context
   consistent — if they drift, the playbook/business_context win (they're what
   actually sends), and you fix the skill.

> Positioning note: business_context is currently lead-gen-framed while this skill
> pushes "premium revenue growth." Elevating production copy means editing
> business_context to match `positioning.md` — a deliberate owner-approved change,
> not an automatic one.

## Learning integration (how the Skill compounds)

Nova already runs a champion/challenger loop (ADR-0004, Wilson-scored) over
`outreach_outcomes` in SQLite. Wire the skill into it:

- **Metrics to track (per message variant):** sent → opened → replied → positive-
  reply → **booked** (booked is the north star), plus cold-call connect→booked.
  Tag every send with `strategy`/variant id (the schema already carries `strategy`,
  `send_hour`, `send_day`, `quality_score`).
- **Identify winners:** a variant is "champion" when its Wilson lower-bound on
  booking-rate beats the field at adequate sample. Losers auto-retire.
- **A/B evolution:** register challenger variants of a reference's templates (e.g.
  two hooks for detailers); the loop routes traffic and promotes the winner.
- **Feed improvements back:** when a variant wins durably, promote its pattern into
  the relevant reference here (source of truth) AND into business_context
  (production). That's the compounding loop: production learns → the skill records
  the lesson → every future agent starts from the better baseline.
- **Record meaningful changes in the vault:** append promote/retire events to
  `vault/20-ops/improvement-log.md` (already synced by `vault_pull.py`) and, for a
  real strategy shift, a note in `vault/40-decisions/` or `active-context.md`.

## Verification loop

Before a variant is trusted: it passes `qa-checklist.md` (hard gates) → proofreader
score ≥ threshold → approval gate (human unless autopilot) → outcome logged →
Wilson score updates. No variant is promoted on vibes; only on booked-rate at
sample. Stability is preserved because champions only change when beaten on
evidence.
