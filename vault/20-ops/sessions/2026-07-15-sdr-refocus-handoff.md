---
name: session-2026-07-15-sdr-refocus-handoff
description: Full handoff after the SDR refocus — read this + the master doc to understand the whole system
type: session
created: 2026-07-15
status: active
---

# HermesClaw / OROVA — SDR Refocus Handoff (2026-07-15)

> **New chat: read this in this order.** (1) `vault/90-docs/HERMESCLAW_OROVA_MASTER.md`
> — the complete system reference. (2) THIS file — what changed in the SDR refocus
> and the current state. (3) `CLAUDE.md`, `vault/10-brain/active-context.md`,
> `vault/40-decisions/0006-*` and `0007-*`. Everything below verified against the
> repo/prod on 2026-07-15.

---

## 0. The one thing that matters

**HermesClaw is now an autonomous AI SDR (ADR-0006).** Its only job: find →
research → qualify → personalize → contact → book meetings for OROVA. North-star
metric = **booked meetings**. The business has **zero paying clients, zero
prospects ever contacted, $0 budget, one founder (Mark)**. The machine is
excellent and heavily instrumented; **the only thing between OROVA and its first
client is a founder action, not code**: set `TARGET_NICHE` on Render (or paste a
CSV) → run a hunt → Mark emails the best 10 from his Gmail. Every new chat should
resist the pull to keep building and push toward that.

## 1. What changed this session (the SDR refocus)

The repo was a sprawling "AI operating system" (agent + Electron desktop GUI +
general assistant). It is now **only the SDR**. Executed as reviewed, merged,
deploy-verified PRs:

| PR | Change | Status |
|---|---|---|
| #66 | Enrichment quality gates (reject junk emails/sentence-fragment names) | live |
| #71 | `HERMESCLAW_OROVA_MASTER.md` (the base system doc) | merged |
| #72 | **Deterministic ICP scorer** (replaced the flat-50) + **CSV lead import** | live |
| #73 | **ADR-0006** + subtraction: `openclaw_instance/`, dead skills, root artifacts | live |
| #74 | **Electron GUI archived out** (487 files → `archive/electron-gui` branch) | live |
| #75 | **Unified event log** (ADR-0007) — the pipeline spine | live |
| #76 | **CAN-SPAM footer** + **`/outcome` Telegram capture** | live |
| #77 | **Dossier v1** — stage-gated deep research feeding the personalizer | live |
| #78 | **Chat-crash fix** — "All AI providers failed" on Telegram messages | live |

