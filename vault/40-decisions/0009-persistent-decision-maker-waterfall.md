---
name: 0009-persistent-decision-maker-waterfall
description: Persistent, evidence-accumulating decision-maker waterfall — keep hunting the buyer across sources until confident or exhausted, never fabricate
type: decision
created: 2026-07-20
status: active
---

# ADR-0009 — Persistent decision-maker waterfall

## Status
Accepted (owner mandate 2026-07-20: "maximize the probability of finding the
real decision maker; never give up after the first failure; verify with real
production leads").

## Problem (proven by the live 5 leads)
ADR-0008 made the pipeline *honest* — but honesty is the floor. The first
real hunts produced **0 of 5 decision makers**, while one lead literally
stored `blake@westcoastexoticcars.com` — a human SDR reads "Blake" in
seconds. Root causes:
1. **Gives up after one synchronous pass.** `enrich_lead_4step` fires three
   sources once, takes first-hit, returns. No miss ever triggers another
   attempt.
2. **Ignores evidence already in hand.** No email-local-part → name
   inference existed.
3. **No decision-maker targeting.** It grabs whatever name a page yields; it
   doesn't pursue Owner→Founder→CEO→GM by priority.
4. **Single-source provenance, no cross-referencing.** No "two sources
   agree", no confidence accumulation, no `last_checked`.
5. **Stored leads are frozen** — never re-researched.

## Research → principles borrowed (not products)
How Clay / Apollo / ZoomInfo / Instantly-class tools get trustworthy
contacts, distilled:
- **Waterfall with per-field provider provenance** (Clay): each field records
  which source produced it; weak fields re-enter the waterfall.
- **Cross-source agreement as verification**: two independent sources on the
  same person is stronger than either; a personal email whose local-part
  matches a scraped/registry name *verifies* the email.
- **Primary-source anchoring** (ZoomInfo): legal filings/registries and the
  company's own site outrank third-party guesses.
- **Confidence is first-class**: displayed, filtered, and gate-able.
- **Recognized-name precision**: infer a single first name only when it's a
  known given name — precision over recall protects the never-fabricate rule.

OROVA can out-*trust* these for its narrow CA-luxury ICP because registry +
own-site + Google Business coverage is near-total there, and all are free.

## Decision
New module `app/skills/contact_waterfall.py`: an **ordered source chain that
accumulates evidence** rather than short-circuiting.

```
email-localpart inference → registry(SoS) → team/about/contact pages
→ search-snippet mining  [→ public LinkedIn, socials: staged next]
```

- Each source emits `Evidence{value, confidence, source, method,
  last_checked, title}` into a per-field ledger.
- After every source, `merge_candidates` cross-references: same normalized
  name from N sources → max single-source confidence + (N−1)×15 agreement
  bonus (cap 97); email-localpart matching another source → email verified
  personal (+10).
- Stops early once a candidate clears `CONFIDENCE_STOP`=82, else runs every
  source. Role priority (Owner→…→Ops) breaks ties and labels the title.
- **Never fabricates**: a source unsure contributes nothing; single-token
  first names only when in a recognized-names set (`blake` yes, `jsmith`
  no); business words (`exotics@`) rejected.

Wired three ways:
1. **Hunt-time** (`worker.py`): runs after enrichment, before scoring, so a
   discovered owner earns its ICP +25.
2. **Persistence lane** (`reenrich_stored_leads` + `POST
   /api/actions/reenrich-leads`): re-runs the waterfall on stored
   low-confidence leads, upgrading in place (idempotent, upgrade-only).
3. **Storage + API + UI**: `owner_confidence` + `evidence_json` columns
   (reconciler migrates); `/api/leads` returns the ledger + `icp_reason`;
   Mission Control shows decision maker · title · confidence with a
   "sources used" tooltip and the ICP verdict as the score tooltip.

The storage gate defers to a waterfall-vetted owner (positive
`owner_confidence`) so recognized single first names like "Blake" persist,
while still guarding ungated CSV/Sheets ingest.

**Rejected:** rewriting the scraping layer (sources are right; the gap was
persistence + cross-referencing); paid contact APIs (violates $0-until-first-
client).

## Consequences & next steps (priority order)
1. ✅ This ADR: waterfall + inference + cross-ref + reenrich + ledger + UI.
2. Add public-LinkedIn (`site:linkedin.com/in` via DDG) and
   Facebook/Instagram-bio sources as further waterfall stages — the chain is
   built to append.
3. Low-confidence re-entry loop (Clay's re-waterfall) + a scheduled reenrich
   lane so coverage compounds over days as registries warm.
4. Gate autopilot outreach on a minimum decision-maker confidence.
5. Feed reply/meeting outcomes back to recalibrate per-source confidence.

## Risks
- Recognized-names set trades recall for precision (rare first names miss as
  single-token locals; full `first.last` locals and other sources still
  catch them).
- Website/search sources are network-flaky (fail-open; the waterfall simply
  moves on).
- Re-enrichment is upgrade-only; it never overwrites a stronger registry hit.

## Expected improvement
- Decision-maker coverage on the live 5 goes from **0 → ≥1** immediately
  (Blake), more as registry/team-page sources warm.
- Every decision maker carries a "why we believe this" ledger — the
  difference between a lead list and an SDR dashboard.
- Zero new spend.

## Linked
- [[0008-lead-intelligence-provenance]] · [[0006-sdr-refocus-and-subtraction]] · [[session-2026-07-20-phase0-reliability]]
