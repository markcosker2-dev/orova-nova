# Implementation Plan

**Make OROVA's Python backend fully autonomous on Render free tier by adding API endpoints for all HermesClaw features, wiring the worker scheduler into the FastAPI lifespan, and ensuring zero dependency on the Node.js layer.**

Render free tier runs Docker containers with Python/FastAPI only. The HermesClaw Node.js/Electron layer (bridge service, standalone manager, gateway, version channels, shared config registry) is a desktop development tool that doesn't deploy. All 5 changes below make the Python backend fully self-sufficient.

[Types]

No new types/classes needed. The existing OutcomeTracker, StrategyOptimizer, ImprovementLoop, CEOBrain, and proofread_email are complete. This plan adds API endpoints and startup wiring only.

[Files]

| Action | File | Purpose |
|--------|------|---------|
| **NEW** | `app/core/hermesclaw_endpoints.py` | 9 new API endpoints for autonomous features + registration function |
| MODIFY | `app/main.py` | Register endpoints in lifespan, add features to /health |
| MODIFY | `render.yaml` | Fix healthCheckPath to /api/health |
| MODIFY | `HermesClaw/electron/api/routes/orova.ts` | Add 9 new proxy route translations |
| VERIFY | `Dockerfile` | Already correct (port 18790, HEALTHCHECK uses /health) |

[Functions]

**New functions (app/core/hermesclaw_endpoints.py):**
- `register_hermesclaw_routes(app)` — Registers all endpoints onto FastAPI instance
- `POST /api/proofread` — Email proofreading via AI quality gate
- `POST /api/morning_brief` — CEO morning briefing generation
- `GET /api/health_check` — Pipeline health check (score + alerts)
- `POST /api/improvement_loop` — Self-improvement cycle trigger
- `POST /api/approve_pruning` — Stale lead pruning approval
- `GET /api/outreach_outcomes` — Query outreach outcome records
- `GET /api/learned_strategies` — Query learned strategies
- `POST /api/worker/trigger/lane/{lane}` — Manual worker lane trigger (1-9)

**Modified functions:**
- `app/main.py:lifespan()` — Added `register_hermesclaw_routes(app)` call
- `render.yaml` — Changed `healthCheckPath: /health` to `/api/health`
- `orova.ts:translatePath()` — Added 9 new route translations

[Classes]

No new or modified classes.

[Dependencies]

No new pip packages. The existing FastAPI, uvicorn, httpx, apscheduler, sqlite3 stack is sufficient.

[Testing]

```
python -c "from app.core.hermesclaw_endpoints import register_hermesclaw_routes; print('OK')"
python -c "import app.main; print('OK')"
```

[Implementation Order]

1. Create `app/core/hermesclaw_endpoints.py` ✅
2. Modify `app/main.py` to register endpoints ✅
3. Update `render.yaml` healthCheckPath ✅
4. Update `HermesClaw/electron/api/routes/orova.ts` ✅
5. Run verification ✅