---
name: free-llm-routing-2026-09-23
description: Current zero-budget inference options for HermesClaw, their real limits, and the selected provider order.
type: doc
created: 2026-09-23
status: active
tags: [hermesclaw, llm, zero-budget, reliability]
---

# Free LLM routing for HermesClaw — 2026-09-23

## Decision summary

Keep the existing abstraction and make it more resilient instead of adding
another provider adapter before there is usage evidence:

1. **Groq `openai/gpt-oss-120b`** — primary. Strongest currently configured
   zero-cost model for reasoning, tool calling and structured output.
2. **Gemini Flash / Flash-Lite** — secondary. Retain the native tool-capable
   path and the lighter text path; quotas vary by project and model.
3. **Named OpenRouter `:free` models** — tertiary while their slugs exist.
4. **OpenRouter `openrouter/free`** — final catalog-resilient fallback. It
   selects a current free model compatible with requested capabilities.

The structural spend gate accepts only names ending in `:free` plus the exact
`openrouter/free` router. `openrouter/auto` and paid model names remain blocked
unless the owner deliberately enables paid routing.

> [!warning] Operational state
> A live, minimal `openrouter/free` request on 2026-09-23 returned HTTP 401 with
> the configured OpenRouter credential. The new fallback is code-ready but not
> operational until Mark replaces the key. No key was printed or changed.

## Current provider evidence

| Provider | Free reality | Tool/JSON fit | OROVA decision |
|---|---|---|---|
| Groq | Published developer limits; quotas are finite and may change | Strong; GPT-OSS 120B supports tool use and JSON modes | Keep primary |
| Gemini API | Free-tier quotas depend on model/project and are visible in AI Studio | Strong native tools; existing adapter works | Keep secondary; do not send unnecessary prospect PII |
| OpenRouter | Free plan is limited; `openrouter/free` costs $0 but selects among changing models | Router filters for required capabilities, but model behavior is not stable | Keep final fallback after credential repair |
| Cloudflare Workers AI | 10,000 neurons/day included; some demanding models require paid Workers | Viable OpenAI-compatible future adapter | Defer until measured provider failures justify another account/integration |
| Cerebras | Current offer is a $5 trial, not a dependable permanent free production tier | Excellent speed and OpenAI compatibility | Do not add as a zero-budget dependency |
| Hugging Face Inference Providers | Free users receive only $0.10 monthly credit | Broad catalog, too little durable capacity | Exclude from production routing |
| GitHub Models | Catalog/playground/inference API are no longer available to customers | Not applicable | Exclude |
| Mistral Studio | Documentation says a free experimental mode exists, but account/API-key billing requirements are not consistently described | Function calling supported | Test only after owner creates a key; do not promise as a fallback |

## What “learning from mistakes” actually means

A free hosted model does not learn OROVA's business by changing its weights
after each run. HermesClaw improves through its own persisted control layer:

- execution traces and outcomes record what was attempted and what happened;
- learned strategies/preferences provide memory to later runs;
- challenger/champion selection can promote a variant only after real outcome
  evidence; and
- failures such as invalid credentials, catalog turnover and empty responses
  must become observable provider-health events rather than silent fallbacks.

There are still **zero prospect conversations**, so there is no honest sales
outcome dataset from which to learn yet. The next useful data is five reviewed
DM sends and their separate reply, demo-call and meeting events—not synthetic
model self-evaluation.

## Sources checked

- [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [Groq GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b)
- [Groq tool use](https://console.groq.com/docs/tool-use/overview)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [OpenRouter pricing](https://openrouter.ai/pricing)
- [OpenRouter free router](https://openrouter.ai/openrouter/free/)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Cloudflare paid-model change](https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/)
- [Cerebras Inference](https://www.cerebras.ai/inference)
- [Hugging Face Inference Providers pricing](https://huggingface.co/docs/inference-providers/en/pricing)
- [GitHub Models](https://docs.github.com/en/github-models)
- [Mistral first API request](https://docs.mistral.ai/getting-started/quickstarts/developer/first-api-request)
- [Mistral organisation/key setup](https://docs.mistral.ai/getting-started/quickstarts/admin/create-organization)

## Recheck trigger

Re-run provider health when a configured model returns 404/401/429, when the
free-tier terms change, or monthly while HermesClaw is active. Never infer a
permanent SLA from a provider's free tier.

Linked: [[0019-free-llm-redundancy-is-not-self-learning]] · [[active-context]]
