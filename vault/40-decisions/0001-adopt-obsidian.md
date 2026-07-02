---
name: adr-adopt-obsidian
description: "ADR: Adopt Obsidian as the knowledge layer over repo markdown"
type: decision
created: 2026-07-03
status: active
---

# ADR-0001: Adopt Obsidian as the knowledge layer

## Context

The repo accumulated 23+ disconnected markdown files (memory bank, lead wikis,
agent specs, deployment guides) that no code reads and no tool connects. The
CEO morning brief evaporated into Telegram with no durable copy. Mark needed
one place to browse, search, and link project knowledge; Claude needed durable
cross-session context.

## Decision

A `vault/` folder inside the repo is an Obsidian vault and the project's
shared brain. Git is the source of truth (no Obsidian Sync, no Git plugin).
Claude reads/writes it as plain files, guided by `CLAUDE.md`. Production
knowledge reaches the vault through one local pull script
(`scripts/vault_pull.py`) over the existing dashboard API — never via git
pushes from Render.

## Consequences

- Easier: search/graph over all project knowledge; briefs and leads become
  browsable documents; Claude sessions leave durable notes.
- Harder: one more convention to maintain (frontmatter, folder taxonomy).
- Given up: real-time sync of production state into markdown — by design.
  The vault is curated knowledge, not a SQLite mirror.
