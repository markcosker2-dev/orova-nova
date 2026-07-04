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

1. **Set ONE live LLM key on Render** — the #1 blocker. All three are dead (Groq
   401, OpenRouter 401, Google empty). Cheapest: fresh free key from
   openrouter.ai/keys → Render env `OPENROUTER_API_KEY`. *Nothing AI works until
   this is done.*
2. **Merge [PR #21]** (bundles model IDs + vault brain + WP1–WP4). Close #19/#20.
3. **`DASHBOARD_API_KEY`** in local `.env` (for vault sync).
4. **Sending domain + SPF/DKIM** (e.g. getorova.com) — biggest deliverability lever.
5. **Meta app creds** (`META_ACCESS_TOKEN/APP_ID/APP_SECRET`) — to run client ads.
6. **Higgsfield account** + **Stripe/Wise invoicing** + a **one-page site**.
7. When outreach is proven good, flip `OUTREACH_AUTOPILOT=1` / `CALLS_AUTOPILOT=1`
   on Render to let Nova send without approval.

## 🟡 Claude (next code sessions — in priority order)

1. **WP4 remainder — the funnel middle-mile**: reply → qualify → **calendar
   booking**. When a hot reply lands, auto-progress to a booking link + create the
   Google Calendar event (reuse `calendar_skill`), instead of stopping at a
   Telegram alert. (Approval gates for email/calls are already done.)
2. **Higgsfield ↔ Claude ad-creation flow** — generate lead-gen ad creatives and
   stage them (behind the always-on ad approval gate).
3. **Verify the lead engine live** once a key is set — run a real hunt, confirm
   `/api/leads` shows populated owner/email/phone.
4. **Deliverability hardening** — once the domain exists, wire SPF/DKIM checks.
5. **CRM sync** — Make.com scenario for HubSpot / GoHighLevel when a client uses one.

## 🟢 Nova (runs autonomously once a key + approval are set)

Hunt (Google Maps + web enrichment) → score → **request approval** → send cold
email → if no reply, **request approval** → cold call → book with Mark. Learns
which frameworks/subject lines/timing win (Wilson champion/challenger) and the
CEO brief proposes daily actions.

## Later (after first revenue)

Paid tooling (Anthropic, enrichment/verification, Render paid tier) · autopilot
on · multi-client scaling · real subagent parallelism.
