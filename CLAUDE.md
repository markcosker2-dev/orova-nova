# CLAUDE.md — OROVA / HermesClaw

## What this repo is

- `app/` — "Nova", the autonomous lead-gen agent (Python/FastAPI, deployed on Render free tier at orova-nova.onrender.com). 9 scheduled worker lanes: hunting, outreach, replies, cold calls (Retell), backups, CEO brain, health, self-improvement, drips.
- `electron/` + `src/` — the HermesClaw desktop GUI (OpenClaw-based). `HermesClaw/` holds reference mirrors only; canonical code lives in `electron/`.
- `mission-control/` — the web dashboard served by the FastAPI app.
- `.clinerules` — the behavioral ruleset for AI tools working here; it complements this file.

## The vault is the shared brain

`vault/` is an Obsidian vault and the project's curated knowledge base.

- **At session start** on product/strategy/architecture work, read `vault/10-brain/active-context.md`.
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

- Python tests: `python -m pytest tests -q` (98 passing baseline). TS tests: `npx vitest run`. Typecheck: `pnpm typecheck`.
- httpx must stay 0.27.2 (starlette 0.27 TestClient vs mcp/ollama constraints — see requirements.txt comment).
- Production knowledge (CEO briefs, leads) is pulled into the vault with `python scripts/vault_pull.py` (needs `RENDER_EXTERNAL_URL` + `DASHBOARD_API_KEY` in `.env`).
