---
name: home
description: OROVA vault dashboard — start here
type: brain
created: 2026-07-03
status: active
---

# OROVA Mission Vault

The shared brain for OROVA/HermesClaw — curated knowledge for Mark and Claude.
Production data (leads DB, learned strategies) lives in SQLite on Render; this
vault holds what's worth *reading*, not a database mirror.

## The Brain

- [[10-brain/active-context|Active Context]] — what's happening right now (keep this current)
- [[10-brain/project-brief|Project Brief]] — what OROVA is and why
- [[10-brain/system-patterns|System Patterns]] — how the 9 worker lanes and agents fit together
- [[10-brain/tech-context|Tech Context]] · [[10-brain/product-context|Product Context]] · [[10-brain/progress|Progress]]

## Operations

- **Briefs** → `20-ops/briefs/` — daily CEO briefs pulled from production (`python scripts/vault_pull.py`)
- **Sessions** → `20-ops/sessions/` — Claude Code session notes worth keeping

## Pipeline

- **Leads** → `30-leads/` — one wiki note per enriched lead (auto-written by the scraper, synced by the pull script)

## Decisions

- [[40-decisions/0001-adopt-obsidian|ADR-0001: Adopt Obsidian as the knowledge layer]]

## Reference

- `90-docs/` — deployment guides, audits, setup docs
- Agent personas & tools: `../HermesClaw/context/AGENTS.hermesclaw.md`, `../HermesClaw/context/TOOLS.hermesclaw.md`
