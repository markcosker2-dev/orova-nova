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

## 🛠 Deployment (Railway)
1. Fork this repo.
2. Login to Railway.app.
3. "New Project" -> "Deploy from GitHub".
4. Set Variables:
   - `TELEGRAM_BOT_TOKEN`
   - `GROQ_API_KEY` (or others)
   - `PORT` = `8000`

## 🛠 Local Setup
```bash
# 1. Install deps
pip install -r requirements.txt
playwright install chromium

# 2. Config
cp .env.example .env
# Edit .env

# 3. Run
python app/main.py
```
