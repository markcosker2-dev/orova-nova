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
- **WP4 done** — approval gates enforced in code (cold email/calls need approval,
  fail-closed) **and** the reply → qualify → booking middle-mile is wired: replies
  are classified HOT/WARM/COLD, HOT ones are qualified and auto-progressed to a
  booking-link reply (approval-gated via `REPLIES_AUTOPILOT`, durable retry queue),
  and a Cal.com webhook (`/api/cal/webhook`) creates the Google Calendar event on
  booking. All degrade gracefully with no LLM key / no booking link. 124 tests
  pass. See [[session-2026-07-04-wp4-booking-funnel]].
- Vault learning bridge live (`scripts/vault_pull.py`).
- **Owner-name engine (2026-07-04, [[0003-owner-name-first-lead-engine]])** — new
  registry-FIRST resolver (`app/skills/owner_finder.py`). **Live-verified the sources**:
  WA SoS is **anti-bot gated → unusable server-side** (now dormant behind
  `WA_SOS_ENABLED`); OpenCorporates free tier is open-data-only (paid for us); CA
  key-gated. **SerpAPI is the one working free source** (validated live — found "Kim
  Malek" for Salt & Straw; 250/mo, score-gated; fixed an over-capture bug + 20s
  timeout). Upshot: free registries are a dead end — **SerpAPI + the website/AI scrape
  are the real free owner sources, so a live LLM key is the top lever.** SerpAPI key is
  set (local + Render). Also fixed 2 latent bugs (gmail_skill, sheets_sync). **151 tests
  pass.** Audits: [[lead-engine-research]] · [[skill-health-audit]].

## Lead scraping overhaul (2026-07-05) — discovery FIXED, extraction next

Live-tested the real pipeline and found the discovery layer was the root problem:
`find_leads_v3` used the **deprecated** `duckduckgo_search` + Google-Maps HTML scrape,
returning junk (WHOIS text as owner, image filenames as email). Fixes shipped:

- **Discovery → SerpAPI Google Maps engine** (`_source_serpapi_maps` in `lead_gen_v3`).
  Live result: **business + phone (E.164) + website at 100%** on real luxury dealers
  (Lamborghini Beverly Hills, Marshall Goldman, DRIVE LA). Uses the existing SerpAPI
  key; ~15 businesses/search; shares the 250/mo quota (fail-OPEN so a DB hiccup can't
  zero out lead-gen). Legacy scrape/DDG kept only as fallback.
- **Groq**: the key in `.env` was INVALID (401); Mark provided a valid one
  (`gsk_IdJ…`). AI client now returns real output. ⚠️ **Render `GROQ_API_KEY` must be
  updated to this same key.**
- Removed 3 junk enrichment sources (`_state_registry_lookup` → `bizfile@sos.ca.gov`,
  `_whois_lookup` → ToS boilerplate, `_ddg_owner_verification` → deprecated DDG).
- Outreach: fixed a **double-send + approval-gate bypass** (drip now starts at the
  day-2 follow-up, not a day-0 second email). Broadened the hunt niches across the ICP.

**Still open (the hard part): email + owner-name extraction.** The AI path
(`enrich_lead_lite`) times out at the 25s Render ceiling and returns empty; needs a
fast, focused rewrite (homepage + /about + /contact only, short per-page timeout,
one Groq extraction call). This is the next task. Local-test note: scripts must
`load_dotenv(<repo>/.env, override=True)` — the shell has an empty `SERPAPI_KEY`.

## 🚨 The #1 blocker: ~~no working LLM key~~ RESOLVED 2026-07-05 (valid Groq key)

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
