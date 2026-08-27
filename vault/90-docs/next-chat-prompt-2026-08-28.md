# Prompt for the next chat

Paste everything below the line into a fresh session.

---

Read `vault/90-docs/handoff-2026-08-28.md` FIRST, before any other tool call.
Then run `python scripts/nova.py` and trust it over any document.

I'm Mark, solo founder, OROVA — a one-person agency selling Meta ads and an AI
lead-qualification caller. I'm in the Philippines (UTC+8) targeting US West
Coast contractors. Nova is my autonomous AI SDR. North-star metric: booked
meetings. It still reads **zero**.

STATE (verify, don't trust): production https://orova-nova.onrender.com,
`DASHBOARD_API_KEY` is in `.env` (rotated 2026-08-21). ~82 leads, mostly WA
sole operators with verified insurance. The repo is PUBLIC on purpose — it
feeds my Make.com; do NOT change visibility (ADR-0016).

FIRST: check whether PR #199 merged and deployed cleanly
(`nova.py deploy`, `nova.py status`). It fixes four defects the last session
found reviewing its own work — the most important being that the AI-call
jurisdiction gate had been written into `scripts/nova.py` instead of
`ai_call_allowed()`, so it protected the CLI and none of the other four paths.

THEN, in this order:

1. **The Retell sync — drafted but NOT pushed.** Three agents: keep Nova v19
   (cold, gated) as-is, create "Nova — Demo (invited)" from the draft, and add
   a demo-caller branch to the inbound agent. Across all: "Mark Cosker" →
   "Mark", "ten minutes" → "fifteen", ads-only → three offerings. The demo
   agent draft still needs `post_call_analysis_data` and `boosted_keywords`.
   ⚠️ Retell updates an LLM version IN PLACE with no rollback — dump the
   current text of every agent to a file BEFORE touching anything, and show me
   the new text before sending it.

2. **Ask me for these four**, then act on whatever I give you:
   - `BUSINESS_POSTAL_ADDRESS` (a PO box counts) — sending is hard-blocked
     without it at `agentmail_skill.py:309`, and the inbound prompt promises a
     confirmation email it currently cannot send
   - whether the cal.com event is now 15 minutes, and whether availability is
     fixed (it showed ONE slot per day, at midnight my time)
   - whether I've got a Seattle number (716 is Buffalo)
   - `AI_CALL_ALLOWED_STATES` — empty means no AI call is permitted anywhere

3. **Then ask me what I want built.**

DO NOT:
- change repo visibility, spend money, or sign up for anything
- set or imply a price — Nova quotes nothing; I quote. P1 $4k, P3 $3k, P2 $5k
- compile a guessed list of AI-call-permitted states into code. A wrong entry
  is $500–1,500 per call. It is configuration, decided by me or a lawyer
- loosen the consent gate, the DNC gate, the approval gate, or
  `BUSINESS_POSTAL_ADDRESS`. `CALLS_AUTOPILOT=0` stays 0
- add lead sources — 8,768 WA contractors are unworked
- commit prospect PII or a burned credential, even as an example
- re-litigate: cold email providers, Apollo, Six Degree, NPPES, Meta Ad
  Library, Yelp paid, OpenCorporates, CALICO, med spas (ADR-0015)

SETTLED — don't re-derive:
- **The sample is the proof** (ADR-0017). No testimonials exist and none may be
  invented, so outreach leads with "we've built the AI qualifier — can I have
  it call you?" and the prospect is qualified BY it. Asking permission is also
  the §227(b) consent cure. Record it: `nova.py consent <id> dm|call|email`.
- **Inbound beats outbound** for the demo: legal on all 82 leads today where
  outbound is legal on 5, filters for intent, and works while I sleep.
- **Pain B → Package 3**, not P2. A man drowning in bad leads is not short of
  leads. It is also the diagnosis the demo produces most often.
- **Fail-open turns a dead dependency into an empty field, not an error.** A
  field empty for EVERY row is a dead dependency until proven otherwise.
- **Put gates where paths converge**, never at each call site — `planner`
  exposes the dialler to the LLM as a tool and cannot be gated by convention.
- Solo is a DISCOUNT, not a disqualification: 42% of contractors above the $1M
  insurance minimum are one-man operations.

ONE THING I OWE YOU AN ANSWER ON — push me if I dodge it:
The WA ADAD / §227(b) lawyer hour. It is now a narrow question — *does
live-operator-obtained consent satisfy RCW 80.36.400 and CA PUC §2874?* — and
it decides whether 93% of my pipeline is machine-callable. Everything
downstream is built and idle.

THEN: five lines on where things stand and the highest-leverage next action.

Last thing. Nineteen PRs shipped last session and the number that matters
didn't move: 0 calls, 0 meetings, 0 prospect conversations, ever. The top of my
list is a 25-year sole operator carrying $2M of cover, ranked there on evidence
Nova pulled itself — `nova.py brief 4` has his name and number. 6–9am my time
is his afternoon. If your best suggestion is another PR, say so, but say why it
beats me making that call.
