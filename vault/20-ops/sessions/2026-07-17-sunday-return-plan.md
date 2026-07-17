---
name: session-2026-07-17-sunday-return-plan
description: Prioritized runbook for Mark's return on Sunday 2026-07-19 — env fixes, first campaign, repo hygiene
type: session
created: 2026-07-17
status: active
---

# Sunday Return Plan (prepared 2026-07-17, Mark back 2026-07-19)

> Prepared while Mark was away. Verified against the repo on 2026-07-17:
> **322 tests passing** (exact documented baseline), **knowledge gate green**
> (`compile_knowledge.py --check` OK), **0 open issues**, **2 open PRs** (#64, #11).
> Production could not be live-verified from this session's container (network
> policy blocks orova-nova.onrender.com) and `vault_pull.py` couldn't run here
> (no `DASHBOARD_API_KEY`/`RENDER_EXTERNAL_URL`) — so **step 0 on Sunday is a
> health check**. Everything else below is from the 07-15 handoff, which was
> prod-verified at the time.

## The one thing that matters (unchanged)

The SDR is built, instrumented, and healthy. It has **never contacted a real
prospect** and there are **0 booked meetings**. Nothing on the code side blocks
outreach. The plan below is ordered so that Sunday ends with **the first 10
personalized emails sent from Mark's Gmail**.

---

## Step 0 — Health check (5 min)

- Open `https://orova-nova.onrender.com/health` → expect Operational.
- Check `/api/logs` for `NOVA Gateway Online`, `Restored database snapshot`,
  `[EVENTS] Event log ready`, zero `malformed`.
- Remember: a 200 on `/health` is NOT proof of a good deploy — the old instance
  keeps serving if a new deploy crashes. The log lines are the real signal.

## Step 1 — Render env fixes (15 min, only Mark can do these)

In priority order:

1. **Rotate `TELEGRAM_BOT_TOKEN`** — the current one (starts `8551361156:`) is
   leaked. Security first. (BotFather → /revoke → new token → update Render.)
2. **Delete or deliberately set `TARGET_NICHE`** — the stale generic value
   overrides the curated 15-niche rotation and is the biggest lead-quality
   lever. If you'll use CSV import (Step 2, option A), deleting it is enough.
3. **Set `BUSINESS_POSTAL_ADDRESS`** — registered-agent / PO-box address so
   every send is fully CAN-SPAM compliant (currently opt-out-only).
4. **Remove the invalid `OPENROUTER_API_KEY`** — its 401 masks real errors as
   "All providers failed".
5. **Set the booking link** — `CALENDLY_LINK` or `CAL_COM_EVENT_SLUG` (+ the
   Cal.com webhook). A HOT reply today would queue a booking reply with no link.
6. *Optional, when ready:* finder keys (Tomba/Prospeo/Verifalia — sign up with
   Nova's AgentMail address, Tomba rejects webmail) and the $25/mo SerpAPI
   upgrade. Neither blocks the first campaign.

## Step 2 — The first campaign (~1 hour, the actual goal)

**Option A — CSV import (fastest, no SerpAPI/`TARGET_NICHE` needed):**
1. Build/paste a CSV of ~25–50 West-Coast luxury/exotic dealers (flexible
   headers are fine) → `POST /api/leads/import-csv` (dashboard-key gated).
2. Pipeline auto-runs: quality gates → dedupe → deterministic ICP score →
   dossier for HOT (≥70) leads.

**Option B — Live hunt (needs `TARGET_NICHE` fixed first):**
1. `POST /api/actions/hunt-leads`, then inspect `/api/leads`.

**Then, either way:**
3. Review the top-scored leads + their dossier icebreakers in mission control
   or `/api/leads`.
4. **Email the best 10 from Gmail personally** — deliverability from
   `@agentmail.to` lands in spam; Mark's Gmail is the client-#1 path.
   (Nova's drafts/icebreakers are the raw material; `/claude` + the
   sales-intelligence skill can QA each message.)
5. Log every outcome via Telegram: `/outcome <lead_id> <booked|held|noshow|closed|lost>`
   — this feeds the events table, which the learning loop will graduate onto.

## Step 3 — Repo hygiene (30 min; Claude can drive, Mark approves merges)

Batch these into ONE merge window (every merge to main redeploys Render):

1. **PR #64** (remove unused `scrapling`, pin `spacy`) — still valid:
   `requirements.txt` is unchanged since it was opened (verified 2026-07-17),
   `scrapling` is still unpinned+unused and `spacy` unpinned. Its original
   premise (stale prod image) is resolved, but the de-risking itself is worth
   merging. Should merge cleanly.
2. **PR #11** (Dependabot: jinja2 3.1.2 → 3.1.6, security) — line still matches
   main; merge alongside #64.
3. After the batch merge: watch `/api/logs` for the restore line + healthy boot
   (Step 0 checklist).

## Step 4 — Decision queue for Mark (no code until decided)

- **M2 of ADR-0005 sign-off**: generate `business_context.json` from canonical
  facts + elevate positioning from "lead-gen" to "premium revenue growth".
  Changes what Nova says to prospects → owner call. The drift is already
  flagged by the CI compliance linter.
- **Autopilot posture**: everything outbound is approval-gated
  (`*_AUTOPILOT=0`). Fine for campaign #1; decide after first sends whether
  replies lane gets autopilot.

## Deferred (correctly — do NOT pull these forward)

- Coach/learning-loop migration to the `events` table — needs real reply volume.
- Deliverability hardening / sending domain — post-revenue.
- Server-side vault sync GitHub Action (M3) — nice-to-have; also note this
  remote container can't run `vault_pull.py` (no creds), which is more evidence
  for M3.
- Per-client call caps, DNC registry scrub, Dependabot highs — per
  [[active-context]].

## Housekeeping noticed this session

- `CLAUDE.md` tells every session to read `vault/10-brain/strategy-snapshot.md`,
  but the file doesn't exist in `10-brain/` (progress.md links it too).
  Presumably `vault_pull.py` creates it — either run the pull on a machine with
  creds, or fix the reference.
- The claude-council plugin commands were not available in this session
  (no provider key configured here) — noted per protocol, proceeded without.

## Linked

- [[session-2026-07-15-sdr-refocus-handoff]] — the state this plan builds on
- [[active-context]] · [[progress]] · [[hermesclaw-orova-master]]
- [[0006-sdr-refocus-and-subtraction]] · [[0007-prospect-event-log]]
