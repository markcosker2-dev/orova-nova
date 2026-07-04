---
name: tech-context
description: Runtimes, dependencies, env vars, and the hard constraints
type: brain
created: 2026-07-03
status: active
---

# Technical Context

## Runtimes

- **Nova (the agent):** Python 3.11, FastAPI, on Render free tier. Local venv:
  `C:\Users\Mike\AppData\Local\hermes\hermes-agent\venv`.
- **HermesClaw GUI:** Node.js / TypeScript, Electron + esbuild.
- **Database:** SQLite (`app/orova.db`) — primary state store. Render disk is
  ephemeral, so state is backed up to Google Drive every 3h + on shutdown, and
  restored Drive-first on boot.

## Key dependencies

FastAPI · AgentMail SDK (email) · Retell.ai (voice) · google-generativeai
(Gemini) · Groq + OpenRouter (LLM) · APScheduler (lane cron) · httpx ·
BeautifulSoup + duckduckgo_search (lead sourcing) · gspread (Sheets).

## LLM stack (see [[claude-brain]] for detail)

3-tier routing in `app/core/ai_client.py`: **tier 1** Groq
`llama-3.3-70b-versatile` (primary, tool-calling) → **tier 2** native Gemini
2.5-flash → **tier 3** OpenRouter free models (`llama-3.3-70b`, `qwen3-next-80b`,
`qwen3-coder`). Retell call agent runs on gpt-4.1-mini.

## Critical env vars

| Var | Purpose |
|---|---|
| `GROQ_API_KEY` | Tier-1 brain. **Local copy is dead (401) — verify Render's is fresh.** |
| `GOOGLE_API_KEY` | Gemini tier-2 + embeddings. Empty locally — verify on Render. |
| `OPENROUTER_API_KEY` | Tier-3 fallback models |
| `AGENTMAIL_API_KEY` | Outreach email sending |
| `DASHBOARD_API_KEY` | Mission Control + vault-sync auth |
| `GOOGLE_APPLICATION_CREDENTIALS` | Drive backup/restore + vault (service acct) |
| `RETELL_FROM_NUMBER` / `RETELL_API_KEY` | Cold calls (number +1 716 670 3920) |
| `MAKE_CRM_WEBHOOK_URL` | Forward Retell events to Make.com CRM |
| `TELEGRAM_BOT_TOKEN` + `PERSONAL_CHAT_ID`/`ADMIN_CHAT_ID` | HITL approvals + alerts |
| `RENDER_EXTERNAL_URL` | Base URL for `scripts/vault_pull.py` |

## Hard constraints (don't "fix" these)

- **`httpx==0.27.2`** must stay pinned (starlette 0.27 TestClient vs mcp/ollama
  constraints — see `requirements.txt` comment).
- **python-telegram-bot removed** — it pinned httpx ~0.26 and was never imported.
- Render free tier = 512 MB RAM, ephemeral disk. Playwright/Chromium browser
  scrapers (e.g. Apollo) can't run there.
- `load_dotenv(".env")` explicitly — bare `load_dotenv()` fails under `python -`
  stdin with dotenv 1.2.2.

## Tests

`python -m pytest tests -q` → 98 passing · `npx vitest run` → 40 passing ·
`pnpm typecheck` clean (src only).
