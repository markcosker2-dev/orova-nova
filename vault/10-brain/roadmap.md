---
name: roadmap
description: What to execute next — split by Mark / Claude / Nova
type: brain
created: 2026-07-04
status: active
---

# OROVA Roadmap

The single goal right now: **land the first paying client.** Everything below
serves that. Split by who does it. See [[orova-playbook]] for the business detail
and [[active-context]] for current state.

## 🔴 Mark (owner-only — these unblock everything)

1. **Set ONE FREE LLM key on Render** — the #1 blocker. All three are dead (Groq
   401, OpenRouter 401, Google empty). Use a **free tier** — easiest is Groq:
   console.groq.com → API Keys → set Render env `GROQ_API_KEY` (free, no card,
   supports tool-calling). Or Google AI Studio (`GOOGLE_API_KEY`) / OpenRouter
   free models (`OPENROUTER_API_KEY`). *Nothing AI works until this is done.*
2. ~~Merge PR #21~~ ✅ **done 2026-07-04** — merged to main, #19/#20 resolved,
   Render auto-deploys from main.
3. **`DASHBOARD_API_KEY`** in local `.env` (for vault sync).
4. **Sending domain + SPF/DKIM** (e.g. getorova.com) — biggest deliverability lever.
5. **Meta app creds** (`META_ACCESS_TOKEN/APP_ID/APP_SECRET`) — to run client ads.
6. **Higgsfield account** + **Stripe/Wise invoicing** + a **one-page site**.
7. When outreach is proven good, flip `OUTREACH_AUTOPILOT=1` / `CALLS_AUTOPILOT=1`
   on Render to let Nova send without approval. New in WP4-remainder:
   `REPLIES_AUTOPILOT=1` lets Nova auto-send the booking-link reply to HOT leads
   without approval (own flag — lower risk than cold outreach).
8. **Cal.com/Calendly booking link + webhook** — set `CALENDLY_LINK` (or
   `CAL_COM_EVENT_SLUG` / `GOOGLE_CALENDAR_BOOKING_LINK`) so the booking-link reply
   isn't empty, and point Cal.com's webhook at `POST /api/cal/webhook` with
   `CAL_WEBHOOK_SECRET` set. Calendar event creation also needs the Google
   Calendar OAuth token (`app/credentials/calendar_token.json`).
9. **Owner-name engine keys (optional, free)** — WA SoS works with NO key. To widen
   coverage: `OPENCORPORATES_API_KEY` (free, 50/day), `SERPAPI_KEY` (free, 250/mo),
   and `CA_SOS_API_KEY` only if the CA CALICO free tier is confirmed. Engine no-ops
   safely without them. See [[0003-owner-name-first-lead-engine]].

## 🟡 Claude (next code sessions — in priority order)

1. ~~**WP4 remainder — the funnel middle-mile**~~ ✅ **done 2026-07-04**: reply →
   classify (HOT/WARM/COLD) → qualify (lead lookup) → auto-progress HOT replies to
   a booking-link reply (approval-gated, durable queue) instead of stopping at a
   Telegram alert; Cal.com webhook (`/api/cal/webhook`) now creates the Google
   Calendar event on booking. See [[session-2026-07-04-wp4-booking-funnel]].
   Degrades gracefully with no LLM key (keyword classifier) / no booking link.
2. **Higgsfield ↔ Claude ad-creation flow** — generate lead-gen ad creatives and
   stage them (behind the always-on ad approval gate).
3. **Verify the owner-name engine live** (built 2026-07-04, [[0003-owner-name-first-lead-engine]]).
   The registry clients (`app/skills/owner_finder.py`) are wired but their live
   request shapes are unverified — validate WA SoS FIRST (it's keyless), then
   confirm the CA/OpenCorporates/SerpAPI shapes once keys exist; run a real hunt and
   confirm `/api/leads` shows populated owner names. Then verify the booking funnel
   end-to-end once a booking link + calendar OAuth exist.
4. **Deliverability hardening** — once the domain exists, wire SPF/DKIM checks.
5. **CRM sync** — Make.com scenario for HubSpot / GoHighLevel when a client uses one.
6. **Scoped removal of dead scraper modules** — `lead_gen_v2`, `lead_finder`,
   `smart_scraper`, `scrapling_scraper`, `apollo_free_scraper`, `apollo_scraper/`,
   `crawl_skill`, `browser_use_skill`, `mem0_skill` are unused/broken on Render but
   wired into `planner`/`pipeline`/`ceo_brain`/`competitive_intel`/`deep_research`/tests
   — removal needs its own careful pass (unwire refs + retest), not a delete.

## 🟢 Nova (runs autonomously once a key + approval are set)

Hunt (Google Maps + web enrichment) → score → **request approval** → send cold
email → if no reply, **request approval** → cold call → book with Mark. Learns
which frameworks/subject lines/timing win (Wilson champion/challenger) and the
CEO brief proposes daily actions.

## Later (after first revenue)

Paid tooling (Anthropic, enrichment/verification, Render paid tier) · autopilot
on · multi-client scaling · real subagent parallelism.
