---
name: active-context
description: What's happening on OROVA right now — read this first every session
type: brain
created: 2026-07-03
status: active
---

# Active Context

> Session-start file. Read this first (CLAUDE.md rule). Keep it current when the
> direction changes materially.

## ICP decision (owner, 2026-07-13)

**The ICP stays MIXED** — automotive + custom home builders + luxury RE +
high-ticket services, per Mark's explicit call on 2026-07-13. The 07-12
"automotive-only" narrowing proposal is **rejected**; `business_context.json`
and the 15-niche `DEFAULT_HUNT_NICHES` rotation are correct as-is. The one
blocker to on-ICP leads: **`TARGET_NICHE` on Render still holds a stale generic
value that overrides the curated rotation** (confirmed by a live hunt 07-13 —
returned generic auto shops). Owner must delete it or set it deliberately.

## Where things stand (2026-07-10)

Nova is **live on Render free tier** (`orova-nova.onrender.com`), all 9 lanes
green. The lead engine is rebuilt end-to-end: SerpAPI-Maps discovery →
registry/SERP owner-name resolver → single-AI-pass extraction (under the 25s
ceiling) → owner-email finder layer (Tomba/Prospeo/Verifalia — **built, awaiting
keys**). The gate to everything is still **the first paying client**. Test
baseline: **197 Python + 40 TS passing**.

## Deploy/data-loss status (updated 2026-07-13)

**Every merge to `main` still redeploys Render and wipes production SQLite**,
but the Drive backup lane is now **WORKING** — creds were added and the first
`[Vault] Uploaded` was live-verified 2026-07-11. Still: **batch merges** and
check `/api/logs` for the restore line after each deploy.

## Shipped recently (PRs #23–34, 2026-07-06 → 07-10)

- **Owner-email finder layer** (`app/skills/email_finder.py`, PR #32): Tomba
  (25/mo) → Prospeo (75/mo) finders + Verifalia (25/day) HTTP verification of
  pattern-guessed emails (Deliverable → `verified`, all-bounce → dropped).
  Env-gated, SQLite-rationed, fails open. See [[owner-email-finder]].
- **Extraction timeout fix** (PR #29): one AI pass over combined page text
  instead of per-page Groq calls — live-proven (iLusso → owner + direct email).
- **SerpAPI Google Maps discovery** (`_source_serpapi_maps`): business + phone
  (E.164) + website at ~100% on live luxury dealers. Shares the 250/mo quota.
- **WP4 booking funnel**, **approval gates**, **DNC fail-closed gate**,
  **learning loops scheduled** (Lane 8), **dead scraper purge** (−3,270 lines),
  **CI fixed** (Electron E2E + Render deploy), **Sheets restore row-tolerance**
  (PR #34), **SerpAPI quota alert in the health lane** + `_schedule_background`
  log-persistence fix (this session).

## Owner actions (in order — these unblock everything)

1. **Google Drive creds on Render** (`GOOGLE_REFRESH_TOKEN`,
   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) — stops the deploy data loss.
2. **Finder keys** — sign up Tomba/Prospeo/Verifalia **with Nova's AgentMail
   address** (Tomba rejects webmail signups) and set `TOMBA_API_KEY`+
   `TOMBA_SECRET`, `PROSPEO_API_KEY`, `VERIFALIA_USERNAME`/`VERIFALIA_PASSWORD`.
3. **Remove the invalid `OPENROUTER_API_KEY` on Render** (its 401 masks real
   errors as "All providers failed"; Groq+Gemini carry the load — the live
   `/api/chat` path is verified working).
4. `CALENDLY_LINK`/`CAL_COM_EVENT_SLUG` + Cal.com webhook — a HOT reply today
   queues a booking-link reply **with no link configured**.
5. SerpAPI $25/mo — the one paid upgrade worth making pre-revenue (the 250/mo
   free quota is the binding constraint; the health lane now alerts at 90%).

## Code milestone board — ALL SHIPPED (2026-07-10, PRs #32–#42)

Every code milestone on the board is merged, deployed, and live-verified:
`business_context.json` §6 (owner-approved), CEO-brief funnel math
(live-verified in a production brief), ADR-0004 Phases 1 **and** 2
(SkillChallengerEvaluator in Lane 8, no-op until a challenger registers),
mission-control overflow fix (live-verified in the served CSS + preview at
577px/375px), Dependabot criticals (**4 → 0**, GitHub banner confirms),
log-pipeline secret redaction (live-verified: `bot[REDACTED]` in the boot
log), SerpAPI quota alert, and the owner-email finder layer.

**The gate is now entirely the owner env actions above** — nothing on the
code side blocks outreach volume.

## Genuinely-later code work (post-revenue or post-volume)

- Per-client call caps (`MAX_CALLS_PER_DAY` is global — fine at 1 client,
  binds at 3+; profitability-plan §5).
- National DNC registry scrub gate ahead of `trigger_retell_call()`
  (compliance follow-up, needs a paid/free-tier scrub API).
- Deliverability hardening (SPF/DKIM checks) once a sending domain exists.
- ADR-0004 Phase 3 (HermesClaw vault service + Render read-gap decision).
- Remaining Dependabot highs (76, GUI-side, non-critical).

## Standing constraints (don't "fix" these)

$0 pre-revenue · Render free tier: 512 MB, ephemeral disk, no browser, no SMTP
(MX-only verify), 25s enrichment ceiling · `httpx==0.27.2` pinned · TCPA:
**published business lines only, never personal cells** · cold email/calls/
replies approval-gated unless `*_AUTOPILOT=1` · ads/spend always human-approved.

## Linked

- [[project-brief]] · [[business-model]] · [[system-patterns]] · [[claude-brain]]
- [[progress]] — running done/remaining · [[profitability-plan]] — funnel math
- [[session-2026-07-10-handoff]] — full state dump this refresh is based on
