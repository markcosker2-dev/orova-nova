# OROVA HermesClaw — Comprehensive System Audit Report
**Date:** 2026-06-21  
**Auditor:** GitHub Copilot  
**Scope:** Full-stack audit across Security, Reliability, Code Quality, Architecture, Configuration, and Operations

---

## Executive Summary

The OROVA HermesClaw system is an ambitious autonomous AI sales agency with a multi-agent architecture, self-learning loop, and extensive hardening layers. The codebase demonstrates significant defensive engineering (circuit breakers, semantic firewall, guardrails, drift guard, rate limiting). However, several **critical** and **high-severity** issues were identified that could lead to data loss, security breaches, or production outages.

| Category | Critical | High | Medium | Low | Info |
|---|---|---|---|---|---|
| Security | 3 | 4 | 3 | 2 | 1 |
| Reliability | 2 | 3 | 4 | 2 | 0 |
| Code Quality | 0 | 2 | 5 | 3 | 2 |
| Architecture | 1 | 2 | 3 | 1 | 1 |
| Configuration | 2 | 1 | 3 | 2 | 0 |
| Operations | 1 | 2 | 2 | 1 | 1 |
| **TOTAL** | **9** | **14** | **20** | **11** | **5** |

---

## 1. Security Audit

### 🔴 CRITICAL

#### S-01: Hardcoded Default Secret Key
**File:** `app/config.py:22`  
**Issue:** `secret_key: str = "change-me-in-production"` — If `.env` is missing this value, the app runs with a known secret. This is used for session tokens and potentially signing.  
**Fix:** Remove the default. Raise `ValidationError` if `secret_key` is not set in production.

```python
# Before
secret_key: str = "change-me-in-production"

# After
secret_key: str  # No default — pydantic will raise if missing
```

#### S-02: SQL Injection via String Interpolation in Router
**File:** `app/core/router.py:107-113`  
**Issue:** The `_approve_pruning_handler` builds SQL with f-string interpolation:
```python
placeholders = ",".join("?" for _ in lead_ids)
leads = await DatabaseManager.fetchall(
    f"SELECT business FROM leads WHERE id IN ({placeholders})",
    tuple(lead_ids)
)
```
While parameterized, the pattern is fragile — if `lead_ids` were ever sourced from untrusted input without validation, the placeholder count could mismatch. More critically, the same pattern is used for UPDATE:
```python
f"UPDATE leads SET status = 'Archived' ... WHERE id IN ({placeholders})"
```
**Fix:** Use a proper ORM or validate `lead_ids` is a list of integers before interpolation.

#### S-03: Dashboard API Key 500 on Missing Config
**File:** `app/main.py:316-318`  
**Issue:** `require_dashboard_api_key` returns a 500 with "Server misconfiguration" if `DASHBOARD_API_KEY` is not set. This leaks server configuration details to attackers and makes all protected endpoints 500 instead of 503.  
**Fix:** Return 503 Service Unavailable with a generic message. Log the misconfiguration server-side.

### 🟠 HIGH

#### S-04: CORS Allows Empty Origin
**File:** `app/main.py:197-204`  
**Issue:** `os.getenv("RENDER_EXTERNAL_URL", "")` adds an empty string to `allow_origins`. Some CORS implementations treat empty string as "allow any origin with credentials", which defeats the purpose of the allowlist.  
**Fix:** Filter out empty strings before adding to `allow_origins`.

#### S-05: Telegram Bot Token in Multiple Sync HTTP Calls
**File:** `app/skills/agentmail_skill.py:30-36`, `app/worker.py:87-93`  
**Issue:** `_send_telegram_alert` uses synchronous `requests.post()` inside async contexts. This blocks the event loop. Additionally, the token is read from env on every call without caching.  
**Fix:** Use `httpx.AsyncClient` for all HTTP calls in async contexts. Cache the token at module level.

#### S-06: No Request Size Limits on FastAPI Endpoints
**File:** `app/main.py`  
**Issue:** No `max_body_size` middleware configured. An attacker could send multi-GB payloads to `/telegram` or `/api/agents/retry`, causing OOM on the 512MB Render free tier.  
**Fix:** Add body size middleware:
```python
@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    # Reject bodies > 1MB
```

