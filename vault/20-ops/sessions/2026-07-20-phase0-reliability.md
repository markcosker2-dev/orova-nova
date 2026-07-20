---
name: session-2026-07-20-phase0-reliability
description: Phase 0 reliability sweep — provider chain fixed + verified, fabricated lead data traced to Sheets restore and gated out
type: session
created: 2026-07-20
status: active
---

# Phase 0 — Reliability Before Features (2026-07-20)

Owner mandate: no new architecture; make the SDR production-trustworthy.
Two PRs: **#81** (merged, deploy-verified) and **#82** (P2/P3-P5 batch).

## P1 — "All AI providers failed … Last error: Unknown" (fixed + verified)

Traced from live `/api/logs`, not guessed. Three compounding causes:

1. **Groq 400 `tool_use_failed`** — model emitted `morning_brief(client_id="OROVA")`
   against an `integer` schema; Groq validates generations server-side and
   rejects the whole request. (Schema description now steers to numeric 0;
   `ceo_brain._coerce_client_id` guards the Gemini path; one Groq retry on
   `tool_use_failed` since it's a bad generation, not an outage.)
2. **Gemini fallback crashed** on `'ChatCompletionMessageToolCall' object has
   no attribute 'get'` — the planner appended raw SDK objects into message
   history; Gemini's converter assumed dicts. Symmetric hazard: Gemini's
   SimpleNamespace tool calls would kill Groq's JSON serialization.
   **Keystone fix: `planner._normalise_tool_calls`** — history holds only
   plain OpenAI-format dicts. Converter also reads defensively now.
3. **"Unknown"** — only Tier-3 ever set `last_error`. Now every tier leaves a
   structured `[AI-FAIL]` record `{request_id, role, provider, model, HTTP
   status, response body}` + stack trace; the terminal message names each
   provider's real failure and a request id for log search.

**Production verification (post-#81):** the ledger immediately showed the
*current* failures are pure free-tier quota exhaustion — Groq 429
RateLimitError + Gemini ResourceExhausted 429 at the same moment, OpenRouter
key removed. Not a code bug; a capacity decision for Mark (see Owner actions).
Also caught worker lanes hammering the 429'd providers 1×/sec → breaker now
covers Tiers 1-2 (PR #82).

## P2 — fabricated Mission Control rows (root-caused + gated)

Prod held exactly 2 leads, both junk, both created the same second:
- the repo's own `make_blueprint/sample_webhook_payload.json` fixture, stored
  verbatim ("Acme Remodeling Co"/"Jane Doe"/+1-555-123-4567/**score 85 from
  the payload**);
- a business-less row whose phone `14047334400` rendered as "Business".

**Ingress: the Sheets restore fallback** (`main.py` cold boot) saved Sheet
rows with zero validation — and the junk lives IN the Sheet/Drive snapshot,
so it re-entered on every deploy. Fixes (defense in depth, PR #82):
- `lead_validator.validate_lead_for_storage` — the single rule set;
- gate wired into `save_lead` (the choke point every ingest path uses);
- `lead_hygiene.quarantine_invalid_leads()` every boot after any restore
  (`status='Invalid'`, excluded from `/api/leads`);
- dashboard: Contact column read `lead.contact` which the API never sends
  (always blank!) → now `lead.owner`; missing values render `—`, never a
  substituted field.

## P3-P7 — mapped to existing machinery (no redesign)

The enrichment stack already had MX gates, Verifalia, email_status
(verified/found/guessed), ranked pattern guessing, owner plausibility,
LinkedIn corroboration, E.164 normalization. What was missing:
- **enforcement at storage time** → the P2 gate;
- **surfaced confidence** → `contact_confidence()` (deterministic, computed,
  never stored): email 90/65/35 by status (generic −15), phone 70 max
  (no verification source exists — never claim more), owner 60 + 20 title
  + 10 LinkedIn. In `/api/leads` + `· NN%` badges in Mission Control.
- **"always ~50" scores** → those were the two fabricated payload scores;
  server-side recompute + hygiene rescore ends payload-score trust entirely.

P6's five stages map: fast enrich = enrich_lead_lite · cross-check =
MX/Verifalia/LinkedIn · confidence = contact_confidence · conflict
resolution = _score_and_select_email · MC validation = gate + sweep + filter.

## Owner actions (unchanged + one new)

1. `TARGET_NICHE` on Render (stale value still the biggest lead-quality lever)
2. `BUSINESS_POSTAL_ADDRESS` for full CAN-SPAM
3. Rotate `TELEGRAM_BOT_TOKEN` (leaked)
4. **Provider capacity**: with OpenRouter removed, Groq+Gemini free tiers
   429 simultaneously under load. Either re-add a WORKING OpenRouter key or
   fund one paid tier — otherwise expect fail-fast "circuit breaker open"
   messages during bursts.
5. **Clean the Leads tab of the Google Sheet** (delete the Acme/no-name test
   rows) — the gate blocks them now, but the Sheet stays dirty.

## Follow-ups (deliberate, not dropped)

- Per-field `*_source` columns (schema change; reconciler makes it cheap).
- `score_lead_icp` credits `website` but not `url` — leads with only `url`
  lose 10 pts.
- Embedding model 404 (`text-embedding-004` deprecated) — semantic firewall
  silently degraded to keyword matching; spawn-task chip filed.
- Firewall blocked a benign `check_replies` for "hey" (goal-alignment 0.00 +
  auto-deny on thin history) — worth a look at thresholds.

## Part 2 — CEO mandate: lead intelligence (same day, PRs #84–#87)

- **First real production hunts ran** ("exotic car dealer California",
  explicit niche via the new hunt-endpoint override): 5 real on-ICP dealers
  land in Mission Control with real phones and domain emails. Nothing was
  emailed — the approval gate held (autopilot off).
- **ADR-0008**: audit verdict — keep the waterfall (registries/site/GBP are
  the right free sources), fix the plumbing that destroyed provenance at
  three joints. Per-field `owner_source`/`email_source`/`phone_source`/
  `phone_verified` now flow discovery → DB → API → UI.
- **Fabrication class found via the live hunt and killed**: scraped sentence
  fragments stored as owners ("THANKS TO", "We Proudly", "Good People") and
  an email fabricated FROM the fake name (thanks@…). One canonical
  `is_plausible_person_name` replaced three divergent copies; the storage
  gate drops implausible owners + derived guessed emails.
- **Cross-source phone verification live**: Maps + website agreement →
  `phone_verified=1` → confidence 90 (3 of 5 leads on the verified rerun).
- **Durability chain fixed after losing the first hunt to a deploy wipe**:
  post-hunt Drive snapshot (PR #86) → surfaced that the **Drive OAuth token
  is expired (invalid_grant, every backup failing silently)** → Sheets-sync
  fallback on Drive failure (PR #87). Scores are honest now (75/60/60/60/50
  — fake-owner points gone).

### Owner actions added
6. **Re-authorize the Google Drive OAuth token on Render** — full-fidelity
   snapshots (learning data + events) are broken until then; leads survive
   via the Sheets fallback only.

## Linked
- [[session-2026-07-15-sdr-refocus-handoff]] · [[0008-lead-intelligence-provenance]] · [[hermesclaw-orova-master]] · [[active-context]]
