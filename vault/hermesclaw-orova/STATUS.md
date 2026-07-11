---
name: hermesclaw-orova-status
description: Current snapshot — where the project stands, next action, blockers
type: doc
created: 2026-07-11
status: active
---

# STATUS — 2026-07-11

> Live snapshot. Update whenever the state changes materially.

## Where the project stands

Production is **Operational** (orova-nova.onrender.com — db ok, memory ok).
**Every code milestone is shipped and live-verified** (PRs #32–#46): the full
funnel — SerpAPI-Maps discovery → owner-name resolver → Prospeo owner-email
finder (live-proven: iLusso → todd@ilusso.com, VERIFIED) → approval-gated
outreach → HOT-reply booking flow → daily CEO brief with funnel conversion
math. Learning machinery (ADR-0004 Phases 1+2) is scheduled and waiting on
volume. Tests: 248 Python + 40 TS passing.

**The gate to outreach volume is env/owner work, not code.**

## ⏭️ NEXT ACTION (single most important)

**Finish `GOOGLE_REFRESH_TOKEN` on Render** — the last mile of the Drive
backup fix. Verified live 2026-07-11: the service account connects to Drive
but *cannot upload* (Google 403: service accounts have no storage quota), so
until the OAuth trio is complete, **every deploy wipes all learning data**
(leads survive via Sheets; strategy win-rates / skill outcomes do not).

How: run `python scripts/get_google_refresh_token.py` locally (or use the
consent-link flow from chat), approve in the browser, set
`GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` + `GOOGLE_REFRESH_TOKEN` on
Render. Claude then verifies the first `[Vault] Uploaded →` line and the
next boot's full-fidelity restore.

## Blockers (all owner-side, in value order)

1. `GOOGLE_REFRESH_TOKEN` — see next action above. **Blocks learning.**
2. Confirm `AGENTMAIL_API_KEY` is set on Render — **blocks all cold email.**
3. Booking link (`CALENDLY_LINK` or `CAL_COM_EVENT_SLUG` + `CAL_WEBHOOK_SECRET`)
   — a HOT reply today gets a booking message **with no link in it.**
4. Rotate `TELEGRAM_BOT_TOKEN` via BotFather — old value leaked to logs
   before the redaction fix (2026-07-10); scrubbing can't un-leak history.
5. Later: sending domain + SPF/DKIM (deliverability), SerpAPI $25/mo
   (removes the 250/mo discovery ceiling — health lane alerts at 90%).

## Needs review

- Prospeo free key is in chat transcripts — rotate from prospeo.io when
  convenient (low urgency, free-tier key).
- ✅ Owner playbook COMPLETE (2026-07-11, 11-question interview) —
  `playbook/` has 6 skill files; outreach copy + `business_context.json`
  brought into conformance (past-client claims removed, cadence capped at
  1+3+call, 5th drip email deleted). Mark: skim the playbook files and
  correct anything that reads wrong.
- ✅ claude-council INSTALLED & LIVE (2026-07-11): smoke-tested against
  Gemini (gemini-2.5-flash), stop-gate armed, CLAUDE.md mandate written —
  Claude convenes it on significant calls from next session onward.
- Plugin decision still pending: **obsidian-second-brain** — commands-only,
  full (its agents auto-rewrite the vault), or skip? (kepano skills installed;
  obsidian-mind recommended skip.)

## Env facts (verified 2026-07-11)

Dead keys deleted (OPENAI_API_KEY/BASE_URL — the "401 User not found"
source — plus COMPOSIO/MIMO/SGAI/OROVA_API_KEY/CRON_SECRET). LLM chain:
Groq (primary) + Gemini; no tier-3. `PROSPEO_API_KEY` live on Render.
`GOOGLE_CREDENTIALS_JSON` stays (Sheets + Drive read).
