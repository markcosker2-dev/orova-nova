---
name: system-patterns
description: How the 9 worker lanes, the agent loop, and the firewall fit together
type: brain
created: 2026-07-03
status: active
---

# System Patterns

## Agent execution loop

1. Nova receives a goal → scopes the relevant tools (`_scope_tools()`).
2. **Semantic Firewall** validates each tool call before execution (rules in
   `config/firewall-rules.json`, shared by the Python core and the TS mirror).
3. Circuit breaker prevents runaway execution; per-provider breakers open on
   repeated LLM failures and cool down.
4. Efficiency optimizer caches results to cut redundant calls.
5. Drift guard watches for goal deviation.
6. High-risk actions go through a **Telegram HITL approval** (approve/reject
   `APPROVAL-XXXX`, DB-persisted, single-use, 24h TTL).

## 9 worker lanes (`schedule` lib in a daemon thread; APScheduler only runs the vault backup interval)

| # | Lane | Cadence | Does |
|---|---|---|---|
| 1 | Fast Lane | ~2 min | Process approvals + execute queued calls |
| 2 | Lead Hunt | ~60 min | Discover leads (Google Maps + DuckDuckGo + free enrich) |
| 3 | Reply Monitor | ~5 min | Check AgentMail for responses |
| 4 | Cold Escalation | ~30 min | Trigger Retell.ai cold calls on cold leads |
| 5 | Cloud Backup | ~3–6 hr | Back up SQLite to Google Drive |
| 6 | CEO Brief | daily | Operator-voice executive briefing |
| 7 | Health Monitor | ~2 hr | Pipeline health score + alerts (incl. SerpAPI quota at ≥90%) |
| 8 | Self-Improvement | ~6 hr | Wilson-ranked strategy optimization ([[claude-brain]]) |
| 9 | Drip Sequence | ~1 hr | Send pending sequence emails |

Lanes are individually triggerable for testing via
`POST /api/worker/trigger/lane/{1-9}`.

## State & memory

- SQLite (`app/orova.db`) is the single source of truth; Drive backup + Drive-first
  restore survive Render's ephemeral disk.
- Task-scoped memory: sub-agents get relevant summaries, not full history.
- PII/secret scrubbing in the logging pipeline; system traces and outreach data
  live in separate tables.
- The **vault** is the curated human/Claude-readable layer on top — never a DB
  mirror. `scripts/vault_pull.py` pulls leads, briefs, and learned strategies in.

## Linked

- [[claude-brain]] — the LLM routing + learning loop
- [[tech-context]] — runtimes, env vars, constraints
