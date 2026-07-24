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

## 🎯 IDENTITY: HermesClaw is an SDR (owner, 2026-07-14/15 — FINAL)

**HermesClaw's sole purpose is to be the best autonomous AI SDR for OROVA**
(ADR-0006). North-star metric: **booked meetings**. The Electron GUI is archived
out of the repo (`archive/electron-gui` branch); the repo is now
`app/ + knowledge/ + vault/ + mission-control/ + scripts/ + tests/`.
Target architecture: the Pipeline Blackboard (Prospect state machine + unified
event log, ADR-0007 — event log live, additive). Shipped in the Phase-0 batch
(PRs #72–#74 + event log, 2026-07-15): deterministic ICP scoring (replaces the
flat-50 scorer), CSV lead import (`POST /api/leads/import-csv`), repo
subtraction (openclaw_instance/, dead skills, artifacts), GUI archival.
Rejected channels (legal grounds, ADR-0006): LinkedIn automation (ToS), cold
SMS (TCPA). Next in queue: CAN-SPAM footer, Telegram outcome-capture,
dossier v1 (stage-gated), M2 of ADR-0005.

## 🎯 ICP decision — RE-RANKED (owner, 2026-07-24, [[0012-icp-rerank-and-pilot-pricing|ADR-0012]])

**Supersedes the 2026-07-13 "ICP stays MIXED" call.** The mix is now **ranked by
deal economics**, using one filter: *does ONE extra closed deal per month more than
cover the ~$6,500–7,500 all-in monthly cost?*

1. **Custom home builders / high-end remodelers — LEAD** (one $100K+ job grosses
   $20–50K → pays 4–7 months of retainer)
2. **Med spas / aesthetics** (1–2 extra patients/mo covers it; most-proven Meta vertical)
3. **Luxury RE top producers only**

**Exotic/luxury auto → opportunistic only** (economics work, but a $200K buyer
rarely starts on a Meta lead form). `DEFAULT_HUNT_NICHES` re-weighted from **50%
auto** to **~50% homes / 21% med spa / 14% RE / 14% auto** — note the hunt samples
with `random.choice()`, so *entry count is the weighting*.

**Disqualify on sight:** general auto repair (~$400/job → ~16 jobs/mo to break
even) · franchised new-car dealers (OEM co-op mandates) · already under agency contract.

**Pricing:** always quote **ALL-IN ~$6.5–7.5K**; client #1 is a **$1,500–2,000/mo
60-day pilot** that buys a case study, not revenue.

`TARGET_NICHE` is **not set** (owner-confirmed 2026-07-24), so the curated rotation
is live — the generic auto-repair rows in the pipeline are legacy restored data.

> ⚠️ This ranking is inference from deal economics, **not** customer evidence —
> zero prospect conversations have happened. ~20 calls with remodelers settles it.

## 🩹 Positioning — sell the painkiller ([[0013-painkiller-positioning-and-real-competition|ADR-0013]])

**Never sell growth ("more leads") — that's a vitamin, and it loses to Angi's ~$400
price anchor at 16x.** Sell the deadline:

- **Pain A — The Gap:** *"When your crew finishes the job they're on, what's next?"*
  (job wraps in 3 weeks, six W-2 guys burning $30-40K/mo) → **P1 or P2**
- **Pain B — The Wasted Saturday:** *"You'll never drive 40 minutes to a tire-kicker
  again."* (6 dead estimates last month) → **P2 ONLY — P1 makes this pain worse**

**Diagnose before prescribing.** Supersedes profitability-plan §2.2's "always lead
with P1".

**The real enemy is inertia**, not an agency — zero switching cost, worked for 15
years. Only a deadline he already feels beats it (hence: backlog <8 weeks + W-2 crew
on payroll are the hard qualifiers). **Never argue price — change the unit** from
cost-per-lead to cost-per-idle-week-of-payroll.

**One differentiator only:** every lead phoned + AI-qualified in minutes, so he only
drives to real buyers. Never pitch "we're AI-operated", "you're talking to our AI
right now", or "AI creatives" — worthless to the buyer.

## 🔴 THE BLOCKING ACTION (2026-07-24)

**Zero emails have ever been sent. Zero prospect conversations have happened.**
Everything above is inference. The next move is not code:

1. **Call Eric Curran** — West Coast Exotic Cars, +1 844-488-9232, conf 83
   (LinkedIn-corroborated). The free practice rep.
2. **20 remodelers off Google Maps** using the 5 discovery questions in
   `business_context.json` → `discovery_questions`. **Does not require the pipeline.**
3. Bring back the transcripts. ≥8/20 hits = the ICP is real; ≤3 = switch to med spas.

**No further positioning or targeting work before those 20 calls.**

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
