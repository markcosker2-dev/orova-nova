# OROVA Nova — Autonomous Business OS

AI-powered sales pipeline that finds leads, writes emails, makes calls, manages ads, and runs your business 24/7.

## 12 Agents

| Agent | Role |
|-------|------|
| HAWK | Lead Hunter — 3-tier web search |
| SAGE | Media Buyer — Meta Ads with kill-switch |
| Quill | Copywriter — Cold emails, sequences, ad copy |
| Oracle | Analytics — Pipeline reports, ROI |
| Nova | Orchestrator — ReAct planner, 51 tools |
| Viper | Stealth Scraper — Cloudflare bypass |
| Closer | Proposals — Discovery call booking |
| Sentinel | System Monitor — Health alerts |
| NightShift | After-Hours — Handles US leads while you sleep |
| Revenue | Pipeline Tracker — Dollar values, forecast |
| Warmup | Email Domain Health — Gradual sending |
| Signals | Buying Signal Monitor — Funding, hiring detection |

## Deploy to Render (Free, No Card)

1. Fork this repo
2. Go to [render.com](https://render.com) → Sign up with GitHub
3. New → Web Service → Connect this repo
4. It auto-detects the Dockerfile
5. Add environment variables in dashboard:
   - `TELEGRAM_BOT_TOKEN`
   - `MIMO_API_KEY` (free from kilocode.ai)
   - `MIMO_BASE_URL` = `https://api.kilocode.ai/v1`
   - `MIMO_MODEL` = `MiMo/v2-pro`
   - `RETELL_API_KEY`
   - `RETELL_AGENT_ID`
   - `RETELL_FROM_NUMBER`
   - `AGENTMAIL_API_KEY`
   - `OROVA_API_KEY` (any password you choose)
6. Deploy

### Keep It Awake (Free)

1. Go to [uptimerobot.com](https://uptimerobot.com) → Sign up (free)
2. Add monitor: `https://your-app.onrender.com/health`
3. Interval: 5 minutes

Your bot now runs 24/7 for free.

## Local Development

```bash
cp .env.example .env
# Fill in your API keys in .env
pip install -r requirements.txt
python -m app.main
```

## Dashboard

Open `http://localhost:7860` after starting.

## Telegram Commands

| Command | Action |
|---------|--------|
| `/start` | Nova online |
| `/report` | Daily report |
| `/available` | Your availability |
| `/slots` | Next booking slots |
| `/block YYYY-MM-DD` | Block dates |
| `/unblock YYYY-MM-DD` | Unblock dates |

## Tech Stack

- Python 3.10 + FastAPI
- Telegram Bot API
- MiMo v2 Pro (free AI) + OpenRouter + Groq fallback
- Retell AI (voice calls)
- DuckDuckGo + Scrapling + Playwright (lead search)
- SQLite (WAL mode)
- Meta Graph API (ads)

## License

Private — OROVA
