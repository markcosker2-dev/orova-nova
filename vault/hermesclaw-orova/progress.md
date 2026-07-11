---
name: hermesclaw-orova-progress
description: Project diary — dated log of what happened, what changed, what's next
type: doc
created: 2026-07-11
status: active
---

# Progress Diary

> Append-only. Newest entry first. One entry per working day/session.

## 2026-07-11 — Keys activation + Drive backup last mile

- **Happened:** Mark supplied the Prospeo key. Live smoke test immediately
  caught a production bug — Prospeo had **deprecated** the `/email-finder`
  endpoint our code targeted (silent no-op on every lead). Rewired to
  `/enrich-person`, verified end-to-end against ground truth (iLusso →
  `todd@ilusso.com`, VERIFIED); free tier is actually **100 credits/mo**
  (PR #44). Key set on Render.
- Drive backup saga: wired `GOOGLE_CREDENTIALS_JSON` (the existing Sheets
  credential) into the Drive path (PR #45) — restore now *connects*, but
  live test proved Google's hard rule: **service accounts cannot upload**
  (403 storageQuotaExceeded). Built the one-time OAuth helper
  `scripts/get_google_refresh_token.py` (PR #46). Client ID + secret exist;
  **refresh token still pending** — the current blocker.
- Env cleanup: identified the real "401 User not found" source
  (`OPENAI_API_KEY`+`OPENAI_BASE_URL` feeding a dead fallback tier — there
  was never an OPENROUTER key on Render) and five dead vars; Mark deleted
  them. AgentMail key retrieved for Mark from local .env.
- Vault: created this project folder (README/STATUS/progress/decision).
  Started the owner-decision interview → `playbook/`.
- **Next:** refresh token on Render → verified backup/restore cycle → then
  outreach volume.

## 2026-07-10 — The big shipping day (PRs #35–#43)

- **All remaining code milestones shipped and live-verified**: log-pipeline
  secret redaction (Telegram bot token had leaked into the dashboard-readable
  buffer — root logger BufferHandler, no scrubbing existed); SerpAPI quota
  alert in the health lane (90% threshold, month-debounced); `_schedule_
  background` fix (state writes were silently dropped + cross-thread
  create_task); CEO brief funnel-math section (7d vs prior-7d conversion vs
  benchmark bands — verified in a real production brief); owner-approved
  `business_context.json` §6 edits (ICP narrowed: aviation/yacht →
  opportunistic-only; margin corrected to 90%+; P1-first framing; TCPA
  calling policy codified) + hunt rotation to match; ADR-0004 Phase 1
  (vault-context injection, skill-outcome tracking, improvement changelog,
  `/api/skill_health`) **and** Phase 2 (SkillChallengerEvaluator in Lane 8);
  Dependabot criticals **4 → 0** (openclaw 2026.4.29, baileys 7.0.0-rc12);
  mission-control overflow fix (agent strip contained, verified at 577px +
  375px). Suite 187 → 243.
- Executive audits instituted; brain docs fully reconciled with reality.

## 2026-07-06 → 07-09 — Owner-email finder + data-loss discoveries (PRs #32–#34)

- Built the owner-email finder layer (`email_finder.py`): Tomba/Prospeo
  finders + Verifalia guess-verification, env-gated, SQLite-rationed,
  fail-open (PR #32). Tomba/Verifalia signups blocked (webmail/disposable
  email) — Prospeo alone suffices.
- **Discovered production data loss**: every merge redeploys Render, wiping
  SQLite; Drive restore dead (no creds) AND the Sheets fallback crashed on
  one malformed row (`int('lead_12345')`) → fixed with per-row tolerance
  (PR #34), verified: "Restored 4 leads" on every boot since.
- Earlier (07-08): enrichment extraction rewrite — one AI pass under the 25s
  ceiling, live-proven on iLusso (PR #29 era).

## 2026-07-04 → 07-05 — Lead engine foundations

- WP1–WP4: CEO auto-hunt fix, owner-page-first scraping, real sub-agents,
  approval gates + reply→booking funnel with Cal.com webhook.
- Owner-name engine (ADR-0003): registry-first resolver; live verification
  showed free registries are dead ends (WA anti-bot, OpenCorporates
  non-commercial, CA paid) — **SerpAPI is the real free source**.
- Discovery overhaul: SerpAPI Google-Maps engine replaced broken DDG/HTML
  scraping — business+phone+website at ~100% on live luxury dealers.
- Deep research sessions: owner-contact reality (email finders, TCPA/DNC),
  profitability plan (funnel math, 97% margins, ICP narrowing proposal).

## 2026-07-03 — Vault + brain bootstrapping

- Obsidian vault adopted as the shared brain (ADR-0001); brain notes written;
  `vault_pull.py` learning bridge. LLM stack repaired (retired OpenRouter
  models were 404ing); dashboard redesign; Retell agent live.
