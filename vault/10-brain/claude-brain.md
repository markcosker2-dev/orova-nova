---
name: claude-brain
description: How Nova thinks — LLM routing, the models it runs on, and how it learns
type: brain
created: 2026-07-03
status: active
---

# The Brain — LLMs & Learning

How Nova actually thinks, and how it gets smarter over time. Code lives in
`app/core/ai_client.py` (routing) and `app/core/self_improvement.py` (learning).

## Model routing (3 tiers, fail down)

Every call goes through `UnifiedAIClient`, which tries tiers in order and trips a
per-provider circuit breaker on failure:

1. **Tier 1 — Groq** `llama-3.3-70b-versatile` — the primary brain, fast +
   tool-calling. Needs `GROQ_API_KEY`.
2. **Tier 2 — native Gemini** `gemini-2.5-flash` (or `-lite` without tools).
   Needs `GOOGLE_API_KEY`.
3. **Tier 3 — OpenRouter free models** — the fallback chain and the fast/smart/
   genius "flavors". Needs `OPENROUTER_API_KEY`.

### Current free models (post PR #19, 2026-07-03)

| Slot | Model | Notes |
|---|---|---|
| default / fast | `meta-llama/llama-3.3-70b-instruct:free` | tool-calling ✓ |
| smart | `qwen/qwen3-next-80b-a3b-instruct:free` | tool-calling ✓ |
| genius | `qwen/qwen3-coder:free` | tool-calling ✓ |

> Why the upgrade happened: OpenRouter **retired**
> `google/gemini-2.0-flash-lite-preview-02-05:free` and
> `qwen/qwen-2.5-coder-32b-instruct:free`. They were still wired in, so tier-3
> and the fast/genius flavors were 404-ing on every call. All three replacements
> were verified tool-calling-capable via the OpenRouter public API before wiring.

**Free-tier reality:** free models can rate-limit or change. If leads/outreach
quality dips, check the OpenRouter free list is still current and that Groq
(tier 1) is actually answering — a dead `GROQ_API_KEY` silently pushes every call
down to the slower fallbacks. The first paying client funds paid models, which is
the real fix.

## Retell (voice) brain

The cold-call agent "Nova" runs on **gpt-4.1-mini** (bumped up from gpt-5-nano),
post-call analysis on gpt-5-mini. Separate from the text stack above.

## How it learns (this is the "smarter each time" part)

The self-improvement lane (Lane 8) runs a **champion/challenger** loop:

- Every outreach outcome (sent / replied / booked) is recorded per strategy.
- Strategies are ranked by the **Wilson lower bound** — a small-sample-safe score
  so a 1/1 fluke doesn't beat a proven 40/100.
- `select_strategy` is epsilon-greedy (~15% exploration): mostly use the champion,
  sometimes try a challenger.
- Challengers with n≥20 and a Wilson score below half the champion's are retired.

The result: subject lines, send timing, and outreach framing measurably improve
as volume grows — without anyone editing prompts by hand.

## How the vault plugs in

`scripts/vault_pull.py` pulls the current ranked strategies into
[[strategy-snapshot]]. Because Claude reads the brain at session start, **each
session starts with Nova's latest learning already in context** — that's the loop
that makes the whole system compound. See [[system-patterns]] for the full agent
loop and [[active-context]] for what's live now.
