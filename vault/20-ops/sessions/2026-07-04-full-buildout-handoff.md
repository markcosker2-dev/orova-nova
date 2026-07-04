---
name: session-2026-07-04-full-buildout-handoff
description: Complete handoff of everything built and discussed — read to resume in a new chat
type: session
created: 2026-07-04
status: active
---

# Handoff — Full OROVA Buildout Session

Read this + [[active-context]] + [[orova-playbook]] + [[roadmap]] to resume in a
fresh chat with no context lost. This covers everything we did and discussed.

## TL;DR — where we are

Nova (the OROVA agent) is live on Render free tier. This session hardened the
brain, fixed the lead engine, built real sub-agents, added approval gates,
corrected pricing, and populated the Obsidian vault. **All work is MERGED to
`main` via [PR #21](https://github.com/markcosker2-dev/orova-nova/pull/21)** on
2026-07-04 (#19 and #20 auto-resolved into it). Render auto-deploys from main.
Tests: **112 passing on main.**

**The #1 blocker:** no working LLM key (Groq 401, OpenRouter 401, Google empty) —
**must be a FREE key** (Groq / Google AI Studio / OpenRouter free tier; no paid
models). Nothing AI-driven works until one live free key is set on Render.
Nothing AI-driven works until Mark sets one live key on Render.

## What OROVA is (business)

Marketing agency running **Meta ads for luxury/premium US West Coast businesses.**
- **Package 1 — $4,000/mo:** Meta lead-gen + Higgsfield AI creatives; client
  handles their own leads.
- **Package 2 — $5,000/mo:** P1 + OROVA qualifies leads (Retell AI cold-call) so
  the client only talks to buyers + keeps their CRM current + books appointments.
- **Terms:** 1-month trial for new clients, then 1/3/6 months. Corrected pricing:
  1mo $4K/$5K · 3mo $10K/$13K · 6mo **$18K/$24K** (longer = cheaper per month).
- **Payment:** invoice via Wise/ACH. **Ad spend is client-paid, direct to Meta.**
- **Refunds:** partial only — the system build/setup is non-refundable.
- **Margin target:** 75–80% after costs (Twilio, Retell PAYG, Make.com, Higgsfield,
  hosting/LLM) which run ~$60–500/mo per client.
- **Funnel:** cold email → (no reply) Retell cold call → book with Mark → Google
  Meet → agreement + invoice → onboarding (ad manager + CRM access).
- **Differentiator:** the product demos itself — the prospect experiences Nova's
  outreach + qualification before they pay.
Full detail: [[orova-playbook]] · machine twin the agents obey:
`app/core/business_context.json`.

## The system (architecture)

- **`app/` — Nova**: Python/FastAPI, Render free tier (orova-nova.onrender.com).
  9 worker lanes (hunt, outreach, replies, cold calls, backup, CEO brief, health,
  self-improvement, drips). SQLite state, backed up to Google Drive.
- **`electron/` + `src/` — HermesClaw GUI** (local cockpit, OpenClaw-based).
- **`mission-control/` — dashboard** served by FastAPI.
- **`vault/` — Obsidian knowledge base** (this). Synced from production by
  `scripts/vault_pull.py`. The brain: [[project-brief]] [[business-model]]
  [[claude-brain]] [[system-patterns]] [[orova-playbook]].
- **LLM routing** (`app/core/ai_client.py`): Groq `llama-3.3-70b-versatile` →
  native Gemini 2.5-flash → OpenRouter free (llama-3.3-70b / qwen3-next-80b /
  qwen3-coder). Retell voice on gpt-4.1-mini.

## What we built this session (by PR)

- **PR #19 — model IDs:** OpenRouter had retired the old free models (404s); moved
  to live free models + Gemini 2.5.
- **PR #20 — vault brain + learning bridge:** refreshed all brain notes (they
  contradicted the real business model), added `claude-brain`, wired
  `vault_pull.py` to sync production learning each session (with a cold-start
  retry so it survives Render sleep), gitignored the auto-synced leads.
- **PR #21 — Nova buildout (consolidates #19+#20):**
  - **WP1** — fixed CEO auto-hunt (`run_planner` ghost import); added Render-safe
    `UnifiedAIClient` extraction to the scraper.
  - **WP2** — lead engine: scan `/about`,`/team` FIRST (they were cut off, so
    owners were never scraped); AI extraction pass; fixed `_prioritize_email`
    (it preferred `info@` over personal addresses).
  - **WP3** — real sub-agents: `dispatch_task` runs a scoped planner with the
    agent's persona + role tools (was a hardcoded string).
  - **WP4 (part 1)** — approval gates: cold email + calls require Mark's approval
    (`app/core/approval_gate.py`, fail-closed); flip `OUTREACH_AUTOPILOT`/
    `CALLS_AUTOPILOT` to enable autonomy later.
  - **WP5** — ADR-0002 + docs.
- **Also:** corrected 6-month pricing; captured refund policy + costs + margin.
- **Obsidian:** discovered Obsidian was opening the wrong (empty) vault; registered
  and opened the OROVA vault; connected the graph (docs index + backlinks).

## Key findings / decisions

- **All 3 LLM providers dead** (Groq/OpenRouter 401, Google empty) — THE blocker.
- **Render blocks SMTP** 25/465/587 → no live email verification ever; we verify
  domain (MX) only and flag guessed emails.
- **Apollo can't run on Render** (no browser) — dropped from critical path; the
  free Google-Maps + web-scrape pipeline is the real hunter.
- **Sub-agents weren't real** — persona files only; now a lightweight scoped-planner
  model (ADR-0002), not a heavy multi-process framework (fits 512 MB).
- **Retell** is provisioned: agent "Nova", number +1 716 670 3920, webhook → prod.

## Open blockers (owner actions) — see [[roadmap]]

~~merge PR #21~~ ✅ done 2026-07-04. Remaining: **set one FREE LLM key on Render**
(Groq is easiest: console.groq.com → API Keys → set `GROQ_API_KEY`) · sending
domain + SPF/DKIM · Meta app creds · Higgsfield + Stripe/Wise + one-page site ·
`DASHBOARD_API_KEY` in `.env`.

## How to resume in a new chat

1. Session start runs `python scripts/vault_pull.py` then reads [[active-context]]
   + [[strategy-snapshot]] (CLAUDE.md rule).
2. Next code task: **WP4 remainder** — reply → qualify → calendar booking. The
   plan file is `.claude/plans/majestic-noodling-feigenbaum.md` (WP4 marked START HERE).
3. Verify the lead engine live once a key exists.

## Using Fable 5 without burning tokens

- Check remaining: `/usage-credits`. (We hit the Fable limit this session.)
- Use Fable for quick drafts/edits/summaries; switch to Opus/Sonnet (`/model`) for
  architecture, debugging, multi-file work.
- Don't spawn Fable sub-agents for big jobs — they re-read context cold and drain
  the limit fast. Keep context small (`/compact`, don't paste large files).