#### S-07: Session Tokens Stored in State Store Without Expiry Cleanup
**File:** `app/main.py:329-340`  
**Issue:** Dashboard tokens are stored in `state_store` but there's no cron or mechanism to purge expired tokens. Over time, this grows unbounded.  
**Fix:** Add a periodic cleanup job or use TTL-based storage (Redis with EX).

### 🟡 MEDIUM

#### S-08: Guardrails Sanitization is Bypassable
**File:** `app/core/guardrails.py:95-110`  
**Issue:** The forbidden phrase list uses simple regex substitution (`[REDACTED]`). Unicode homoglyph normalization is applied, but the list is static and easily bypassed with creative phrasing ("forget everything above", "new directive:").  
**Fix:** Consider using the semantic firewall for prompt injection detection instead of regex.

#### S-09: AgentMail API Key Exposed in Error Messages
**File:** `app/skills/agentmail_skill.py:44-45`  
**Issue:** Error messages from `_get_client()` may include partial API key info in exception strings.  
**Fix:** Sanitize error messages before returning to callers.

#### S-10: No HTTPS Enforcement
**File:** `app/main.py`  
**Issue:** The app doesn't enforce HTTPS. While Render provides TLS termination, direct access via IP would be unencrypted.  
**Fix:** Add HSTS headers and redirect middleware for non-HTTPS requests.

### 🟢 LOW

#### S-11: `secrets.compare_digest` Used Correctly
**Good:** The dashboard API key comparison uses constant-time comparison. No issue.

#### S-12: Rate Limiter Has No Per-Route Configuration
**File:** `app/core/hardening.py:82-120`  
**Issue:** Single global rate limit applies to all endpoints equally. Login/token endpoints should have stricter limits.  
**Fix:** Add per-route rate limit overrides.

### ℹ️ INFO

#### S-13: Guardrails Block Cloud Metadata Endpoints
**Good:** `guardrails.py` blocks `169.254.0.0/16` (cloud metadata) and `metadata.google.internal`. SSRF protection is comprehensive.

---

## 2. Reliability Audit

### 🔴 CRITICAL

#### R-01: SQLite Connection Pool Has No Real Pooling
**File:** `app/core/database.py:150-170`  
**Issue:** `get_connection()` creates a new `sqlite3.connect()` on every call. The `queue.Queue` pool is initialized but never populated — connections are opened and closed per-query. Under concurrent load, this causes `SQLITE_BUSY` errors and potential data corruption.  
**Fix:** Implement proper connection pooling with `aiosqlite` or use the initialized pool. Consider `sqlmodel` (already in requirements) for async ORM.

#### R-02: `_run_async` in Worker Can Deadlock
**File:** `app/worker.py:28-33`  
**Issue:** The `_run_async` helper uses `concurrent.futures.ThreadPoolExecutor` to run `asyncio.run()` inside a thread when an event loop is already running. If the inner coroutine tries to interact with the outer event loop (e.g., calling `DatabaseManager.query`), it will deadlock because `DatabaseManager.query` calls `asyncio.get_running_loop()`.  
**Fix:** Use `asyncio.run_coroutine_threadsafe()` consistently, or restructure the worker to run entirely within the FastAPI event loop.

### 🟠 HIGH

#### R-03: Race Condition on Global Counters in Worker
**File:** `app/worker.py:55-62`  
**Issue:** `daily_hunt_counter` and `daily_call_counter` are global variables modified without locks. In a multi-threaded environment (the worker uses `threading`), these can race.  
**Fix:** Use `threading.Lock()` or atomic operations for counter updates.

#### R-04: Telegram Queue Worker Has No Error Recovery
**File:** `app/core/telegram_queue.py:65-73`  
**Issue:** If `_handler` raises an exception, the worker logs it and continues. But if the handler consistently fails (e.g., AI provider down), the queue will drain without processing, and messages are lost (no retry/dead-letter queue).  
**Fix:** Implement a retry mechanism with exponential backoff and a dead-letter queue for permanently failed messages.

