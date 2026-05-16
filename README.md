---
title: OROVA Mission Control
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# Moltbot v2 (Free OpenClaw)

A production-ready, autonomous AI agent designed to run for free on Railway/Render.

## 🚀 Features
- **24/7 Operations:** Runs continuously with a health check server.
- **Smart Routing:** Shortcuts for instant replies, AI for complex tasks.
- **Lead Generation:** Headless browser scraping via Playwright.
- **Unified AI:** Auto-fallback (DeepSeek -> Groq -> OpenRouter -> Gemini).

## 🛠 Deployment (Render)
1. Fork this repo or connect it to Render.
2. Create a new Web Service with `Docker` runtime.
3. Point Render to this repo and branch.
4. Add environment variables in Render:
   - `DASHBOARD_API_KEY`
   - `CRON_SECRET`
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `RENDER_EXTERNAL_URL` (recommended)
   - `DATABASE_URL` = `sqlite+aiosqlite:///app/app/data/orova_v5.db`
   - `GOOGLE_CREDENTIALS_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`

## 🛠 Local Setup
```bash
# 1. Install deps
python -m pip install -r requirements.txt

# 2. Config
cp .env.example .env
# Edit .env with your API keys and secrets

# 3. Run locally
python app/main.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 18789
```
