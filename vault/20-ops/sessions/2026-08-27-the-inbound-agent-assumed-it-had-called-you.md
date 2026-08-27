---
name: the-inbound-agent-assumed-it-had-called-you
description: The Retell inbound script greeted every caller as a voicemail callback, which since ADR-0017 is usually a fabrication — and the linter built to catch "ten minutes" could not see the word "ten"
type: session
created: 2026-08-27
status: active
---

# The inbound agent assumed it had called you

Mark sent a Retell dashboard link and asked to make the call smoother.

## The link was the inbound agent, not the outbound one

`agent_850b1ed50ca29bcd7b66ac3a55` is **"Nova - Inbound (callback)"**, on
`llm_2e8ffc461d20535ee17bcd64bdd5` v0, bound to +1 716 670 3920. The outbound
cold-call agent is a different one (`agent_54910fe…` on `llm_56da0e89…` v19).

That is the right agent to be working on. Under [[0017-the-sample-is-the-proof]]
inbound is legal on all 82 leads where outbound is legal on 5, it filters for
intent, and it runs while Mark sleeps.

## The finding: the script fabricated a prior call

All four branches of the old inbound script were written for one caller — a
person returning a voicemail from a cold call. ADR-0017 changed who actually
dials that number: the main path is now someone Mark *invited* to try the
qualifier, who was never cold-called at all.

So the agent's default posture was to thank people for calling back about a
call that never happened. That is a fabrication, and a contractor hears it
instantly. It also sat directly beside a `no_fabrication` compliance rule that
only covered inventing *content* of a previous call, not inventing the call.

Fixed: a `demo_caller_trying_it_out` branch (the main path now), and a
`never_claim_we_called` compliance rule.

## The bigger idea, which was already in the repo

The caller is *standing inside the product*. They are being qualified by the
thing being sold. The old prompt described the painkiller as though pitching
it; the new prompt's governing instruction is to stop selling and just run a
genuinely good qualification call, because the call is the proof. That is
ADR-0017 applied to the one surface where it is literally true.

The `how_do_i_know_it_works` objection now answers itself: *"You're talking
to it."*

## The linter could not see the drift it was built for

`business_context.json` said **"ten minutes"** in five places; canonical is 15.
There is a `lint_meeting_duration` in the knowledge compiler whose entire job
is catching that, and it passed clean every run for four months. Two reasons,
both of which had to be fixed:

1. `_DURATION_RE` matched `\d{1,3}` only. **Spoken copy spells numbers out** —
   a call script writes "ten minutes", never "10 minutes". The linter was
   blind to the only form the drift ever takes.
2. `_MEETING_WORD_RE` required `call|chat|meeting|conversation`. The spoken ask
   is *"would you be open to fifteen minutes with Mark?"* — it names the
   **person**, not the artefact, so the word "call" never appears. Even after
   fixing (1), every real instance still slipped through.

Both fixed, with three tests, one of which fails against the old pattern.
Accepted cost, documented in the source: "Mark" is also a verb we use, so a
false positive is possible — it needs a duration *and* disagreement with
canonical *and* proximity to the name *and* not a latency, and the line takes
a `noqa: duration` marker. Recall is the right side to err on: a missed drift
is a wrong number spoken on every call.

## The generation gap is closed

`business_context.json` was labelled the source of truth for the script while
nothing pushed it anywhere — which is why the drift survived. There is now
`scripts/retell_sync.py` with three verbs: `dump` (back up every agent, the
rollback Retell does not provide), `render` (build the prompt from the file,
offline), `push` (writes, refuses without `--confirm`, dumps first).

## What was NOT done

- **The live prompt was never read.** No `RETELL_API_KEY` in this container and
  no network route to `api.retellai.com`. Every claim about what is *currently*
  deployed comes from this repo's own notes. Run the dump first.
- **The outbound agent** still carries the same drift. `retell_sync.py` renders
  inbound only.
- **The third "Demo (invited)" agent** was not created — the inbound agent's new
  demo branch covers that caller on the number already published, without a
  second prompt to keep in sync. Worth deciding deliberately rather than by
  default.

## Note

`nova.py` reported production BROKEN and the lead list empty. That is this
sandbox, not production: the proxy 403s `orova-nova.onrender.com`, and `.env`
does not exist in a fresh clone. Nothing was learned about production health.

No council provider key is configured in this environment, so the stop-gate
review did not run.