#### R-05: Vault Backup Can Fail Silently During WAL Mode
**File:** `app/skills/vault_skill.py:46-52`  
**Issue:** `sqlite3.connect().backup()` is used for hot-copy, but if the source DB is under heavy write load with WAL mode, the backup can hang indefinitely. There's no timeout on the backup operation.  
**Fix:** Add a timeout to the backup operation and run it in a thread with a deadline.

### 🟡 MEDIUM

#### R-06: Memory Distiller FAISS is Disabled But Code Still References It
**File:** `app/core/memory.py:15-20`  
**Issue:** `_initialize_faiss()` sets `self.index = None` and `self.encoder = None`, but `retrieve_context()` still has code paths that check `self.index` and attempt FAISS search. This is dead code that could confuse future maintainers.  
**Fix:** Remove the FAISS code paths entirely or add a clear `# TODO: Re-enable when RAM allows` comment.

#### R-07: Pattern Reinforcer Has No Idempotency Guard
**File:** `app/core/pattern_reinforcer.py:30-40`  
**Issue:** `_identify_winners()` queries `learned_patterns` but the GROUP BY doesn't include `winning_approach` in a way that prevents duplicate upserts. `_upsert_pattern` does an UPDATE but if no row matches, no INSERT occurs — patterns can be silently lost.  
**Fix:** Use `INSERT OR REPLACE` or `UPSERT` pattern in `_upsert_pattern`.

#### R-08: CEO Brain Auto-Execute Has No Cancellation Safety
**File:** `app/core/ceo_brain.py:130-140`  
**Issue:** `_schedule_auto_execute` stores proposals in `_pending_proposals` dict with `asyncio.Task` references. If the process restarts, all pending proposals are lost. There's no persistence of pending auto-executions.  
**Fix:** Persist pending proposals to `state_store` and reload on startup.

#### R-09: Health Check Endpoint Returns Hardcoded Agent Count
**File:** `app/main.py:345`  
**Issue:** `"agents_online": 6` is hardcoded. If any agent subsystem is down, the health check still reports 6 agents online.  
**Fix:** Dynamically check agent status from the worker scheduler or agent router.

### 🟢 LOW

#### R-10: Global `BACKGROUND_LOOP` Variable
**File:** `app/main.py:30`  
**Issue:** `BACKGROUND_LOOP` is a module-level global that's set during lifespan startup. If the event loop restarts (e.g., after a crash), the stale reference could cause issues.  
**Fix:** Use a more robust reference pattern or check `is_running()` before use.

#### R-11: `_task_loop_running` Flag Not Thread-Safe
**File:** `app/main.py:33`  
**Issue:** `_task_loop_running` is a module-level boolean modified from async context. While Python's GIL provides some protection, this is not formally thread-safe.  
**Fix:** Use `asyncio.Event` for task loop coordination.

---

## 3. Code Quality Audit

### 🟠 HIGH

#### CQ-01: Massive Planner File with 50+ Imports
**File:** `app/core/planner.py:1-50`  
**Issue:** The planner imports 50+ functions from 30+ skill modules at module level. Any import failure (missing dependency) crashes the entire application. The `try/except` blocks for `elite_scrape`, `vision_browse`, and `mega_memory` show awareness of this, but most skills have no such guard.  
**Fix:** Use lazy imports inside `available_functions` or a skill registry pattern that gracefully degrades.

#### CQ-02: Duplicate Identity Probe Logic
**Files:** `app/core/router.py:18-22`, `app/core/planner.py:55-62`  
**Issue:** Identity probe detection regex is defined independently in both `router.py` and `planner.py` with slightly different patterns. This violates DRY and means fixes must be applied in two places.  
**Fix:** Centralize identity probe detection in `guardrails.py` and import from there.

### 🟡 MEDIUM

#### CQ-03: Inconsistent Error Handling Patterns
**Files:** Multiple  
**Issue:** Some skills return `{"status": "error", "message": "..."}` (agentmail), others return `{"success": False, "error": "..."}` (gmail, outbound_dialer), and others raise exceptions. The planner has to handle all three patterns.  
**Fix:** Define a standard result type (e.g., `SkillResult` dataclass) and enforce it across all skills.

