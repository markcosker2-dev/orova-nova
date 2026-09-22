---
name: session-2026-09-23-owner-safety-retell-readiness-and-llm-routing
description: Prevented malformed owner names, added a live-safe inbound demo gate and renderer, and hardened zero-budget LLM routing.
type: session
created: 2026-09-23
status: done
---

# Session: owner safety, Retell readiness and LLM routing (2026-09-23)

## Outcome

OROVA is safer and more testable, but demo traffic remains on hold. No live
Retell, Cal, Make, Instagram, LinkedIn or production setting was changed; no
message was sent. The first-client lane remains manual researched DM → prospect
voluntarily calls the disclosed inbound demo → Mark closes.

## Changes

- Added a single owner-name safety rule across storage, enrichment, hygiene and
  the CLI brief. A positive confidence score can no longer make a malformed
  multi-token value such as `Kalin CFO Daisy General` prospect-facing.
- Added `scripts/retell_inbound_readiness.py`, a GET-only gate that reports
  redacted status and exits 2 when any launch-critical condition fails.
- Added `scripts/render_retell_inbound_prompt.py`. It deterministically renders
  canonical Retell fields, defaults to capture-only booking, and makes no API
  calls or live edits.
- Added the official `openrouter/free` router as the final zero-cost catalog
  fallback, guarded so paid OpenRouter names remain excluded.

## Live read-only findings

The inbound number still points to the reviewed agent and LLM. Both legacy Cal
tools still point to event type `2804866`. AI disclosure and the no-offer
boundary are present. The live prompt still fails recording consent, demo
simulation, post-demo diagnosis and the 15-minute ask. The Cal duration could
not be independently verified because no local Cal key is available. The
agent stores “Everything,” its handbook AI disclosure flag is false, and its
legacy Cal tools now have a time-bound migration. The local outbound
`RETELL_FROM_NUMBER` also differs from the reviewed inbound number; no value was
printed or changed.

The configured OpenRouter credential returned HTTP 401 on one minimal free
router smoke test. The fallback is ready in code but unavailable until a valid
key is supplied.

## Verification so far

- Owner/provenance focused tests: **68 passed**.
- Provider resilience focused tests: **19 passed**.
- Retell readiness and renderer tests: **7 passed**.
- Combined focused regression set: **99 passed**.
- Full repository suite: **1,529 passed**, with 26 existing dependency
  deprecation warnings and no failures.
- Canonical knowledge compiler: clean. Secret scan: clean. Diff check: clean.

## Next action

Mark reviews the Retell launch package. With explicit approval for a live
change, take an exact private backup, migrate/fix the Cal event, create and test
a draft Retell version, publish via the production tag, then run one approved
phone test. Only an exit-0 readiness result unlocks the five manual DMs.

Linked: [[retell-inbound-demo-launch-runbook-2026-09-23]] ·
[[free-llm-routing-2026-09-23]] ·
[[0019-free-llm-redundancy-is-not-self-learning]]
