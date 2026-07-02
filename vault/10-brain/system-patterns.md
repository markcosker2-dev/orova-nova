# System Patterns

## Split-Brain Architecture
- **OpenClaw (Node.js)** — Sensory-motor layer: WebSocket gateway, channel management, TypeBox schema validation
- **Hermes Agent (Python 3.11)** — Cognitive kernel: planning, memory, self-improvement, tool execution

## Communication Protocol
- Engine-to-gateway: MCP (Model Context Protocol) or TypeBox-validated JSON-RPC over WebSockets
- Every WebSocket frame must match OpenClaw's TypeBox schemas
- AJV compilers validate payloads; undeclared fields are rejected

## Agent Execution Pattern
1. Nova receives goal → scopes tools via `_scope_tools()`
2. Semantic Firewall validates tool calls before execution
3. Circuit breaker prevents runaway execution
4. Efficiency optimizer caches results to reduce redundant calls
5. Drift guard monitors for goal deviation

## 9 Worker Lanes (Cron Schedule)
1. Fast Lane (2min) — Approvals + execute calls
2. Lead Hunt (60min) — Multi-tier lead discovery
3. Reply Monitor (5min) — Check AgentMail for responses
4. Cold Escalation (30min) — Auto-trigger RetellAI calls
5. Cloud Backup (6hr) — Google Drive database backup
6. CEO Brief (daily 17:00 PST) — Morning executive briefing
7. Health Monitor (2hr) — Pipeline health scoring
8. Self-Improvement (6hr) — Strategy optimization loop
9. Drip Sequence (1hr) — Send pending sequence emails

## Memory Isolation
- Task-scoped memory: sub-agents receive relevant summaries, not full history
- PII/Secret scrubbing in logging pipeline
- Separate SQLite tables for system traces vs. outreach data