#### CQ-04: Bare `except:` Clauses
**File:** `app/core/planner.py:356`  
**Issue:** `except:` (bare except) is used when parsing tool call arguments. This swallows `KeyboardInterrupt` and `SystemExit`.  
**Fix:** Use `except Exception:` instead.

#### CQ-05: `np` Import in Memory Distiller Without numpy in Requirements
**File:** `app/core/memory.py:4`  
**Issue:** `import numpy as np` is at the top of the file, but `numpy` is not in `requirements.txt`. If FAISS is ever re-enabled, this will crash.  
**Fix:** Move the import inside the method that uses it, or add numpy to requirements.

#### CQ-06: Tool Definitions Use Inconsistent Schema Styles
**File:** `app/skills/definitions.py`  
**Issue:** Some tool definitions use `strict: True` and `additionalProperties: False`, while others don't. Some use `pattern` regex, others don't. This inconsistency makes it harder for the LLM to generate valid tool calls.  
**Fix:** Standardize all tool definitions with `strict: True` and `additionalProperties: False`.

#### CQ-07: `DatabaseManager` Mixes Sync and Async Methods
**File:** `app/core/database.py`  
**Issue:** `get_metrics()`, `get_clients()`, `get_cold_leads()` are synchronous (create new connections), while `query()`, `fetchone()`, `fetchall()` are async. This dual pattern is confusing and error-prone.  
**Fix:** Convert all methods to async or use a proper async ORM.

### 🟢 LOW

#### CQ-08: `agent_router.py` Has Trivial Scoring Logic
**File:** `app/core/agent_router.py:15-35`  
**Issue:** `calculate_hawk_score` only checks 3 binary conditions and produces a 0-10 score. The "deep reasoning" in the docstring is aspirational.  
**Fix:** Either implement meaningful scoring or remove the misleading docstring.

#### CQ-09: `dispatch_task` and `get_all_statuses` Are Stubs
**File:** `app/core/agent_router.py:42-50`  
**Issue:** These functions return hardcoded values and are marked `[LEGACY]`. They're imported by the planner as real tools.  
**Fix:** Remove or properly implement.

#### CQ-10: `composio_action` is Always a Fallback
**File:** `app/core/planner.py:68`  
**Issue:** `composio_action` is always set to `make_disabled_tool_fallback(...)`, meaning it always returns an error. It's still in the tool definitions, wasting LLM context.  
**Fix:** Remove from tool definitions when not configured.

### ℹ️ INFO

#### CQ-11: Extensive Use of `SimpleNamespace` for LLM Responses
**File:** `app/core/ai_client.py`  
**Issue:** Using `SimpleNamespace` to mimic OpenAI response objects works but is fragile. If OpenAI changes their response schema, the compatibility layer breaks silently.  
**Fix:** Consider using pydantic models for response parsing.

#### CQ-12: `voice_audit` in `soul.py` is Never Called
**File:** `app/core/soul.py:80-90`  
**Issue:** The `voice_audit` function exists but is never invoked in the planner or router. It's dead code.  
**Fix:** Integrate into the planner's response pipeline or remove.

---

## 4. Architecture Audit

### 🔴 CRITICAL

#### A-01: DatabaseManager is a God Class / SPOF
**File:** `app/core/database.py`  
**Issue:** `DatabaseManager` is a single class with 30+ class methods handling all DB operations, connection management, migrations, metrics, state storage, and quota tracking. It's imported by virtually every module. Any failure in this class takes down the entire system.  
**Fix:** Decompose into:
- `ConnectionManager` — pool management
- `LeadRepository` — lead CRUD
- `MetricsRepository` — metrics tracking
- `StateStore` — key-value state
- `MigrationRunner` — schema migrations

### 🟠 HIGH

