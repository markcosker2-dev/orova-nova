# CLAUDE.md — OROVA / HermesClaw

## Council protocol (owner mandate, 2026-07-11)

The claude-council plugin is Claude's own advisory board, not a user tool.
When its commands are available (`/claude-council:ask` in the skills list):

- **Consult the council before committing to** architecture decisions,
  non-obvious bug diagnoses, business-sensitive copy, and any judgment call
  where the owner playbook (`vault/hermesclaw-orova/playbook/`) doesn't
  settle it. Weigh the outside opinions, then decide — the council advises,
  Claude decides, Mark overrules.
- The stop-gate (`.claude/council-stop-gate.json`, enabled) has a second
  model review Claude's uncommitted diff at end of turn. Treat a `BLOCK:`
  verdict as a real finding: fix or explicitly rebut it, never ignore it.
- If no council provider key is configured, note it once and proceed —
  the council is an amplifier, not a dependency.

## What this repo is

**HermesClaw is an autonomous AI SDR** (ADR-0006). Its one job: find qualified
prospects, research them, personalize outreach, start conversations, and book
meetings for OROVA. The north-star metric is booked meetings.

## Extension-first rule (owner mandate, 2026-07-21)

Before implementing any feature, first ask whether it can be expressed as an
extension of an existing abstraction — the evidence ledger, the event log,
the scorer, the pipeline, or the data contract. If yes, extend it. If no,
justify the new abstraction in an ADR before building it. Prefer subtraction
and consolidation over expansion. (Origin: ADR-0010; the evidence ledger
extending to email/phone/title instead of a parallel "trust layer" is the
canonical example.)

## Single-source-of-truth rule (owner mandate, 2026-07-21)

Every piece of information has exactly one canonical owner; anything else
holding it is a projection of that owner, never a second writer. Store
facts, compute views (e.g. store `last_checked`, derive staleness).

| Information | Canonical owner |
| --- | --- |
| Prospect data | Prospect contract (`app/core/contracts.py`, ADR-0010) |
| Contact evidence | Evidence ledger (`evidence_json`) |
| Pipeline state / history | Event log (`events` table, ADR-0007) |
| Scores | `score_lead_icp` (server-side recompute) |
| Business facts | Knowledge compiler (`knowledge/`, ADR-0005) |
| Decisions | ADRs (`vault/40-decisions/`) |
| Session history | Vault (`vault/20-ops/sessions/`) |
| Runtime configuration | Environment (Render env vars / `.env`) |

If two modules own the same information, one must become a projection.

## Three-things rule (owner mandate, 2026-07-21)

Every future feature must clearly improve at least one of: **data quality**,
**conversion rate**, or **operational reliability**. If it doesn't, don't
build it. Improvements should be driven by production evidence, not design
discussion — trustworthy data before automation, evidence before inference,
consolidation before expansion, production validation before declaring
success, real customer outcomes before further optimization.

- `app/` — "Nova", the SDR engine (Python/FastAPI, deployed on Render free tier at orova-nova.onrender.com). 9 scheduled worker lanes: hunting, outreach, replies, cold calls (Retell), backups, CEO brain, health, self-improvement, drips.
- `knowledge/` — canonical business facts + the build-time compiler (ADR-0005).
- `mission-control/` — the web dashboard served by the FastAPI app.
- `.claude/skills/sales-intelligence/` — the sales craft layer for Claude agents.
- `.clinerules` — the behavioral ruleset for AI tools working here; it complements this file.
- The former Electron desktop GUI lives on the `archive/electron-gui` branch (removed from `main` per ADR-0006 — restore by merging that branch if ever needed).

## The vault is the shared brain

`vault/` is an Obsidian vault and the project's curated knowledge base.

- **At session start** on product/strategy/architecture work: run `python scripts/vault_pull.py` to pull Nova's latest production learning into the vault, then read `vault/10-brain/active-context.md` and `vault/10-brain/strategy-snapshot.md`. This is the learning bridge — every session begins with what the agent has learned since last time. (Sync needs `DASHBOARD_API_KEY` + `RENDER_EXTERNAL_URL` in `.env`; it's idempotent and safe to re-run.)
- **Write session notes** worth keeping to `vault/20-ops/sessions/YYYY-MM-DD-topic.md` (use `vault/_templates/session.md`).
- **Record architectural decisions** as ADRs in `vault/40-decisions/NNNN-title.md` (template: `_templates/decision.md`).
- **Keep `vault/10-brain/active-context.md` current** when the project direction changes materially.
- **Every vault note carries frontmatter**:
  ```yaml
  ---
  name: kebab-case-slug
  description: one line
  type: brain | lead | brief | decision | session | doc
  created: YYYY-MM-DD
  status: active | done | archived
  ---
  ```

## Do NOT

- Mirror SQLite/production state (`memories` table, `learned_strategies`, lead rows) into markdown — the vault is curated knowledge, not a database replica.
- Edit anything under `vault/.obsidian/`.
- Create new documentation at the repo root — docs go in `vault/90-docs/` (root keeps only README/SECURITY/PRIVACY/TERMS).
- Name any vault folder `docs` — the repo `.gitignore` ignores `docs/` at every depth.

## Auto-memory bridge

Your auto-memory directory is for your own recall. Anything Mark should be able to read in Obsidian belongs in `vault/` instead.

## Practical notes

- Tests: `python -m pytest tests -q` (289+ passing baseline). Knowledge gate: `python scripts/compile_knowledge.py --check`.
- httpx must stay 0.27.2 (starlette 0.27 TestClient vs mcp/ollama constraints — see requirements.txt comment).
- Production knowledge (CEO briefs, leads) is pulled into the vault with `python scripts/vault_pull.py` (needs `RENDER_EXTERNAL_URL` + `DASHBOARD_API_KEY` in `.env`).
