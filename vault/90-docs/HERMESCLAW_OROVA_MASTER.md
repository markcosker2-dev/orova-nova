---
name: hermesclaw-orova-master
description: Complete system documentation for HermesClaw / OROVA — hand this to any new chat to understand the whole system
type: doc
created: 2026-07-14
status: active
---

# HermesClaw / OROVA — Master Documentation

> **Purpose of this file.** A single, complete, self-contained explanation of the
> whole system, written so a brand-new chat (with zero prior context) can
> understand it. If you are that new chat: read this top to bottom, then read
> `CLAUDE.md`, `vault/10-brain/active-context.md`, and
> `vault/hermesclaw-orova/STATUS.md`. Everything here was verified against the repo
> on 2026-07-14.

---

## 0. TL;DR (read this first)

- **OROVA** is a one-person, AI-operated **marketing agency** that runs **Meta
  (Facebook/Instagram) ads for luxury/premium businesses on the US West Coast**,
  with **AI lead qualification + appointment setting** as the upsell. Lead vertical
  = **luxury automotive** (dealers, exotic rentals, detailers, wrap/PPF, performance,
  restoration), but the ICP is intentionally **mixed** (also custom-home builders,
  luxury real-estate agents, high-ticket services).
- **Nova** is the autonomous agent that *is* the agency — a Python/FastAPI app on
  Render's free tier (`orova-nova.onrender.com`) that hunts leads, enriches them,
  and (with human approval) does outreach, cold calls, booking, and reporting.
- **HermesClaw** is the umbrella system: Nova + an Electron desktop GUI + an
  Obsidian "brain" (the `vault/`).
- **The single goal: land the first paying client.** There is **no revenue yet.**
  The machine is over-built for its stage; the gap has always been *contacting real
  prospects*, not code.
- **Owner:** Mark. Solo founder, effectively **$0 budget** (can't spend $12 on a
  domain — this is real, not a figure of speech). Pre-revenue go-to-market is:
  the engine finds + enriches leads for free, and **Mark emails the best ones
  manually from his personal Gmail** and calls a few. Domain/deliverability
  automation is post-revenue.

---

## 1. What the three layers are

| Layer | What it is | Where it lives | Runtime |
|---|---|---|---|
| **Nova** | The autonomous lead-gen/outreach agent — the revenue engine | `app/` | Python 3.12 (Docker) on Render free tier |
| **HermesClaw GUI** | Desktop app (OpenClaw-based) — *not* the revenue path | `electron/` + `src/` | Node/TypeScript, Electron |
| **The Brain** | Curated human+AI knowledge base (Obsidian vault) | `vault/` | Markdown; read locally, synced manually |

`HermesClaw/` (capital-H folder) is **reference mirrors only** — canonical GUI code
is in `electron/`. `mission-control/` is a web dashboard served by the FastAPI app.

---

## 2. The business

### Packages & pricing (exact — see `knowledge/facts/company.json`, the canonical source)
- **Package 1 — Meta Lead Gen + Ad Creatives — $4,000/mo.** Meta ads + AI ad
  creatives (Higgsfield AI). Client handles the leads. Tiers: 1-mo $4,000 / 3-mo
  $10,000 / 6-mo $18,000.
- **Package 2 — Lead Gen + AI Qualification + CRM + Appointments — $5,000/mo.**
  P1 plus Retell AI cold-call qualification, CRM kept current, appointment booking.
  Tiers: 1-mo $5,000 / 3-mo $13,000 / 6-mo $24,000.
- **Ad spend is separate** (~$2,000–2,500/mo) and paid by the client **directly to
  Meta** — it never flows through OROVA. ~90% operating margin. Payment via Wise/ACH.
  New clients start a 1-month trial. **No full refunds; no discounts.**

### The differentiator (this is the whole pitch)
> Every other agency emails you *leads to chase*. OROVA hands you **conversations
> with buyers already qualified** — every lead is called and qualified within
> minutes, so you only ever talk to people ready to move. **And you've already seen
> it work — that's exactly how OROVA reached you.** The product demos itself.

### Positioning note (open item)
The Sales Intelligence skill + ADR-0005 push "**premium revenue growth, not lead
generation**," but `business_context.json` is still lead-gen-framed. Elevating the
production copy to match is **M2** (owner-approved change — it changes what Nova says
to prospects). This drift is now *detected* by CI but not yet *fixed*.