#### A-02: Circular Import Risk Between Core Modules
**Files:** `app/core/planner.py` ↔ `app/core/router.py` ↔ `app/core/ceo_brain.py`  
**Issue:** `router.py` imports from `planner.py`, `planner.py` imports from `ceo_brain.py`, and `ceo_brain.py` imports from `ai_client.py`. The `hermesclaw_endpoints.py` creates new instances of `Router`, `TaskPlanner`, and `UnifiedAIClient` on every request, creating circular dependency chains.  
**Fix:** Use dependency injection with a service container or FastAPI's dependency system.

#### A-03: No Dependency Injection — Objects Created Ad-Hoc
**Files:** Multiple  
**Issue:** `CEOBrain()` creates a new `UnifiedAIClient()` in `__init__`. `hermesclaw_endpoints.py` creates new `Router`, `TaskPlanner`, and `UnifiedAIClient` instances per request. This means multiple AI client instances, multiple DB connections, and no shared state.  
**Fix:** Use FastAPI's `Depends()` system to inject shared singletons.

### 🟡 MEDIUM

#### A-04: Worker Runs in Separate Thread with Its Own DB Connections
**File:** `app/worker.py`  
**Issue:** The worker uses `schedule` + `threading` to run periodic jobs. Each job creates its own DB connections and AI clients. There's no coordination with the FastAPI app's event loop.  
**Fix:** Migrate worker jobs to APScheduler (already imported in `main.py`) running within the FastAPI event loop.

#### A-05: Skill Functions Have No Common Interface
**Files:** `app/skills/*.py`  
**Issue:** Skills are plain functions with varying signatures (some sync, some async, some return dicts, some return strings). The planner has to handle all patterns.  
**Fix:** Define a `Skill` protocol/base class with standardized `async def execute(**kwargs) -> SkillResult`.

#### A-06: Self-Learning Loop is Not Actually a Loop
**File:** `app/core/self_learning.py`  
**Issue:** `SelfLearningLoop` has `record_trace()`, `detect_patterns()`, and `crystallize_skill()` methods, but there's no autonomous loop that calls them in sequence. The `pattern_reinforcer.py` is a separate system that does something similar but different.  
**Fix:** Consolidate the two learning systems or clearly define their boundaries.

### 🟢 LOW

#### A-07: Pipeline Engine Has No Error Propagation
**File:** `app/core/pipeline.py`  
**Issue:** If a pipeline step fails, there's no defined error propagation strategy. The next step receives the error string as input.  
**Fix:** Add step-level error handling with `on_failure` callbacks.

### ℹ️ INFO

#### A-08: Agent Roster is Hardcoded in Soul
**File:** `app/core/soul.py:12-20`  
**Issue:** The 9-agent roster (Atlas, Pixel, Quill, etc.) is defined in the system prompt but has no runtime representation. All tasks go through Nova's unified brain.  
**Fix:** This is acceptable for now but should be documented as aspirational architecture.

---

## 5. Configuration Audit

### 🔴 CRITICAL

#### CF-01: `secret_key` Default Allows Production Deployment Without Setting It
**File:** `app/config.py:22`  
**Issue:** (Duplicate of S-01) The default `"change-me-in-production"` means the app starts successfully without any secret key configuration. In production, this is a critical vulnerability.  
**Fix:** Add a validator:
```python
@field_validator('secret_key')
@classmethod
def secret_key_must_be_set(cls, v, info):
    if info.data.get('app_env') == 'production' and v == 'change-me-in-production':
        raise ValueError('secret_key must be changed in production')
    return v
```

#### CF-02: Multiple LLM API Keys Can All Be Empty
**File:** `app/config.py:28-42`  
**Issue:** All LLM API keys (`groq_api_key`, `openrouter_api_key`, `google_ai_studio_key`, `openai_api_key`) default to empty strings. The app will start but all AI calls will fail silently until at least one is configured. There's no startup validation.  
**Fix:** Add a startup check that at least one AI provider is configured, and log a prominent warning if none are.

### 🟠 HIGH

#### CF-03: `database_url` Points to Local SQLite by Default
**File:** `app/config.py:67`  
**Issue:** `database_url: str = "sqlite+aiosqlite:///./data/orova.db"` — The `sqlmodel`/`aiosqlite` URL is configured but `DatabaseManager` uses raw `sqlite3` with a different path (`DB_PATH` from `database.py`). The config value is never actually used.  
**Fix:** Either use the configured `database_url` or remove it from config to avoid confusion.

