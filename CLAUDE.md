# CLAUDE.md — OROVA / HermesClaw

**This is the single entry point for every AI agent working here** (Claude Code
since 2026-11-26; `AGENTS.md` only points here for Codex/other tools).

## Session start — read in this order

1. `vault/10-brain/operating-brief.md`: the rules, boundaries and priorities
   (Mark's master brief). Non-negotiable.
2. `vault/10-brain/active-context.md`: current state, with **verification
   dates**. Anything older than a few days is a claim, not a fact. Recheck it.
3. The newest `vault/20-ops/sessions/` notes, plus the owner playbook
   (`vault/hermesclaw-orova/playbook/`) before any judgment call.
4. `git status`, branch, last commits. Preserve unrelated work; never reset or
   force-push.

Or run the `/orova-start` skill, which walks the list.

**Hard boundaries (from the brief):** strict **$0** budget. **Outreach is
PAUSED**: no sends, no calls, no AgentMail cold email, no publishing, no
deploys, no spend, no credential or permission changes, no lead deletion, and no
releasing held leads without explicit, current owner approval. Never invent
clients, results, offers, prices, trials, urgency or consent. Med spas are
excluded. The repo is **public**: no secrets, Sheet IDs, phone numbers, prospect
PII, raw logs or DB dumps in git or the vault.

**Cloud sessions:** the owner's OneDrive Obsidian vault is the *same* `vault/`
folder in his local checkout. Cloud sessions see only the repo copy, so write
vault updates here and tell Mark to pull. Render (`orova-nova.onrender.com`)
is blocked by the default network policy. Say live state is unverified rather
than guessing.

## Council protocol (owner mandate, 2026-07-11)

The claude-council plugin is Claude's own advisory board, not a user tool.
When its commands are available (`/claude-council:ask` in the skills list):

- **Consult the council before committing to** architecture decisions,
  non-obvious bug diagnoses, business-sensitive copy, and any judgment call
  where the owner playbook (`vault/hermesclaw-orova/playbook/`) doesn't
  settle it. Weigh the outside opinions, then decide — the council advises,
  Claude decides, Mark overrules.
- The stop-gate (`.claude/council-stop-gate.json`, local-only: `.claude/*` is
  gitignored, so it is absent in fresh cloud checkouts) has a second model
  review Claude's uncommitted diff at end of turn. Treat a `BLOCK:`
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
| Prospect data | Storage gate: `lead_validator.validate_lead_for_storage` → `_lead_repo.save_lead` (the `leads` table) |
| Contact evidence | Evidence ledger (`evidence_json`) |
| Pipeline state / history | Event log (`events` table, ADR-0007) |
| Scores | `score_lead_icp` (server-side recompute) |
| Business facts | Knowledge compiler (`knowledge/`, ADR-0005) |
| Decisions | ADRs (`vault/40-decisions/`) |
| Session history | Vault (`vault/20-ops/sessions/`) |
| Runtime configuration | Environment (Render env vars / `.env`) |

If two modules own the same information, one must become a projection.

> **Corrected 2026-08-03.** This table used to name `app/core/contracts.py` as
> the owner of prospect data. **That file does not exist and never did** —
> ADR-0010 listed it as a plan, and a table entry pointing at a phantom sends
> every future session looking for a canonical owner that isn't there. The real
> owner is the storage gate every ingest path (hunt, CSV import, Sheets restore)
> converges on. ADR-0010's own closing line applies to its own table:
> *contracts codify reality, not aspiration.*
>
> Two further entries are aspirational rather than false, and are flagged here
> rather than silently trusted:
> - **Pipeline state / history → event log.** The `events` table does **not
>   exist in production** (`no such table: events`), and Google Sheets — not the
>   event log — currently drives the approval→call state machine. PR #129 fixes
>   the table; the Sheets coupling is unresolved.
> - **Contact evidence → evidence ledger.** Real, but most rows now arrive from
>   licence registries with no email at all, so the ledger is thinly populated.

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

## Engineering rules (carried over from the Codex `AGENTS.md`)

- Keep two lanes separate. One is OROVA's own researched, individual
  prospecting. The other is future clients' consent-checked inbound Meta-lead
  qualification. Retell executes authorized calls; it never decides legality.
- AI may reason and draft. Deterministic code owns permission, side effects,
  state transitions, idempotency and result verification.
- The DB and events are truth. Sheets is a projection and a partial
  lead-recovery tier, **not** a full DB backup.
- Inspect the real caller/data contract before changing anything. Patch the
  smallest material failure. Run targeted then full gates, then verify
  external state.
- Never start the app locally with production `.env`. Startup re-registers the
  Telegram webhook and starts background jobs.
- `ZERO_BUDGET_MODE=1` and `CALLS_AUTOPILOT=0` stay on. Don't disable them for a
  test or demo.
- Mark merges and approves deploys. Render's free disk is ephemeral, so verify
  a full backup before any deploy. Release gate: `operating-brief.md` §9.
- Chat history lives in bounded `nova_chat:<chat_id>` entries in `state_store`.
- Report every item as *local/tested → committed → merged → deployed →
  live-verified*, with the date.

## Practical notes

- Tests: `pip install -r requirements.txt pytest pytest-asyncio`, then
  `python -m pytest tests -q` (**1,807 passing** on 2026-11-26; without
  `pytest-asyncio` about 120 async tests fail spuriously). Full local
  benchmark: `python scripts/nova.py benchmark` (can exceed 2 min; a timeout is
  not a pass).
- Gates: `python scripts/compile_knowledge.py --check`, `python scripts/check_secrets.py`;
  security lint is the narrow ruff gate in `.github/workflows/ci.yml`.
- Nova's planner injects the first ~2,000 chars of `vault/10-brain/active-context.md`
  (`app/core/vault_context.py`). Keep the current facts at its top.
- httpx must stay 0.27.2 (starlette 0.27 TestClient vs mcp/ollama constraints — see requirements.txt comment).
- Production knowledge (CEO briefs, leads) is pulled into the vault with `python scripts/vault_pull.py` (needs `RENDER_EXTERNAL_URL` + `DASHBOARD_API_KEY` in `.env`).