### Owner playbook (hard rules — `vault/hermesclaw-orova/playbook/`)
- **Price is the price** (no discounts/freebies). **Past is closed** — zero
  past-client claims, no names/numbers/verticals; **never mention Mark's previous
  agency**, any channel, ever. If asked "am I your first?": *"No — I've signed and
  worked with clients before."*
- **Cadence cap:** 1 email → up to 3 follow-ups (different days) → 1 cold call →
  mark cold, never contact again. **Five touches, ever.** The break-up email must be
  true. No fake urgency.
- **Always escalate:** legal/press, cancellations, refunds, big-name opportunities,
  anything harmful.
- **Tie-break priority:** revenue > certainty > reputation > speed, inside the red
  lines.

---

## 3. Repository map

```
OROVA/  (repo root; the deployed app is here — the HermesClaw/ folder is mirrors)
├── app/                     # NOVA — the production agent (Python/FastAPI)
│   ├── main.py              # FastAPI app + lifespan (startup/shutdown, DB restore)
│   ├── worker.py            # the 9 scheduled worker lanes (the autonomous loop)
│   ├── core/                # 38 modules: database, planner, ai_client, ceo_brain,
│   │                        #   self_improvement, self_learning, pattern_reinforcer,
│   │                        #   approval_gate, business_context.json, soul, etc.
│   └── skills/              # 43 skills: lead_gen_v3, light_enrich, owner_finder,
│                            #   email_finder, agentmail_skill, vault_skill, etc.
├── knowledge/               # NEW (ADR-0005): canonical business facts
│   └── facts/company.json   #   single source of truth for pricing/packages/etc.
├── scripts/                 # compile_knowledge.py, vault_pull.py, deploy helpers
├── vault/                   # THE BRAIN (Obsidian) — see §7
├── mission-control/         # web dashboard served by FastAPI
├── electron/ + src/         # HermesClaw desktop GUI (canonical)
├── HermesClaw/              # reference mirrors only (stale twin of electron/)
├── tests/                   # 289 Python tests (pytest)
├── .claude/skills/          # Claude Skills (sales-intelligence lives here)
├── Dockerfile               # builds the Nova image (Python 3.12-slim)
├── render.yaml              # Render service config (docker runtime, free tier)
├── requirements.txt         # Python deps (lean, for the free-tier image)
└── CLAUDE.md                # project instructions for AI tools (READ THIS)
```

**Legacy / low-value dirs (flagged in the repo audit, not yet cleaned):**
`openclaw_instance/` (abandoned clone; source of 7 orphan git-submodule links that
cause a harmless CI submodule warning), dead skills (`meta_ads_skill.py`,
`scheduler_skill.py`), duplicate root artifacts, and the `HermesClaw/` mirror. Safe
to archive after owner review; none affect the running app.

---

## 4. Nova — the 9 worker lanes (`app/worker.py`)

Nova's autonomy is a scheduler running 9 lanes on intervals:

| Lane | Job | Cadence | What it does |
|---|---|---|---|
| 1 | Fast lane | ~minutes | Checks approvals + pending cold calls |
| 2 | Slow lane (hunt) | ~interval | Hunts new leads (SerpAPI Maps → enrich) |
| 3 | Reply + drip monitor | ~minutes | Watches the inbox, processes drip sequences |
| 4 | Cold escalation | ~interval | Cold (silent) lead → queues the one cold call |
| 5 | Cloud backup | every 3h | Backs SQLite up to Google Drive |
| 6 | CEO morning brief | daily 17:00 UTC | Generates the CEO/exec report |
| 7 | Health check | every 2h | Pipeline health + SerpAPI quota alerts |
| 8 | Self-improvement | every 6h | Wilson champion/challenger strategy tuning |
| 9 | Drip sender | every 1h | Sends scheduled drip-sequence follow-ups |

**All outbound (email, calls, replies) is APPROVAL-GATED** by default
(`app/core/approval_gate.py`, fail-closed) — nothing sends without Mark's Telegram
approval unless an autopilot flag is set (`OUTREACH_AUTOPILOT`, `CALLS_AUTOPILOT`,
`REPLIES_AUTOPILOT` = `1`). Ads/spend/signing are **always** human. Since Mark is
away and nothing is on autopilot, **no outreach currently sends.**