### 🟡 MEDIUM

#### CF-04: `hunt_targets` is a Comma-Separated String
**File:** `app/config.py:82-90`  
**Issue:** `hunt_targets: str = "dentists:Dallas TX,law firms:Houston TX,contractors:Austin TX"` uses a custom colon-separated format parsed by a property. This is fragile and hard to extend (what if a target contains a colon?).  
**Fix:** Use JSON or a proper structured config format.

#### CF-05: `dashboard_api_key` Defaults to Empty String
**File:** `app/config.py:25`  
**Issue:** If `DASHBOARD_API_KEY` is not set, all dashboard endpoints return 500. The app should fail to start or at least disable dashboard routes.  
**Fix:** Add startup validation that warns or fails if `dashboard_api_key` is empty in production.

#### CF-06: `openclaw_gateway_url` and `openclaw_gateway_token` Are Unused
**File:** `app/config.py:70-71`  
**Issue:** These config values are defined but never referenced in the codebase. Dead configuration.  
**Fix:** Remove or implement the OpenClaw gateway integration.

### 🟢 LOW

#### CF-07: `scraper_headless` and `scraper_concurrency` May Not Be Respected
**File:** `app/config.py:76-78`  
**Issue:** These settings are defined but it's unclear if all scraper skills read from `settings` vs. using hardcoded values.  
**Fix:** Audit all scraper skills to ensure they use `settings.scraper_*`.

#### CF-08: `biz_hours_start`/`biz_hours_end` Are Integers, Not Times
**File:** `app/config.py:79-81`  
**Issue:** Business hours are stored as plain integers (9, 17) without timezone awareness. The `biz_timezone` is separate.  
**Fix:** Consider using `time` objects with timezone for type safety.

---

## 6. Operational Audit

### 🔴 CRITICAL

#### O-01: Render Free Tier 512MB RAM with psutil + Multiple AI Clients
**Files:** `app/core/hardening.py`, `app/core/ai_client.py`  
**Issue:** The system targets Render's free tier (512MB RAM) but loads `psutil`, `numpy` (via memory.py), multiple `httpx.AsyncClient` instances, and a full Groq/OpenAI/Google SDK stack. The `MemoryMonitor` caps at 400MB but there's no enforcement — it only logs.  
**Fix:** Add a startup memory check that refuses to start if available RAM is below a threshold. Implement actual OOM protection (graceful degradation, not just logging).

### 🟠 HIGH

#### O-02: No Graceful Shutdown for Worker Threads
**File:** `app/worker.py`  
**Issue:** The worker scheduler runs in a daemon thread with `schedule.run_pending()`. When the main process receives SIGTERM (Render redeploys), the daemon thread is killed mid-operation. This can corrupt in-flight database writes.  
**Fix:** Implement a shutdown event and drain in-flight operations before exiting.

#### O-03: Keep-Alive Ping Creates Unbounded HTTP Connections
**File:** `app/main.py:170-178`  
**Issue:** The keep-alive ping creates a new `httpx.AsyncClient` on every iteration (inside the while loop). This leaks connection pools.  
**Fix:** Create the `httpx.AsyncClient` once outside the loop.

### 🟡 MEDIUM

#### O-04: Docker Compose Doesn't Match Render Configuration
**File:** `docker-compose.yml` vs `render.yaml`  
**Issue:** Docker Compose defines `gateway` + `agent_core` + `redis_cache` services, but Render deploys a single web service. The Docker Compose is outdated and doesn't reflect the actual deployment architecture.  
**Fix:** Update Docker Compose to match the single-service Render deployment, or document that it's for local development only.

#### O-05: No Log Rotation or Aggregation
**Files:** Multiple  
**Issue:** Logs go to stdout/stderr with no rotation. On Render, logs are captured but there's no structured logging (JSON format) for aggregation tools.  
**Fix:** Add structured JSON logging for production (`app_env == "production"`).

### 🟢 LOW

