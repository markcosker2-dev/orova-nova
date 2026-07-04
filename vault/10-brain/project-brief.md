---
name: project-brief
description: What OROVA / HermesClaw is and why it exists
type: brain
created: 2026-07-03
status: active
---

# Project Brief

## The goal

Build a **1–2 person, AI-operated marketing agency** (OROVA) that runs Meta ads
for luxury West Coast businesses. Get the first paying client so revenue funds
better tooling; long-term ambition is a very small team running a very large
business. See [[business-model]] for the commercial detail.

## The two codebases

This repo is a hybrid of two things (see repo `CLAUDE.md`):

- **`app/` — "Nova"** — the autonomous agent that *is* the agency. Python/FastAPI,
  deployed on Render free tier at `orova-nova.onrender.com`. 9 scheduled worker
  lanes do the hunting, outreach, calling, briefing, backups, health checks, and
  self-improvement. This is where ~all the live value is. Also serves the
  `mission-control/` dashboard.
- **`electron/` + `src/` — the HermesClaw desktop GUI** (OpenClaw-based). The
  local cockpit. Canonical GUI code lives in `electron/`; the `HermesClaw/` folder
  holds reference mirrors only. Doesn't typecheck as one unit (esbuild build);
  `pnpm typecheck` is clean for `src/`.

The original "split-brain" framing (OpenClaw sensory-motor layer + Hermes
cognitive kernel) is the design lineage. In practice today the running product is
the FastAPI agent; the Electron GUI is the operator surface.

## Key components

1. **Nova** — the orchestrating agent (planning, tool routing, memory).
2. **9 worker lanes** — see [[system-patterns]] for the schedule.
3. **Semantic Firewall** — validates tool calls before execution (Python core +
   TS mirror, shared `config/firewall-rules.json`).
4. **Learning loop** — Wilson-ranked champion/challenger strategy selection; the
   agency literally gets better at outreach over time. See [[claude-brain]].
5. **The vault** — this Obsidian knowledge layer; the curated shared brain for
   Mark and Claude. Synced from production each session.

## Linked

- [[business-model]] · [[product-context]] · [[system-patterns]] · [[tech-context]] · [[claude-brain]]
