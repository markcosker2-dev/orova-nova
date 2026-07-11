---
name: hermesclaw-orova-readme
description: Stable overview of the HermesClaw + OROVA project — start here
type: doc
created: 2026-07-11
status: active
---

# HermesClaw + OROVA

> Stable overview. Rarely changes. For the live state, read [[STATUS]].

## What it is

**OROVA** is a 1–2 person, AI-operated marketing agency that runs Meta
(Facebook + Instagram) ads for luxury/premium businesses on the US West Coast.
**Nova** is the autonomous agent that *is* the agency — it hunts leads, finds
owners' direct emails, sends outreach, cold-calls via Retell AI, books
meetings, briefs the CEO daily, and learns from every outcome.
**HermesClaw** is the umbrella system: Nova (Python/FastAPI on Render) + a
desktop cockpit (Electron, OpenClaw-based) + this Obsidian vault as the
shared brain.

## Why it matters

- **The product demos itself**: every prospect experiences Nova's outreach
  before they ever pay — "you're talking to the product right now."
- **~97% realistic margins** at current vendor pricing ($35–150/mo per client
  against $4–5K/mo retainers) — see [[profitability-plan]] §3.
- **Self-improving**: Wilson-bound champion/challenger loops mean outreach
  measurably improves with volume, without hand-editing prompts.
- The single goal right now: **land the first paying client.**

## Who it's for

- **Mark** (owner/CEO) — approves outreach, closes deals on Google Meet.
- **Nova** (the agent) — runs everything else, approval-gated.
- **AI assistants** (Claude Code and future chats) — build, operate, improve.

## The offer (commercial source of truth: [[business-model]])

| | P1 — $4,000/mo | P2 — $5,000/mo |
|---|---|---|
| Meta lead gen + Higgsfield AI creatives | ✅ | ✅ |
| Retell AI qualification + CRM + booking | — | ✅ |

1-month trial → 1/3/6-month terms. Ad spend client-paid, direct to Meta.
**Lead with P1** for first-touch cold outreach (no case study yet).

**ICP** (narrowed 2026-07-10): exotic/luxury auto (dealers, detailing/PPF/
wrap, restoration) · custom home builders / high-end remodeling · luxury
real-estate agents (individual top producers). West Coast: CA/OR/WA/NV/AZ.

## Useful links

- **Production**: https://orova-nova.onrender.com (dashboard: mission-control)
- **Repo**: https://github.com/markcosker2-dev/orova-nova
- **Deep brain**: [[active-context]] · [[orova-playbook]] · [[roadmap]] ·
  [[system-patterns]] · [[claude-brain]] · [[tech-context]]
- **Decisions**: [[decision]] (this folder) + ADRs in `40-decisions/`
- **Owner playbook** (how Mark decides): `playbook/` in this folder (built
  from the 2026-07 interview; any AI acting for Mark reads it first)

## How AI should help

1. **Read [[STATUS]] first** every session, then act on the top next-action.
2. Follow repo `CLAUDE.md`: branch-first git (never commit to main), vault
   notes carry frontmatter, never edit `vault/.obsidian/`, docs never at repo
   root.
3. **Verify live, not just in tests** — production evidence over assumption;
   report Verified / Inferred / Unknown honestly.
4. Respect the gates: cold email/calls/replies are approval-gated; ads and
   spend ALWAYS need Mark; **call published business lines only, never
   personal cells** (TCPA).
5. Hard constraints: Render free tier (512MB, ephemeral disk, no browser, no
   SMTP, 25s enrichment ceiling), `httpx==0.27.2` pinned, $0 budget until
   revenue.
6. Batch merges — every deploy wipes learning data until Drive backup works
   (see [[STATUS]]).
