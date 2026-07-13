---
name: progress
description: Running done / remaining list for OROVA
type: brain
created: 2026-07-03
status: active
---

# Progress

## Done

- [x] Nova agent + 9 worker lanes (cron via APScheduler)
- [x] Semantic Firewall + circuit breakers + drift guard + efficiency optimizer
- [x] Telegram HITL approval loop (DB-persisted, single-use)
- [x] Learning loop — Wilson lower-bound ranking, champion/challenger, auto-retire
- [x] Lead engine — Google Maps + DuckDuckGo + free WHOIS/registry/BBB/DNS enrich
- [x] Outreach — AgentMail inbox, personalized composer, A/B subjects, send timing
- [x] Retell cold-call agent (webhook → prod, gpt-4.1-mini, booking → Calendar)
- [x] Mission Control dashboard — structural redesign + all buttons wired
- [x] Auth chain fixed (session tokens validated; "failed to queue" resolved)
- [x] Drive backup + Drive-first restore — creds set on Render, backup verified
      2026-07-11, restore-path crash fixed PR #61 (2026-07-13); prod SQLite now
      survives deploys via the Drive snapshot (see [[active-context]])
- [x] Vault knowledge layer (ADR-0001) + business model captured
- [x] LLM model upgrade — live free models, dead fallbacks removed (PR #19)
- [x] Valid `GROQ_API_KEY` local + Render (2026-07-05); live `/api/chat` verified (07-10)
- [x] SerpAPI-Maps discovery + registry-first owner-name engine (ADR-0003)
- [x] Enrichment extraction fix — one AI pass, fits the 25s ceiling (PR #29)
- [x] Owner-email finder layer — Tomba/Prospeo/Verifalia, env-gated (PR #32)
- [x] Sheets lead-restore row-tolerance (PR #34) + SerpAPI quota health alert

## Remaining / next

- [ ] **Land the first client** — the only thing that unblocks paid tooling
- [ ] **Owner: Google Drive creds on Render** — stops the deploy data loss (top action)
- [ ] **Owner: finder keys** (Tomba/Prospeo/Verifalia via the AgentMail address)
- [ ] Owner: remove invalid `OPENROUTER_API_KEY` on Render; set booking link
- [ ] Apply reviewed `business_context.json` diff ([[profitability-plan]] §6)
- [ ] Deliverability check (mail-tester) on first real send
- [ ] Mission-control visual pass (needs owner's specifics)
- [ ] Higgsfield creative samples for the chosen niche (owner)

## Linked

- [[active-context]] — current state · [[strategy-snapshot]] — what Nova has learned