Test suite grew **289 → 322**, all green. Every deploy was boot-verified against
the exact exit-3 crash pattern from the prior session (the restore/WAL bug, fixed
in #65 last session — deploys are healthy now).

## 2. The repo now (post-subtraction)

```
app/           # NOVA — the SDR engine (Python/FastAPI, the ONLY deployed code)
knowledge/     # canonical facts + compiler (ADR-0005)
vault/         # the Obsidian brain
mission-control/  # web dashboard served by FastAPI
scripts/  tests/  .claude/skills/sales-intelligence/
```
The Dockerfile copies **only `app/` + `mission-control/`** — so changes to
`vault/`, `knowledge/`, `.claude/`, `scripts/`, `tests/` rebuild a byte-identical
image (zero runtime risk). The Electron GUI is fully preserved on the
`archive/electron-gui` branch — restore = merge that branch.

## 3. The SDR pipeline (Pipeline Blackboard, ADR-0006/0007)

Target model: a **Prospect state machine** where specialized "agents" own single
transitions and communicate through the DB + an append-only event log (built
incrementally, never a rewrite). Current live flow:

```
Scout (hunt SerpAPI-Maps / CSV import)  →  enrich (owner/email/phone)
  →  ICP score (deterministic, HOT≥70/WARM/COLD/SKIP)
  →  [if HOT] Dossier: read their site, extract a REAL verifiable icebreaker
  →  Composer (uses the icebreaker) → QA proofreader → approval gate
  →  Courier: send via AgentMail (+ CAN-SPAM footer)   [approval-gated]
  →  replies → intent classify → booking flow
  →  /outcome (Mark, Telegram): meeting_booked/held/noshow/closed
  ↑  every step writes to the events table (the learning loop's ground truth)
```

### Key new components (files)
- **`app/skills/lead_validator.py::score_lead_icp()`** — deterministic 0-100 score
  on fields enrichment actually collects (owner+25, direct email+25/generic+10,
  phone+10, website+10, luxury signal+20, vertical+10). Replaced the old
  `score_lead()` which returned a flat 50 for every live lead. Wired in
  `worker.py`.
- **`POST /api/leads/import-csv`** (`app/main.py`) — paste any CSV (flexible
  headers), quality-gated + deduped + scored. Dashboard-key gated. **This is the
  fastest path to a first campaign — no SerpAPI/TARGET_NICHE needed.**
- **`app/core/event_log.py`** (ADR-0007) — `events` table + `alog_event` /
  `aget_events` / `handle_outcome_command`. Fail-open (never blocks a send).
  Ensured at startup AND after a Drive restore. Wired: `lead_discovered`
  (hunt + CSV), `outreach_sent` (inside `send_outreach`), `dossier_built`,
  `meeting_*`/`deal_*` (via `/outcome`).
- **`app/skills/dossier.py::build_dossier()`** — stage-gated (score ≥
  `DOSSIER_MIN_SCORE`=70). Fetches ≤3 site pages, one strict never-invent AI pass,
  returns `{icebreaker, observations, premium_signals}`. Feeds the composer via
  `lead["icebreaker"]`. Fail-open.
- **CAN-SPAM** (`agentmail_skill.py::_apply_compliance_footer`) — opt-out line on
  every send; postal address from `BUSINESS_POSTAL_ADDRESS` (owner must set it).
- **`/outcome <lead_id> <booked|held|noshow|closed|lost> [notes]`** — Telegram
  command, intercepted before the brain in `process_telegram_message`.

## 4. The chat-crash fix (#78 — important, subtle)

A Telegram message returned **"All AI providers failed for role 'default'"**. Two
bugs compounded: (1) no-arg tool calls arrive as `arguments='null'` → `None` →
the semantic firewall crashed on `params.items()`; (2) when Groq 400'd, the
Gemini fallback died for the whole request on `Unknown field for Schema:
additionalProperties` (our OpenAI strict-mode tool schemas carry fields Gemini
rejects). Fixed: coerce non-dict args to `{}` at two sites; recursively strip
OpenAI-only schema fields in `_convert_tools_to_gemini`. If you see that error
again: check `/api/logs` for whether Groq itself is erroring vs. the fallbacks.

## 5. Current production state (verified 2026-07-15)

- **Healthy**: `/health` Operational, boots `NOVA Gateway Online`, restores from
  Drive, `[EVENTS] Event log ready`. 0 crash markers. ~7 leads (test data +
  restored).
- **All outbound is approval-gated** (`OUTREACH_AUTOPILOT`/`CALLS_AUTOPILOT`/
  `REPLIES_AUTOPILOT`=0). Mark is away / nothing on autopilot → **nothing sends**.
- **Booked meetings: 0** (no campaign has run — the whole point).

## 6. Open items

### Owner actions (only Mark can do — these unblock revenue)
1. **`TARGET_NICHE` on Render** — stale generic value overrides the good rotation;
   hunts return wrong businesses until fixed. Biggest lead-quality lever. (Or just
   use CSV import and skip it.)
2. **`BUSINESS_POSTAL_ADDRESS`** — registered-agent/PO-box address for full
   CAN-SPAM compliance (emails ship opt-out-only until set).
3. **Rotate `TELEGRAM_BOT_TOKEN`** (leaked, starts `8551361156:`).
4. **Remove invalid `OPENROUTER_API_KEY`** on Render (its 401 masks real errors).
5. **M2 sign-off** — see below (changes what Nova says to prospects → owner call).

### Code backlog (approved direction, needs data or a decision)
- **M2 of ADR-0005**: generate `business_context.json` from canonical facts +
  **elevate positioning** from lead-gen framing to "premium revenue growth" (the
  skill/positioning already say this; business_context still says lead-gen — the
  drift is *detected* by the CI compliance linter but not fixed). Owner-approved
  content change.
- **Coach / learning promotion**: the event log now exists but the Wilson loop
  still reads `outreach_outcomes`; migrate it to read `events` and make its first
  evidence-based promotion — **needs real reply volume first**.
- **Enrichment reliability**: bot-walled dealer sites are flaky (Firecrawl/
  Browserless/Tavily keys are set on Render but success varies).
- **Deliverability**: automated sends from `@agentmail.to` land in spam; Mark's
  Gmail is the client-#1 path. Sending domain is post-revenue.
- **Server-side vault sync** (M3): `vault_pull.py` is manual/laptop-bound; a
  scheduled GitHub Action would close the gap.

## 7. How to work here (conventions that bit us)

- **Branch-first, small PRs, batch merges.** Every merge to `main` redeploys and
  wipes SQLite → survives via Drive restore (working since the #61/#65 fixes).
  **After any merge, watch `/api/logs` for `Restored database snapshot` +
  `NOVA Gateway Online` and zero `malformed`** — a crashed deploy leaves the OLD
  instance serving (it answers `/health` 200 while the new one fails, so 200 is
  NOT proof of a good deploy).
- Tests: `python -m pytest tests -q` (322). Knowledge gate:
  `python scripts/compile_knowledge.py --check`. No more TS/vitest (GUI archived).
- Kilo's advisory review and a 3-second "CodeQL" dynamic stub sometimes show
  red/pending — the real CodeQL analyses (Analyze python/actions/js) are the gate.
- Gemini quota is chronically 429'd; Groq carries the load — don't diagnose that
  as a new bug.
- Subagents have historically died on usage limits — prefer working directly.

## 8. Bottom line for the next chat

The SDR is built, instrumented, and healthy. It can hunt or ingest a CSV, score,
research, personalize, and (on approval) send — logging every step for learning.
It has never contacted a real prospect. **Do not start another architecture
review or big build.** The highest-value action is helping Mark run the first
campaign: fix `TARGET_NICHE` (or import a CSV of West-Coast luxury dealers),
trigger a hunt (`POST /api/actions/hunt-leads`), inspect `/api/leads`, and get him
to email the top 10 from Gmail today. Revenue first; everything else is deferred.

## Linked
- [[hermesclaw-orova-master]] · [[active-context]] · [[0006-sdr-refocus-and-subtraction]] · [[0007-prospect-event-log]] · [[0005-canonical-knowledge-facts-and-projection]]
