# Message QA gate

Run this before any message sends. It mirrors the automated check in
`app/skills/email_proofreader.py` — this is the human/Claude-readable version of
the same bar. A message ships only if it passes **every** hard gate.

## Hard gates (any fail = do not send)

- [ ] **On-positioning:** sells qualified conversations / revenue growth, not
      "leads" or generic agency-speak. (see `positioning.md`)
- [ ] **Differentiator present:** the speed-to-lead / product-demos-itself promise
      appears, not buried.
- [ ] **Past is closed:** no client names, numbers, verticals, tenure, or "our
      clients see…"; no mention of a prior agency.
- [ ] **Promise ceiling:** no guaranteed number on a deadline; forward promises are
      reasonable/benchmark-flavored only.
- [ ] **Length:** email ≤75 words; call opener ≤2 sentences; voicemail ≤15s.
- [ ] **No spam triggers:** free, guaranteed, act now, make money, limited time, $$$.
- [ ] **One ask, one link max;** clear OROVA identity + correct signature.
- [ ] **Personalized on THEM:** a real, verifiable specific — never an invented one.
- [ ] **Compliance:** business line only; AI disclosed if asked; nothing that needs
      human sign-off (spend/sign/publish) is promised autonomously.

## Soft score (0–100, tune don't block)

Weight quality signals: hook specificity (25), differentiator clarity (25),
brevity/senior tone (20), single clean ask (15), subject strength (15). Below ~70
→ rewrite before send. This maps to the proofreader's `score`; the loop retries up
to 3× then holds for approval.

## How to use

- Reviewing a draft: run the gates, output PASS/FAIL per line + the rewrite.
- Building automation: this list is the spec `email_proofreader` should enforce;
  when you add a gate here, add it there too (see `integration.md`).
