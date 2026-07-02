# HERMESCLAW — OROVA Operational Guide

## What Is HermesClaw?

HermesClaw is a **desktop AI development & runtime management tool** built on [OpenClaw](https://github.com/openclaw/openclaw). It manages two AI runtimes simultaneously — a Node.js/Electron desktop shell (UI, extensions, gateway) and a Python agent (Nova/OROVA business logic). 

**Critical Reality:** HermesClaw is a **desktop application only**. It cannot run on Render.com — Render lacks a display server and Electron. The Python backend runs autonomously on Render via FastAPI + Uvicorn.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│               YOUR LOCAL MACHINE (Desktop Dev)                │
│                                                              │
│  HermesClaw Desktop App (Electron)                           │
│  ├── Port 6969 — Dev Dashboard (Vite)                       │
│  ├── Port 3100 — Production Dashboard                       │
│  ├── Port 18789 — OpenClaw Gateway                          │
│  ├── Port 18790 — OROVA Python Backend                      │
│  │                (FastAPI: Nova + all skills + DB)          │
│  └── Port 8642 — Hermes Agent Standalone                    │
│                                                              │
│  Mission Control Web UI (served by Render in production)     │
│  ├── Task Board, Analytics, Calendar                         │
│  ├── Lead Pipeline, Memory Bank, Team Structure              │
│  ├── Skills Hub, Pipeline Runner, Digital Office             │
│  ├── CEO Brain Panel (NEW)                                   │
│  ├── Email Proofreader (NEW)                                 │
│  ├── Self-Improvement Dashboard (NEW)                        │
│  └── Worker Lanes Control (NEW)                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    RENDER.COM (Production)                    │
│                                                              │
│  Docker Container (Python 3.12-slim, port 18790)             │
│  ├── FastAPI Server — All API endpoints                      │
│  ├── Nova (TaskPlanner) — 50+ sales skills                   │
│  ├── Worker — 9 autonomous lanes                             │
│  ├── CEO Brain — Morning briefs, health checks               │
│  ├── Self-Improvement Loop — Learns from outcomes            │
│  ├── Email Proofreader — Quality gate for emails             │
│  ├── SQLite DB — 15 tables                                   │
│  ├── Google Sheets Sync — Live lead/campaign data            │
│  ├── Mission Control Web UI (static files)                   │
│  ├── Telegram Bot — Primary user interface                   │
│  └── Keep-Alive Ping — Prevents free tier sleep              │
│                                                              │
│  NOTE: No HermesClaw Electron app — not possible on Render   │
└──────────────────────────────────────────────────────────────┘
```

## 9 Autonomous Worker Lanes

| Lane | Name | Interval | What It Does |
|------|------|----------|-------------|
| 1 | Fast Lane | 2 min | Approvals + Retell AI calls |
| 2 | Slow Lane | 60 min | Multi-tier lead hunting |
| 3 | Reply Monitor | 5 min | Check AgentMail for replies |
| 4 | Cold Escalation | 30 min | Escalate cold leads to call queue |
| 5 | Cloud Backup | 6 h | Google Drive database backup |
| 6 | CEO Brief | 17:00 PST | Morning briefing generation |
| 7 | Health Monitor | 2 h | Pipeline health check |
| 8 | Self-Improvement | 6 h | Strategy optimization loop |
| 9 | Drip Sequence | 1 h | Send pending sequence emails |

## 3 New Autonomous Components

### 1. Email Proofreader
Every outbound email passes through an AI quality gate:
- Checks grammar, tone, personalization, spam triggers, CAN-SPAM compliance
- Returns pass/rewrite/reject verdict with 0-100 quality score
- Auto-fixes on rewrite (max 2 retries)
- Blocks and alerts CEO on reject
- Logs all outcomes to `outreach_outcomes` table for self-improvement

### 2. Nova CEO Brain
Autonomous pipeline analysis and scheduling:
- **Morning Brief** (17:00 PST daily) — Pipeline metrics, 7-day averages, HOT replies, AI executive summary → Telegram
- **Pipeline Health Check** (every 2h) — Health score 0-100, stale lead detection, anomaly detection
- **Task Proposals** — Suggest hunt/reply/drip actions based on pipeline state
- **Auto-Schedule** — Calendar-aware daily plan prioritized by urgency

### 3. Self-Improvement Loop
Learns from every outreach outcome:
- **OutcomeTracker** — Records and queries outreach performance
- **StrategyOptimizer** — Finds best email framework, send timing, niche targeting
- **ImprovementLoop** — Runs every 6h, persists learned strategies, sends weekly "What I Learned" report
- **Stale Lead Pruning** — Proposes dead lead archiving via Telegram for CEO approval

## Database Tables

| Table | Purpose |
|-------|---------|
| `leads` | Lead records from hunting/enrichment |
| `clients` | Multi-tenant client workspaces |
| `outreach_outcomes` | Every email send + result (FOR NEW) |
| `learned_strategies` | Best frameworks, timings, niches (FOR NEW) |
| `drip_campaigns` | Active drip email sequences |
| `metrics` | Historical metric tracking |
| `state_store` | Key-value persistence for system state |
| `learned_patterns` | Pattern reinforcement system |
| `client_quotas` | Per-client API credit limits |

## API Endpoints (All New)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/proofread` | Proofread an email draft |
| POST | `/api/morning_brief` | Generate CEO morning briefing |
| GET | `/api/health_check` | Run pipeline health check |
| POST | `/api/improvement_loop` | Trigger self-improvement cycle |
| POST | `/api/approve_pruning` | Approve stale lead pruning |
| GET | `/api/outreach_outcomes` | Query outreach results |
| GET | `/api/learned_strategies` | Query learned strategies |
| POST | `/api/worker/trigger/lane/{lane}` | Manually trigger a worker lane |

## Development Workflow

### Local (HermesClaw Desktop)
1. Run `npm run dev` — Starts HermesClaw + Python backend
2. Dashboard at `http://localhost:6969`
3. Develop skills, test APIs, debug in real-time

### Deploy to Render
1. Push code to GitHub
2. Render auto-deploys via Dockerfile
3. Python backend runs on port 18790
4. Mission Control at `https://your-app.onrender.com`
5. Telegram bot handles all user interaction
6. 9 worker lanes run 24/7 in background
7. Keep-alive ping prevents cold starts

## Key Files

| File | Purpose |
|------|---------|
| `app/core/hermesclaw_endpoints.py` | ALL new API endpoints |
| `app/skills/email_proofreader.py` | AI email quality gate |
| `app/core/ceo_brain.py` | CEO Brain autonomous analysis |
| `app/core/self_improvement.py` | Learning engine + strategy optimization |
| `app/worker.py` | 9 autonomous worker lanes |
| `app/core/database.py` | DB schema + all 15 tables |
| `mission-control/index.html` | Web dashboard with 15 screens |
| `mission-control/js/app.js` | Dashboard JS with new screen renderers |
| `electron/utils/config.ts` | Port config (6969/3100/18789/18790) |
| `HermesClaw/electron/api/routes/orova.ts` | HermesClaw proxy routes |
| `render.yaml` | Render deployment config |
| `Dockerfile` | Container build instructions |

## Port Reference (Updated 2026)

| Port | Service | Environment Var |
|------|---------|-----------------|
| 6969 | HermesClaw Dev Dashboard | `HERMESCLAW_PORT_HERMESCLAW_DEV` |
| 3100 | HermesClaw Production Dashboard | `HERMESCLAW_PORT_HERMESCLAW_GUI` |
| 13210 | Local Host API Server | `HERMESCLAW_PORT_HERMESCLAW_HOST_API` |
| 18789 | OpenClaw Gateway | `HERMESCLAW_PORT_OPENCLAW_GATEWAY` |
| 18790 | OROVA Python Backend | `PORT` |