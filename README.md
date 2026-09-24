# OROVA Nova

Nova is OROVA's sales assistant: a Python/FastAPI service, a Telegram interface,
and the Mission Control web dashboard. The business is pre-revenue and the
operating budget is $0.

Start with [the current operating guide](vault/90-docs/zero-budget-operations-2026-09-21.md)
and [Codex instructions](AGENTS.md). The Obsidian vault contains the business
decisions and historical handoffs; old notes are not evidence of current service state.

## What works without paid outreach

- Research and store prospects using existing sources, evidence and quality gates.
- Review the pipeline with Telegram `/status` and `/leads`.
- Prepare recorded contact details and an unsent first-message draft with `/contact ID`.
- Retain recent chat context; `/forget` clears only that context.
- Monitor incoming email, preserve approval/opt-out gates, and back up data.

`ZERO_BUDGET_MODE=1` defaults on: paid Retell calls and automated cold emails are
blocked, speculative CEO auto-execution and unnecessary scheduled work are off.
Free-tier API limits still apply. Groq/Gemini billing settings must be checked in
their accounts; possessing a key does not establish that it is free.

## Development

Use Python 3.11 or 3.12. Install `requirements.txt` plus `pytest pytest-asyncio`.
Run `python -m pytest tests -q`, `python scripts/compile_knowledge.py --check`,
and `python scripts/check_secrets.py`.

The app starts with `uvicorn app.main:app --host 127.0.0.1 --port 18790`.
**Do not run it locally using production credentials**: startup registers the
Telegram webhook and starts scheduled jobs. Use isolated test data and dummy
credentials for local verification.

## Deployment and data

Render uses the Dockerfile and serves Mission Control from `mission-control/`.
Check the exact build SHA at `/health`, not just HTTP 200. Free Render disk is
ephemeral. Sheets preserves leads; a working full database backup is needed for
conversation, approval, suppression and event state. Read the operating guide
before deploying, particularly its expired Google Drive authorization warning.

No contact records, keys, raw production logs or database exports belong in this
public repository. Business facts originate in `knowledge/facts/company.json`;
do not independently edit generated pricing or ICP projections.

The former Electron/HermesClaw desktop application is retained on
`archive/electron-gui`; its old setup instructions do not apply to this service.
See [LICENSE](LICENSE).