---

## 5. The lead pipeline (end to end) + current state

```
Discovery → Enrichment → Qualification → DB storage → Outreach prep →
Personalization → (AI qualification) → Booking → CRM update → Reporting
```

| Stage | Implementation | State (verified 2026-07-14) |
|---|---|---|
| **Discovery** | SerpAPI Google Maps (`lead_gen_v3._source_serpapi_maps`) → business+phone+website | ✅ works; blocked by stale `TARGET_NICHE` on Render (finds wrong businesses until fixed) |
| **Enrichment** | `light_enrich.enrich_lead_lite` → scrape site + `owner_finder` (name) + `email_finder` (Prospeo, owner email) + phone | ✅ code correct (live-proven: iLusso→Todd Rowsell+email, O'Gara→Darren O'Gara). ⚠️ **flaky**: dealership sites are Cloudflare bot-walled; bypass keys (Firecrawl/Browserless/Tavily) are set on Render but success is inconsistent |
| **Quality gates** | `_is_valid_business_email`, `_is_plausible_name` in `lead_gen_v3` | ✅ **hardened this session** — rejects junk emails (PNG filenames, telemetry) and sentence-fragment names |
| **Storage** | SQLite (`app/core/database.py`) | ✅ works; ephemeral (see §6) |
| **Outreach** | `agentmail_skill.send_outreach` (compose → `email_proofreader` → verify → send from `nova-orova@agentmail.to`) | ⚠️ code works, but sends from a **shared `@agentmail.to` domain → poor deliverability**. Client #1 path = Mark sends manually from Gmail |
| **AI qualification** | Retell AI cold-call agent | ✅ configured (P2 feature) |
| **Booking** | `cal_booking.py` (Calendly/Cal.com/Google Calendar link) | ⚠️ env-gated; booking link likely unset |
| **CRM** | `sheets_sync.py` + `notion_crm.py` (via Make webhook) | ✅ present |
| **Reporting** | `ceo_brain.py` (daily brief, funnel math) | ✅ present |

