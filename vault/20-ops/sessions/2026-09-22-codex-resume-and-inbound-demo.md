---
name: session-2026-09-22-codex-resume-and-inbound-demo
description: Recovered OROVA NOVA, vetted Codex skills, defined the inbound demo-call lane and prepared its local Retell source.
type: session
created: 2026-09-22
status: done
---

# Session: Codex resume and inbound demo (2026-09-22)

## Outcome

Recovered the exact pinned Codex task and current worktree, re-read the OROVA
vault and owner playbook, verified the repair branch, and converted the owner's
proposed outreach method into the permission-first **inbound demo-call CTA** in
ADR-0018. The local Retell source and regression tests are ready for review.
No deployment, Retell edit, social message or Instagram post occurred.
The reviewed changes were committed locally on `codex/zero-budget-repair` as
`feat: prepare consent-first inbound demo funnel`; they were not pushed or
merged.

## What changed

- `app/core/business_context.json` now handles a prospect who voluntarily calls
  after a personal DM invitation. The opening discloses AI and asks recording
  permission; the demo is labelled as a simulation; the agent diagnoses lead
  volume versus follow-up waste and asks for a 15-minute Mark conversation
  without quoting an offer.
- `tests/test_retell_inbound_demo.py` pins disclosure, recording permission,
  simulation boundaries, diagnosis, handoff and the live-unverified warning.
- ADR-0017 is marked amended; ADR-0018 controls the current call-initiation
  mechanism. Active Context and the zero-budget runbook point to it.
- Installed the reviewed `token-efficiency` and `codex-token-usage` Codex skills.
  Created and validated the local `orova-nova-operator` skill so future OROVA
  work always begins with the current checkout/vault and ends with an Obsidian
  update.
- Reviewed but did not install `brooks-lint`: its six review modes overlap the
  existing engineering review/testing skills. Reviewed but did not install the
  `codebase-migrate` workflow: it adds Composio/GitHub/Linear orchestration that
  is disproportionate to this repository's current first-client bottleneck.

## Verification

- Pre-change full suite: **1,510 passed**.
- Post-change targeted suite: **26 passed**; final full suite: **1,515 passed**.
- Knowledge compiler: clean.
- Secret scan: clean before these content-only changes.
- Live service read-only check: HTTP 200, but recent logs still show Google
  OAuth `invalid_grant` / backup failure. A complete snapshot is not verified.
- Current code remains on `codex/zero-budget-repair`; nothing in this session
  proves merge, deployment, live Retell parity, outreach, replies or meetings.

## Free-model research decision

Keep the existing provider order instead of rewriting a working abstraction:
Groq GPT-OSS 120B primary, Gemini 2.5 Flash/Flash-Lite secondary and OpenRouter
free models only as the limited tertiary. Groq's documented free limits are
usable for the present workload. Gemini's free tier has a data-use tradeoff, so
private/prospect data should not be sent through it. OpenRouter's local key is
invalid and its no-credit free quota is too small to be a production promise.
Cloudflare Workers AI is the best future fourth provider if a separate account
and adapter become justified by real quota failures.

Sources:
[Groq rate limits](https://console.groq.com/docs/rate-limits),
[Groq GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b),
[Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing),
[Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits),
[OpenRouter support](https://openrouter.ai/support),
[OpenRouter free models](https://openrouter.ai/collections/free-models/),
[Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/).

## Codex skill review evidence

- [`undefdev/token-efficiency`](https://github.com/undefdev/token-efficiency):
  small MIT instruction skill; installed after local validation.
- [`huajiexiewenfeng/codex-token-usage-skill`](https://github.com/huajiexiewenfeng/codex-token-usage-skill):
  MIT local JSONL usage parser/report; tests passed; installed.
- [`hyhmrright/brooks-lint`](https://github.com/hyhmrright/brooks-lint):
  inspected, not installed because of overlap.
- [`composio-community/awesome-codex-skills`](https://github.com/composio-community/awesome-codex-skills):
  inspected only; `codebase-migrate` was not installed.

## Next safe action

Back up and compare the live Retell inbound prompt, then update and test it in
Retell with the owner present. Only after that verification should Mark approve
and manually send five individually researched DMs from the existing Instagram
or LinkedIn account. Record each send, reply, inbound call and meeting as
separate evidence. Do not create a second outreach queue.

## Blockers

- Google Drive OAuth returns `invalid_grant`; no verified full snapshot, so no
  deployment or restart.
- Live Retell inbound prompt has not been backed up or checked against the new
  source.
- OROVA's final commercial offer remains owner-controlled and unresolved.
- Existing Make/Instagram queue state has not been re-verified in the UI this
  session. Chrome reached Make's sign-in page but had no authenticated session;
  no credentials were entered and no scenario was changed. Known data remains
  61 rows marked `Not yet sent`, with no outcomes.

## First-five review packet

Prepared a user-facing review packet for leads 216, 215, 214, 229 and 228. The
official business sites verified the recipients and public facts, and each site
exposed a matching Instagram profile. The packet leaves the phone number as a
hard placeholder until live Retell verification. It also flags lead 215's
malformed stored owner value rather than letting it reach a prospect.

## Live Retell read-only audit

The inbound number is still bound to `Nova — Inbound` agent version 0. A
redacted snapshot of the `prod` tag and referenced Retell LLM version 0 was
saved in the untracked workspace; no Retell state changed. The live opening
does disclose that Nova is AI, but the remaining prompt still:

- frames the call only as a returned call;
- contains no invited-demo or simulation path;
- asks for ten minutes rather than the canonical 15;
- describes OROVA as Meta-ads-only;
- contains no recording-permission instruction; and
- says calendar availability/booking tools do not exist even though both native
  Cal.com tools are attached.

The Cal.com credential successfully read event type `OROVA Calls`, confirming
the integration key and event exist. The event is **30 minutes**, while the
canonical meeting is **15 minutes**. Local source now records that mismatch and
keeps direct booking disabled until the event duration is corrected and both
tools pass an end-to-end test. A preferred time must never be recorded as a
booked meeting.

## Instagram content audit and replacement

Reviewed the ready-made founder and call-walkthrough carousels visually. They
are not safe to publish: they imply customer/agency conversations OROVA has not
had, describe a scripted example as a real call, promise sub-minute follow-up,
and promise direct calendar booking while the live prompt forbids its attached
tools and the event duration is wrong.

Created `social/carousel_12_demo_is_proof/`, a five-slide 1080×1350 carousel
with a matching caption. It makes no customer-result claim and uses a DM
`DEMO` CTA so the public phone number stays withheld until Retell is verified.
The visuals use the established monochrome/green OROVA system. The post is a
reviewed draft only; it was not uploaded, queued or published.

A Reel was not silently created. The brand still needs an owner choice between
a real talking-head format and a non-speaking product-motion format; either can
reuse the claim-safe carousel once selected.
