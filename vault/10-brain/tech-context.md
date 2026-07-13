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
  ephemeral; the design is Drive backup every 3h + Drive-first restore on boot.
  **Status 2026-07-13: Drive creds ARE set on Render — backup verified working
  since 2026-07-11 (`[Vault] Uploaded`), and the restore path (which had a
  `str`-vs-`Path` crash) was fixed in PR #61.** Every deploy still wipes the
  ephemeral disk, but the DB is now restored from the latest Drive snapshot on
  boot; Sheets remains the leads-only fallback. See [[active-context]].

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
| `GROQ_API_KEY` | Tier-1 brain. Valid `gsk_IdJ…` key set locally + on Render (fixed 2026-07-05). |
| `GOOGLE_API_KEY` | Gemini tier-2 + embeddings. |
| `OPENROUTER_API_KEY` | Tier-3 fallback. **Render's copy is INVALID (401 "user not found") — remove it**; its error masks real failures. |
| `AGENTMAIL_API_KEY` | Outreach email sending |
| `DASHBOARD_API_KEY` | Mission Control + vault-sync auth |
| `GOOGLE_REFRESH_TOKEN`/`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` | Drive backup/restore. **SET on Render — backup verified 2026-07-11, restore-path crash fixed in PR #61 (2026-07-13). Prod SQLite now survives deploys via the Drive snapshot.** |
| `RETELL_FROM_NUMBER` / `RETELL_API_KEY` | Cold calls (number +1 716 670 3920) |
| `SERPAPI_KEY` | Discovery + owner-name lookup — one shared 250/mo quota (health lane alerts at 90%) |
| `TOMBA_API_KEY`+`TOMBA_SECRET` / `PROSPEO_API_KEY` / `VERIFALIA_USERNAME`+`VERIFALIA_PASSWORD` | Owner-email finder layer (built, keys not yet set — sign up with the AgentMail address, Tomba blocks webmail) |
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

`python -m pytest tests -q` → 197 passing (2026-07-10) · `npx vitest run` → 40
passing · `pnpm typecheck` clean (src only). Known benign warnings: starlette
0.27's own TestClient triggers httpx deprecation notices — inside the pinned
package, goes away when fastapi/starlette are eventually upgraded together
with the httpx pin.
