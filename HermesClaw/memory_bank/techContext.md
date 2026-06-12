# Technical Context

## Runtimes
- **OpenClaw:** Node.js 22/24 (TypeScript)
- **Hermes Agent:** Python 3.11 with `uv` package manager
- **Database:** SQLite (app/orova.db) — primary state store
- **Google Sheets:** Live lead tracking (bidirectional sync)

## Key Dependencies
- FastAPI (Python web framework)
- AgentMail SDK (email sending)
- RetellAI (voice calls)
- gspread (Google Sheets)
- APScheduler (cron lane scheduling)
- Groq / OpenAI / Claude (LLM providers)

## Environment Variables (Critical)
- `AGENTMAIL_API_KEY` — Email sending (env var only, no hardcoded fallback)
- `TELEGRAM_BOT_TOKEN` — Alert delivery
- `PERSONAL_CHAT_ID` / `ADMIN_CHAT_ID` — Telegram target
- `DASHBOARD_API_KEY` — Mission Control auth
- `GOOGLE_CREDENTIALS_JSON` — Sheets access
- `HINDSIGHT_API_LLM_MAX_CONCURRENT=1` — Prevent LLM slot starvation

## Ports
- 18789 — OpenClaw Gateway
- 18790 — OROVA Backend / Mission Control
- 6969 — HermesClaw GUI dev
- 3100 — HermesClaw GUI production
- 9119 — Hermes standalone dashboard