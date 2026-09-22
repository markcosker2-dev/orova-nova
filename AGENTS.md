# OROVA / Nova — Codex entry point

Read `vault/90-docs/zero-budget-operations-2026-09-21.md` first, then
`vault/10-brain/active-context.md` and the owner playbook under
`vault/hermesclaw-orova/playbook/`. Historical notes describe historical
deployments, not present facts. `CLAUDE.md` remains reference material.

## Mission and boundaries

Help Mark get OROVA's first paying client on a $0 pre-revenue budget.
Primary ICP: custom home builders/high-end remodelers on the US West Coast;
secondary: luxury real-estate top producers. Med spas are excluded (ADR-0015).
Diagnose empty pipeline versus unqualified enquiries before proposing a package.
Commercial terms are unresolved: never invent offers, prices, trials, clients,
results, urgency, crew size, or contact consent.

Extend the existing database, evidence ledger, event log and router before
introducing abstractions. Every change must improve data quality, conversion,
or reliability. Prefer disabling unnecessary runtime work to deleting connected
modules blindly. No paid dependency, purchase, ad spend or unsolicited blast.

## Canonical owners

- Business facts: `knowledge/facts/company.json`, compiled projections in
  `app/core/business_context.json` and `vault/10-brain/facts.md`.
- Prospect data: `lead_validator.validate_lead_for_storage` and `_lead_repo`.
- Contact evidence: `evidence_json`; scores are computed server-side.
- Event history: `events`; configuration: environment; decisions: vault ADRs.
- Chat history: bounded `nova_chat:<chat_id>` entries in existing `state_store`.

## Safe operation

- Never start the app locally with production `.env`: startup re-registers
  Telegram's webhook and starts background jobs.
- Never commit credentials, database exports, raw logs or prospect contact data.
- Keep approval, consent, suppression, postal-address and offer gates intact.
- `ZERO_BUDGET_MODE=1` is the default. Do not disable it to make a test/demo send.
- Mark's standing rule is that he merges; ask before changing live deployment.
- Render free disk is ephemeral. Verify full backup before deploying. Sheets
  preserves leads, not all conversation, suppression, approval and event state.
- Preserve local edits and archived session history. Do not edit `vault/.obsidian`.
- Write operational notes in `vault/90-docs`, session notes in `vault/20-ops/sessions`.
- A council plugin is optional, never a dependency. No council review was available
  during the September repair; do not imply it ran.

## Verification

`python -m pytest tests -q`

`python scripts/compile_knowledge.py --check`

`python scripts/check_secrets.py`

Security lint is the narrow gate in `.github/workflows/ci.yml`.
Keep `httpx==0.27.2` unless FastAPI/Starlette are upgraded together and tested.
Distinguish tested locally, merged, and live: verify the exact `/health` build
SHA, successful restore, logs and real Telegram responses before claiming live success.
