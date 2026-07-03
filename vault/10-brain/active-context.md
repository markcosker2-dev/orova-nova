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

## In progress

- **Vault ↔ HermesClaw learning bridge** — `scripts/vault_pull.py` pulls leads,
  CEO briefs, and learned strategies from production into this vault so Claude
  reads Nova's latest learning at the start of every session.

## Blocking the first client (owner actions — only Mark can do these)

1. **`DASHBOARD_API_KEY` in local `.env`** — needed for vault sync to run. Paste
   the same value that's set on Render.
2. **Confirm `GROQ_API_KEY` on Render is fresh** — the local copy returns 401.
   If Render has the dead key, tier-1 brain silently fails every call.
3. `TARGET_NICHE` + `TARGET_LOCATION` set on Render (done).
4. Deliverability check (mail-tester) once the first real outreach sends.
5. Confirm vault restore in Render boot log (`♻️ Restored database snapshot`).

## Not needed (settled)

- **Apollo** — production hunting uses Google Maps + DuckDuckGo + free web/WHOIS/
  registry enrichment. The Apollo scrapers are optional local-only browser tools
  that can't run on Render. Not on the critical path.

## Linked

- [[project-brief]] · [[business-model]] · [[system-patterns]] · [[claude-brain]]
- [[progress]] — running done/remaining list