#### O-06: Health Check Endpoint is Too Lightweight
**File:** `app/main.py:285`  
**Issue:** `/health` only returns `{"status": "Operational"}`. It doesn't check DB connectivity, AI provider availability, or memory status. Render's health check won't detect partial failures.  
**Fix:** Add DB connectivity check and memory check to `/health`.

### ℹ️ INFO

#### O-07: `render.yaml` Has Commented-Out `healthCheckPath`
**File:** `render.yaml:18`  
**Issue:** The health check path is commented out. Render will use its default (TCP connection check), which is less informative than the `/health` endpoint.  
**Fix:** Uncomment `healthCheckPath: /health`.

---

## 7. Priority Remediation Roadmap

### Phase 1 — Immediate (This Week)
| # | Issue | Effort |
|---|---|---|
| 1 | S-01: Remove default `secret_key` | 5 min |
| 2 | S-06: Add request body size limits | 15 min |
| 3 | S-04: Filter empty CORS origins | 5 min |
| 4 | R-01: Fix SQLite connection pooling | 2 hr |
| 5 | O-03: Fix keep-alive client leak | 10 min |
| 6 | CF-01: Add secret_key validator | 10 min |
| 7 | CF-02: Add AI provider startup check | 30 min |

### Phase 2 — Short Term (Next 2 Weeks)
| # | Issue | Effort |
|---|---|---|
| 8 | R-02: Fix `_run_async` deadlock risk | 4 hr |
| 9 | R-03: Add thread locks to worker counters | 30 min |
| 10 | CQ-01: Lazy-load skill imports | 4 hr |
| 11 | CQ-02: Centralize identity probe detection | 1 hr |
| 12 | A-02: Break circular imports | 4 hr |
| 13 | A-03: Add dependency injection | 4 hr |
| 14 | O-02: Add graceful shutdown | 2 hr |
| 15 | O-06: Enhance health check | 1 hr |

### Phase 3 — Medium Term (Next Month)
| # | Issue | Effort |
|---|---|---|
| 16 | A-01: Decompose DatabaseManager | 8 hr |
| 17 | CQ-03: Standardize skill result types | 8 hr |
| 18 | CQ-07: Convert all DB methods to async | 4 hr |
| 19 | A-04: Migrate worker to APScheduler | 4 hr |
| 20 | A-05: Define Skill protocol/base class | 4 hr |
| 21 | O-04: Update Docker Compose | 2 hr |
| 22 | O-05: Add structured logging | 2 hr |

### Phase 4 — Long Term (Next Quarter)
| # | Issue | Effort |
|---|---|---|
| 23 | A-06: Consolidate learning systems | 8 hr |
| 24 | S-08: Replace regex guardrails with semantic detection | 8 hr |
| 25 | R-04: Add retry/dead-letter to Telegram queue | 4 hr |
| 26 | Full test suite (currently 0% coverage) | 40 hr |

---

## 8. Strengths Worth Preserving

The audit also identified several well-engineered patterns that should be maintained:

1. **Semantic Firewall** (`semantic_firewall.py`) — Comprehensive zero-trust tool execution layer with parameter validation, goal alignment scoring, and depth limits. This is production-grade.

2. **Circuit Breaker** (`circuit_breaker.py`) — Proper implementation with half-open state, cooldown periods, and global trip escalation. Well-designed.

3. **Decision Tracing** (`decision_trace.py`) — Full observability of agent decisions with markdown export. Excellent for debugging.

4. **SSRF Protection** (`guardrails.py`) — DNS rebinding protection, private IP blocking, and cloud metadata endpoint blocking. Thorough.

5. **Efficiency Optimizer** (`efficiency_optimizer.py`) — LRU cache for deterministic tools, context deduplication, and token budget tracking. Smart resource management.

6. **Drift Guard** (`drift_guard.py`) — 10 edge-case fallback plans with auto-resolution flags. Good defensive engineering.

7. **Vault Backup** (`vault_skill.py`) — Atomic hot-copy with WAL-safe backup and rolling prune. Solid data survivability.

8. **Telegram Queue** (`telegram_queue.py`) — Bounded queue with backpressure. Correct pattern for resource-constrained environments.

---

*End of Audit Report*