**Bottom line:** the machine is capable end-to-end; the blockers are **config**
(TARGET_NICHE), **enrichment reliability** (bot walls), and **deliverability** (use
Gmail for client #1) — not missing features.

### Enrichment finders (detail)
- **Owner name:** `owner_finder.py` (registry/SERP resolver) + scraping + AI pass.
- **Owner email:** `email_finder.py` — Prospeo `/enrich-person` (live-verified). Also
  Tomba/Verifalia scaffolding (keys not all set).
- **Phone:** extracted from site + validated to E.164 (`phonenumbers`).
- The whole enrich has a **25-second ceiling** (Render's ~30s request kill).

---

## 6. Deployment & infrastructure (the part that bit us — read carefully)

- **Host:** Render **free tier**, Docker runtime, region Ohio. URL
  `https://orova-nova.onrender.com`. 512MB RAM, **ephemeral disk**, no browser, no
  SMTP, ~25s request ceiling. Free tier spins down on inactivity and cold-starts.
- **Deploy trigger:** every push to `main` redeploys (GitHub `render-deploy.yml`
  pings the Render API; Render also auto-deploys from main). The Dockerfile copies
  **only `app/` + `mission-control/`** into the image — so changes to `vault/`,
  `.claude/`, `knowledge/`, `scripts/`, `tests/` **rebuild a byte-identical image**
  (they can't change runtime behavior).
- **The ephemeral-disk problem:** every deploy wipes the SQLite DB. **Survival =
  Google Drive backup/restore** (`app/skills/vault_skill.py`): Lane 5 backs up every
  3h; on cold boot, `main.py` lifespan restores the latest Drive snapshot (falls
  back to Google Sheets = leads only).
- **CRITICAL history (this session):** the restore had two compounding bugs that
  made **every deploy crash on boot with exit 3**, so Render kept serving a *stale*
  image and no fix went live for ~2 days. Root causes, both now **fixed & live**:
  1. `restore_latest()` called pathlib methods on `DB_PATH` (a `str`) → crash. (PR #61)
  2. The restore *swap* corrupted a *valid* snapshot: the empty DB opened in WAL
     mode left `-wal/-shm` sidecars; overwriting the main `.db` under them corrupted
     it on pool close. Fixed with a clean swap (close pool + clear sidecars before
     write) + snapshot integrity validation + guarded startup that can never exit-3.
     (PR #65, merged & verified live: boots `NOVA Gateway Online`, restores data.)
- **How to verify a deploy:** hit `/health` (should be `Operational`, db ok); check
  `/api/logs` within ~5 min of a deploy for `Restored database snapshot from Drive`
  + `NOVA Gateway Online` and **zero** `malformed` lines.

---

## 7. The knowledge architecture

Knowledge lives in several places; **ADR-0005 (2026-07-14)** defines how they
relate. Read `vault/40-decisions/0005-canonical-knowledge-facts-and-projection.md`.

- **Canonical facts** (`knowledge/facts/company.json`) — the single source of truth
  for **structured facts** (pricing, packages, ICP, compliance). Values reused 2+
  times are one node referenced via `{{ref:path}}` (e.g. the $4k/$5k fee that used
  to live in 7 files is now one node). *(NEW this session, "M1".)*
- **The compiler** (`scripts/compile_knowledge.py`) — build-time (CI, not runtime),
  pure stdlib. Resolves references, **validates + lint-checks** runtime artifacts
  against canonical (fails CI on **pricing drift** or a spam/forbidden phrase in
  outbound copy), and projects a read-only `vault/10-brain/facts.md`. The drift gate
  runs in the normal pytest CI (`tests/test_compile_knowledge.py`).
- **`app/core/business_context.json`** — the structured config Nova reads at runtime
  for messaging (`email_rules`, `outreach`, `retell_pitch`, `value_propositions`,
  `services`). Today it's hand-maintained but **guarded against pricing drift**;
  generating it *from* canonical is **M2**.
- **Obsidian vault** (`vault/`) — the human knowledge base. Per ADR-0005, it
  **projects facts** (read-only `facts.md`) but is the **source for narrative** (ADRs,
  playbook, session notes). See §7.1.
- **Sales Intelligence skill** (`.claude/skills/sales-intelligence/`) — the Claude-
  facing sales *craft* layer (cold email, calls, objections, follow-up, QA,
  luxury-automotive hooks). Loaded natively by Claude agents; *projected* into
  Nova/Retell (not auto-consumed by them).
- **The learning system** writes winning strategies back to canonical facts via PR
  (see §8).

### 7.1 Vault structure (`vault/`)
- `Home.md` — the dashboard/map-of-content (rebuilt this session). **Start here.**
- `10-brain/` — living knowledge: `active-context.md` (read first), `business-model.md`,
  `tech-context.md`, `system-patterns.md`, `roadmap.md`, `progress.md`,
  `strategy-snapshot.md` (auto-synced), `facts.md` (generated), + more.
- `20-ops/sessions/` — session notes (handoffs). `20-ops/briefs/` — CEO briefs.
- `30-leads/` — one note per enriched lead (synced from prod).
- `40-decisions/` — ADRs 0001–0005.
- `hermesclaw-orova/` — the owner's operating system: `playbook/` (how Mark decides),
  `close-kit/` (agreement/invoice/onboarding), `STATUS.md`.
- `_templates/` — note templates. **Never edit `vault/.obsidian/`.**
- **Frontmatter is required on every note:** `name`, `description`,
  `type` (brain|lead|brief|decision|session|doc), `created`, `status`.

### 7.2 The knowledge-sync gap (important, unsolved)
Knowledge sync is **manual and laptop-dependent**: `scripts/vault_pull.py` pulls
production learning (leads, briefs, strategies, skill-health, improvement-log) into
the vault, but it has **no cron/CI caller** — it only runs when Mark runs it locally.
**Production never touches the vault** (the Dockerfile doesn't copy `vault/`;
`vault_context.py` self-documents "on Render, VAULT_DIR won't exist"). So when the
laptop is off, the vault goes stale (learning is *not lost* — it's in SQLite + Drive
— but the human view doesn't update). **Recommended fix (M3):** a scheduled GitHub
Action runs `vault_pull.py` + commits, laptop-independent.

---

## 8. The learning system

Three subsystems exist (see ADR-0004 for the full map):
- **Strategy optimizer / champion-challenger** (`app/core/self_improvement.py`,
  Lane 8, every 6h): Wilson lower-bound ranking over `outreach_outcomes` /
  `learned_strategies`. Email frameworks (BAB/PAS/AIDA) compete; winners promoted,
  losers auto-retired. **Currently 0-sample** (no real outreach volume yet).
- **Self-learning loop** (`app/core/self_learning.py`): execution traces →
  learned skills. Partially wired (`run_cycle()` not scheduled — see ADR-0004).
- **Pattern reinforcer** (`app/core/pattern_reinforcer.py`): runs once at boot.

**How it should flow (ADR-0005):** outcomes → Wilson promotes a variant → proposed
as a **PR to `knowledge/facts/`** → CI + compliance linter + human review gate it →
recompile → all runtimes get it. North-star metric = **booked meetings**. This keeps
one write target (no drift) and requires evidence + a gate (stability).

---

## 9. LLM stack & key integrations

- **LLM routing** (`app/core/ai_client.py`): tier 1 **Groq** (`llama-3.3-70b`,
  tool-calling) → tier 2 **Gemini 2.5-flash** → tier 3 OpenRouter. **Note:** Gemini's
  free-tier quota is frequently **exhausted (429s)** — Groq carries the load. The
  Retell voice agent runs on gpt-4.1-mini.
- **Integrations:** SerpAPI (discovery, 250/mo shared quota), Prospeo (owner email),
  AgentMail (email send/inbox, `nova-orova@agentmail.to`), Retell.ai (cold calls,
  number +1 716 670 3920), Google Drive (backup, service-account/OAuth), Google
  Sheets (fallback + CRM), Firecrawl/Browserless/Tavily (bot-wall bypass), Telegram
  (approvals + alerts).

---

## 10. Conventions & rules (for any AI working here)

- **`CLAUDE.md` is binding.** Highlights: consult the **claude-council** for
  architecture/hard calls; a stop-gate reviews uncommitted diffs at end of turn;
  the vault is the shared brain — run `python scripts/vault_pull.py` at session
  start on product/strategy work, then read `active-context.md` + `strategy-snapshot.md`.
- **Git:** branch-first (never commit straight to `main`); small PRs; commits end with
  `Co-Authored-By: Claude …`. Every merge to `main` = a production deploy → batch
  merges, verify the restore line after.
- **Docs go in `vault/90-docs/`** (this file is there). Root keeps only
  README/SECURITY/PRIVACY/TERMS. Never create a folder named `docs` (gitignored).
- **Compliance:** TCPA (business lines only), CA bot-disclosure (voice agent
  discloses AI when asked), ad spend/signing/publishing always human-approved.
- **Testing:** `python -m pytest tests -q` (289 tests). TS: `npx vitest run`.
  Typecheck: `pnpm typecheck`. Knowledge gate: `python scripts/compile_knowledge.py --check`.
- **`httpx` pinned at `0.27.2`** (starlette TestClient vs mcp/ollama constraints).

---

## 11. Current state (verified 2026-07-14)

**Healthy / working:**
- Production is **Operational** (`/health` ok), boots clean, restores data from Drive.
- The deploy crash (exit 3) is **fixed and live**. Deploys now boot successfully.
- Enrichment code is correct; quality gates hardened (no more junk emails/names).
- Knowledge drift gate is live in CI (pricing/positioning can't silently diverge).
- Test suite green (289 collected).

**Open / broken / not-yet-done:**
- **`TARGET_NICHE` on Render is stale** → hunts find wrong-region/wrong-type
  businesses. **Only Mark can fix this** (Render env var). Biggest lead-quality lever.
- **Enrichment reliability** on bot-walled dealership sites is inconsistent.
- **Deliverability**: automated send is `@agentmail.to` (spammy) — use Gmail for
  client #1.
- **Positioning drift** (lead-gen vs revenue-growth) detected but not fixed — M2.
- **Knowledge sync** is manual/laptop-bound — M3.
- **Leaked `TELEGRAM_BOT_TOKEN`** (starts `8551361156:`) still needs rotating.
- **Never contacted a real prospect.** No revenue.

---

## 12. Environment variables (Render)

**Working/set:** `GROQ_API_KEY`, `GOOGLE_API_KEY` (Gemini), `DASHBOARD_API_KEY`,
`AGENTMAIL_API_KEY`, `SERPAPI_KEY`, `PROSPEO_API_KEY`, Google Drive trio
(`GOOGLE_REFRESH_TOKEN`/`CLIENT_ID`/`CLIENT_SECRET`) **or** `GOOGLE_CREDENTIALS_JSON`,
`RETELL_API_KEY`/`RETELL_FROM_NUMBER`, `FIRECRAWL_API_KEY`, `BROWSERLESS_API_KEY`,
`TAVILY_API_KEY`, `RENDER_EXTERNAL_URL`, `TELEGRAM_BOT_TOKEN` (+ chat IDs).

**Action needed:** set/clear **`TARGET_NICHE`** (stale — biggest lever); **rotate
`TELEGRAM_BOT_TOKEN`** (leaked); remove the invalid `OPENROUTER_API_KEY` (its 401
masks real errors); booking link (`CALENDLY_LINK`/`CAL_COM_EVENT_SLUG`) if using
auto-booking. Prospeo/Tomba/Verifalia finder keys partially set.

`.env` locally holds `RENDER_EXTERNAL_URL` + `DASHBOARD_API_KEY` (for `vault_pull.py`
and prod API calls). Firecrawl/Browserless/Tavily/Apollo keys are **not** in the
local `.env` (so local enrichment understates production).

---

## 13. How the next chat should start

1. Read this file, then `CLAUDE.md`, `vault/10-brain/active-context.md`,
   `vault/hermesclaw-orova/STATUS.md`.
2. `python scripts/vault_pull.py` (needs `RENDER_EXTERNAL_URL` + `DASHBOARD_API_KEY`
   in `.env`) to pull the latest production learning.
3. Verify prod: `GET /health` and `/api/logs` (look for `NOVA Gateway Online`, no
   `malformed`). Leads: `GET /api/leads` with header `X-API-Key: <DASHBOARD_API_KEY>`.
4. Run tests before/after changes: `python -m pytest tests -q`.
5. **The highest-value work is not code** — it's getting Mark real, on-ICP,
   enriched leads to email from Gmail. That path: fix `TARGET_NICHE` → run a hunt
   (`POST /api/actions/hunt-leads`) → inspect `/api/leads` → Mark emails the best 10.

---

## 14. What shipped in the 2026-07-13/14 session (context for continuity)

- **PR #60** — junk-email subdomain filter (first pass).
- **PR #61** — Drive restore `str`-vs-`Path` crash fix.
- **PR #62** — ESLint-10 flat config + `undici`/jsdom CI fix (restored the Check job).
- **PR #65** — **the deploy-crash fix** (corrupt/WAL-mismatched restore → exit 3).
  *This is why deploys work again.* Merged & live-verified.
- **PR #66** — enrichment quality: reject junk scraped emails + sentence-fragment
  owner names (13 tests). Live.
- **PR #63/#67** — vault: corrected stale backup claims + rebuilt `Home.md` dashboard.
- **PR #68** — the **Sales Intelligence skill pack** (`.claude/skills/`), reconciled
  against Anthropic Skills best-practices + Gong cold-call data.
- **PR #69** — **ADR-0005** (canonical knowledge architecture decision).
- **PR #70** — **M1**: canonical facts + `compile_knowledge.py` + drift/compliance CI
  gate. Live.
- All merged to `main`; production consolidated, redeployed, and verified healthy.

**Deferred by design:** M2 (generate `business_context.json` from canonical + elevate
positioning — owner-approved), M3 (server-side vault sync), repo cleanup
(`openclaw_instance/` archive, dead skills), enrichment bot-wall reliability.

---

## 15. Known risks & gotchas (don't relearn these the hard way)

- **Every merge to `main` redeploys and wipes SQLite.** Data survives via Drive
  restore (now working) — but anything newer than the last 3h backup is lost. Batch
  merges; verify the restore line.
- **Production may serve a stale image if a deploy crashes on boot** — always verify
  `NOVA Gateway Online` after a deploy, not just that `/health` returns 200 (the old
  instance answers 200 while the new one fails).
- **Gemini quota (429) is often exhausted** — don't diagnose it as a bug; Groq covers.
- **The vault is not in the Docker image** — Nova never reads it in production.
- **`vault_skill.py` is the Drive-backup system, not the Obsidian vault** (naming
  collision).
- **Local enrichment understates production** (Firecrawl/Browserless/Tavily keys are
  Render-only).
- **Subagents historically died on usage limits** — prefer working directly.
- **The council plugin needs a provider key**; Gemini (the only one configured) is
  quota-limited, so external council cross-checks often return empty.
