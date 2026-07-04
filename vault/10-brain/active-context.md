---
name: active-context
description: What's happening on OROVA right now — read this first every session
type: brain
created: 2026-07-03
status: active
---

# Active Context

> Session-start file. Read this first (CLAUDE.md rule). Keep it current when the
> direction changes materially.

## Where things stand (2026-07-03)

Nova (the OROVA agent) is **live on Render free tier** at
`https://orova-nova.onrender.com` — health is green, all 9 worker lanes and the
mission-control dashboard are deployed and working. The build is past the
"make it run" phase; the gate to everything now is **the first paying client**,
which funds better tooling (paid Anthropic, paid enrichment, Render paid tier).

## Shipped recently

- **LLM model upgrade** (PR #19) — the old OpenRouter fallback models
  (`gemini-2.0-flash-lite-preview`, `qwen-2.5-coder-32b`) had been retired by the
  provider and were 404-ing. Now on live free models: `llama-3.3-70b` (default),
  `qwen3-next-80b` (smart), `qwen3-coder` (genius); Groq `llama-3.3-70b-versatile`
  stays tier-1; Gemini bumped to 2.5-flash. See [[claude-brain]].
- **Dashboard** — structural redesign (Tabler-style), readable fonts, all buttons
  wired; the "failed to queue" bug (session tokens issued but never validated) is
  fixed.
- **Auth chain** — `require_dashboard_api_key` now accepts session tokens.
- **Retell cold-call agent** — Nova agent live, LLM bumped to gpt-4.1-mini,
  webhook pointing at production, caller number +1 716 670 3920.
- **Vault** — this knowledge layer (ADR-0001); brain refreshed to match reality
  and wired to pull production learning each session (see [[strategy-snapshot]]).

## Nova buildout (PR #21, in progress — see [[0002-lead-engine-and-subagents]])

- **WP1 done** — fixed the CEO's broken auto-hunt (`run_planner` ghost) + added a
  Render-safe AI extraction path to the scraper.
- **WP2 done** — lead engine: scan owner pages (/about,/team) first, AI extraction
  pass, and fixed `_prioritize_email` (was preferring `info@` over personal).
- **WP3 done** — real sub-agents: `dispatch_task` now runs a scoped planner with
  the agent's persona + role tools (was a hardcoded string).
- **WP4 pending** — enforce the approval gates in code (email/calls need approval)
  + wire the reply → qualify → booking middle-mile.
- Vault learning bridge live (`scripts/vault_pull.py`).

## 🚨 The #1 blocker: no working LLM key

A live test showed **all three providers are dead**: Groq 401, OpenRouter 401
("User not found"), Google empty. Nova has **no working AI brain** — every AI call
falls back to non-AI paths. The buildout code degrades gracefully, but nothing
AI-driven works until Mark sets **one** live key (OpenRouter / Groq / Gemini) on
Render. This gates real-world results more than any code.

## Other owner actions

1. `DASHBOARD_API_KEY` in local `.env` (vault sync). 2. `TARGET_NICHE` /
`TARGET_LOCATION` on Render (done). 3. Deliverability check on first send.
4. Confirm vault restore in Render boot log.

## Not needed (settled)

- **Apollo** — production hunting uses Google Maps + DuckDuckGo + free web/WHOIS/
  registry enrichment. The Apollo scrapers are optional local-only browser tools
  that can't run on Render. Not on the critical path.

## Linked

- [[project-brief]] · [[business-model]] · [[system-patterns]] · [[claude-brain]]
- [[progress]] — running done/remaining list
