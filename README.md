# OROVA Nova — FREE Autonomous Business OS

🚀 **100% FREE OPERATION** — AI-powered sales pipeline that finds leads, writes emails, makes calls, manages ads, and runs your business 24/7.

**FREE Services Used:**
- 🤖 **Gemini 1.5 Flash** (Primary AI - 15 RPM, 1000 RPD, 250K TPM)
- 🗄️ **Upstash Redis** (Database - 500K commands/month, 256MB storage)
- 📧 **AgentMail** (Email - Free tier available)
- 📞 **Retell AI** (Voice calls - Generous free tier)
- 📊 **Google Sheets** (Free)

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

## Deploy to Render (100% FREE, No Card)

1. Fork this repo
2. Go to [render.com](https://render.com) → Sign up with GitHub
3. New → Web Service → Connect this repo
4. It auto-detects the Dockerfile
5. Add environment variables in dashboard:
    - `GEMINI_API_KEY` (free from Google AI Studio)
    - `UPSTASH_REDIS_URL` (free from upstash.com)
    - `UPSTASH_REDIS_TOKEN` (free from upstash.com)
    - `TELEGRAM_BOT_TOKEN` (free from @BotFather)
    - `RETELL_API_KEY` (free tier available)
    - `RETELL_AGENT_ID`
    - `RETELL_FROM_NUMBER`
    - `AGENTMAIL_API_KEY` (free tier available)
    - `OROVA_API_KEY` (any password you choose)
6. Deploy

### Get FREE API Keys

**Gemini 1.5 Flash (AI):**
- Go to [Google AI Studio](https://aistudio.google.com/)
- Create API key (completely free)

**Upstash Redis (Database):**
- Go to [upstash.com](https://upstash.com/)
- Create free Redis database
- Copy URL and token

**AgentMail (Email):**
- Go to [agentmail.ai](https://agentmail.ai/)
- Sign up for free tier

**Retell AI (Voice calls):**
- Go to [retell.ai](https://retell.ai/)
- Generous free tier available

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

## Tech Stack (100% FREE)

- Python 3.10 + FastAPI
- Telegram Bot API (free)
- **Gemini 1.5 Flash** (free AI - primary)
- **Upstash Redis** (free database - primary)
- Retell AI (voice calls - free tier)
- AgentMail (email - free tier)
- DuckDuckGo + Scrapling + Playwright (lead search)
- Google Sheets API (free)
- Meta Graph API (ads - when budget available)

### FREE Tiers Used

| Service | Free Tier Limits | Usage |
|---------|------------------|-------|
| Gemini 1.5 Flash | 15 RPM, 1000 RPD, 250K TPM | Primary AI engine |
| Upstash Redis | 500K commands/month, 256MB | Database & caching |
| AgentMail | 100 emails/day | Email outreach |
| Retell AI | 100 minutes/month | Voice calls |
| Google Sheets | Unlimited | Lead storage |
| Telegram | Unlimited | Bot interface |

## License

Private — OROVA
