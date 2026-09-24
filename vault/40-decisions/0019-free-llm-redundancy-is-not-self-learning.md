---
name: 0019-free-llm-redundancy-is-not-self-learning
description: Keep zero-cost inference redundant and make learning an explicit local outcome loop rather than a model-provider claim.
type: decision
created: 2026-09-23
status: active
tags: [decision, hermesclaw, llm, learning, zero-budget]
---

# ADR-0019 — Free LLM redundancy is not self-learning

## Status

Accepted for the pre-revenue zero-budget phase, 2026-09-23.

## Context

HermesClaw already has three provider paths. The business needs reliability,
but adding every advertised free API creates more credentials, adapters and
silent failure modes. Provider catalogs and quotas change. A hosted model also
does not train itself on OROVA's past calls simply because it is used again.

## Decision

- Route Groq → Gemini → named OpenRouter `:free` models → the official
  `openrouter/free` router.
- Enforce a structural zero-cost check; do not accept merely cheap or unknown
  OpenRouter model names in zero-budget mode.
- Do not add Cerebras, Hugging Face, GitHub Models, Cloudflare or Mistral now.
  Cloudflare is the best fourth-provider candidate only after measured quota
  failures justify the integration.
- Treat learning as OROVA-owned state: record traces and real outcomes, retrieve
  useful memory, and promote strategies only from evidence. Provider fallback
  improves availability; it does not itself improve policy quality.
- Never send more prospect data to a fallback than the task requires.

## Consequences

- Catalog turnover is less likely to disable the entire OpenRouter tier.
- The official free router may select different underlying models, so it is a
  last fallback rather than the primary source of stable behavior.
- The current OpenRouter key is invalid (HTTP 401 on 2026-09-23); the route is
  unavailable until the owner replaces it.
- Sales learning remains starved until real outreach outcomes exist. Synthetic
  “success” must not be recorded as a reply, call or meeting.

Linked: [[free-llm-routing-2026-09-23]] ·
[[0004-obsidian-brain-and-skill-improvement]] · [[active-context]]
