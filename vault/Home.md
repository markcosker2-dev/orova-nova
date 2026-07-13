---
name: home
description: OROVA / HermesClaw vault dashboard — start here
type: brain
created: 2026-07-03
status: active
---

# 🏠 OROVA / HermesClaw — Mission Vault

The shared brain for OROVA/HermesClaw — curated knowledge for **Mark** and **Claude**.
Production data (leads DB, learned strategies) lives in SQLite on Render; this
vault holds what's worth *reading*, not a database mirror.

> [!tip] Start here every session
> 1. [[10-brain/active-context|🧭 Active Context]] — what's happening right now (read first)
> 2. [[hermesclaw-orova/STATUS|📊 STATUS]] — current snapshot, next action, blockers
> 3. Run `python scripts/vault_pull.py` to pull Nova's latest production learning in

---

## 🧠 The Brain — `10-brain/`

The living knowledge base. If two notes disagree, **[[10-brain/active-context|active-context]] wins** (it's the newest "now" note).

| Note | Purpose |
|---|---|
| [[10-brain/active-context\|Active Context]] | What's happening right now — **read first**, keep current |
| [[10-brain/project-brief\|Project Brief]] | What OROVA/HermesClaw is and why |
| [[10-brain/business-model\|Business Model]] | Packages, pricing, ICP — commercial source of truth |
| [[10-brain/roadmap\|Roadmap]] | What to execute next (split Mark / Claude / Nova) |
| [[10-brain/system-patterns\|System Patterns]] | The 9 worker lanes, agent loop, firewall |
| [[10-brain/claude-brain\|The Brain]] | LLM routing, current models, how Nova learns |
| [[10-brain/tech-context\|Tech Context]] | Runtimes, env vars, hard constraints |
| [[10-brain/product-context\|Product Context]] | Product surface & UX |
| [[10-brain/profitability-plan\|Profitability Plan]] | Funnel math & unit economics |
| [[10-brain/strategy-snapshot\|Strategy Snapshot]] | What Nova has learned (auto-synced) |
| [[10-brain/progress\|Progress]] | Running done/remaining log |

## 🎯 Owner's Operating System — `hermesclaw-orova/`

How Mark decides and closes. **Any AI acting for Mark reads the playbook first.**

> [!info] Playbook — [[hermesclaw-orova/playbook/README|index]]
> [[hermesclaw-orova/playbook/client-acceptance|Client Acceptance]] · [[hermesclaw-orova/playbook/pricing-and-negotiation|Pricing & Negotiation]] · [[hermesclaw-orova/playbook/outreach-voice|Outreach Voice]] · [[hermesclaw-orova/playbook/red-lines|Red Lines]] · [[hermesclaw-orova/playbook/escalation|Escalation]] · [[hermesclaw-orova/playbook/judgment-calls|Judgment Calls]]

> [!info] Close-Kit — [[hermesclaw-orova/close-kit/README|index]] (from "yes" to signed & paid)
> [[hermesclaw-orova/close-kit/service-agreement|Service Agreement]] · [[hermesclaw-orova/close-kit/invoice-template|Invoice]] · [[hermesclaw-orova/close-kit/onboarding-checklist|Onboarding Checklist]]

- [[hermesclaw-orova/README|Project overview]] · [[hermesclaw-orova/STATUS|STATUS]] · [[hermesclaw-orova/progress|progress log]]

## ⚙️ Operations — `20-ops/`

- **Briefs** → `20-ops/briefs/` — daily CEO briefs pulled from production
- **Sessions** → `20-ops/sessions/` — session notes worth keeping. Recent:
  [[20-ops/sessions/2026-07-13-junk-email-fix-and-hunt-verdict|2026-07-13 junk-email & hunt]] · [[20-ops/sessions/2026-07-12-handoff|2026-07-12 master handoff]]
- **Improvement log** → `20-ops/improvement-log.md` (auto-synced) — champion/challenger changes

## 🎣 Pipeline — `30-leads/`

One wiki note per enriched lead, synced from production by `vault_pull.py`.

## 📌 Decisions — `40-decisions/`

- [[40-decisions/0001-adopt-obsidian|ADR-0001 — Adopt Obsidian]]
- [[40-decisions/0002-lead-engine-and-subagents|ADR-0002 — Lead engine & subagents]]
- [[40-decisions/0003-owner-name-first-lead-engine|ADR-0003 — Owner-name-first lead engine]]
- [[40-decisions/0004-obsidian-brain-and-skill-improvement|ADR-0004 — Obsidian brain & skill improvement]]

## 📚 Reference — `90-docs/`

- [[docs-index|Reference Docs index]] — guides, setup, historical audits
- Start: [[HERMESCLAW_GUIDE|HermesClaw Guide]] · [[SETUP|Setup]]

---

> [!note]- Vault conventions & known cleanup
> **Every note** carries frontmatter: `name`, `description`, `type` (brain/lead/brief/decision/session/doc), `created`, `status`. Never edit `.obsidian/`; never create docs at the repo root.
> **Known consolidation candidates** (see the 2026-07-13 audit): `hermesclaw-orova/progress.md` overlaps `10-brain/progress.md`; several `90-docs/` reports (AUDIT/FINAL_AUDIT/SYSTEM_AUDIT/PRODUCTION_READY/DEPLOYMENT_COMPLETE) are one-time historical dumps that could be archived. Left in place pending owner decision.
