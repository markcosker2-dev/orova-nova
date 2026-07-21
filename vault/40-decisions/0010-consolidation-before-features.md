---
name: 0010-consolidation-before-features
description: One-week consolidation — deploy verification gate, one enrichment module, one scorer, evidence ledger for all contact fields, events wiring — before any new feature
type: decision
created: 2026-07-21
status: proposed
---

# ADR-0010 — Consolidation before features

## Status
Proposed (owner direction 2026-07-21: "stop adding features; make outputs
trustworthy and measurable"). Blocked-start: nothing merges until the
Render deploy pipeline is healthy again and #88 is verified in production.

## Context
Phase 0 + ADR-0008/0009 fixed honesty and added persistence. The remaining
top risk is entropy in the skills layer — duplicate implementations that
make every change harder to validate:
- Three scorers: `score_lead` (legacy, dead), `score_lead_icp` (live),
  `score_lead_for_orova` (apollo path).
- Two enrichment passes double-crawling every lead:
  `enrich_lead_4step` (lead_gen_v3) then `enrich_lead_lite` (light_enrich)
  — documented TODO since 2026-07-15.
- Lead dict shape drift (`owner` vs `owner_name`, `url` vs `website`).
- Evidence ledger exists for OWNER only; email/phone/title still use
  single-value provenance columns.
- Events table exists (ADR-0007) but `enriched`/`qualified` are unlogged
  and the learning loop still reads legacy `outreach_outcomes`.
- "Deploy succeeded" is inferred from HTTP 200 — proven false this week
  (old image served 200 while the #88 image never booted).

What this ADR explicitly does NOT do: rewrite the pipeline, add agents,
add enrichment sources, add AI models. (ADR-0006 "never a rewrite" stands.
The vault/knowledge/ADR layer and the SQLite→Drive→Sheets durability
ladder are deliberate structure, not entropy — they stay.)

## Decision — ordered, each step independently shippable
1. **Deploy verification gate** (smallest, kills the worst failure class):
   bake the git SHA into the image at build (`BUILD_SHA` env or file),
   expose in `/health`; a deploy is "verified" only when the checklist
   passes post-merge: expected SHA in `/health` → expected schema columns
   present → expected endpoints in the route table → one smoke request
   (e.g. `/api/leads`) returns 200 with sane shape. HTTP 200 alone is
   never proof (live-proven 2026-07-21: old image served 200 for hours).
2. **One scorer**: delete `score_lead` (legacy) and fold
   `score_lead_for_orova` into `score_lead_icp` (or delete if its only
   caller is dead). One documented weight table. `score_lead_icp` already
   returns a named component breakdown — that internal modularity is the
   seam for a future "scoring engine"; the engine is NOT extracted until a
   second real module exists (see Deferred).
3. **One enrichment module + data contract**: merge `enrich_lead_4step` +
   `enrich_lead_lite` into a single pass (halves crawl volume and quota
   burn; removes the double-enrichment guard maze). Introduce
   `app/core/contracts.py` with the three types that exist today —
   `Prospect`, `Evidence` (relocated from contact_waterfall), `Event` —
   and migrate the enrichment module + storage gate to them at the
   boundary. Other modules migrate opportunistically; a big-bang
   migration is rewrite-shaped and rejected. This retires
   `owner`/`owner_name`-class drift permanently.
4. **Evidence ledger for every contact field — the data-trust layer**
   (extends ADR-0009): email, phone, and title evidence accumulate exactly
   like owner evidence — per-field arrays in `evidence_json`, never
   overwrite, upgrade-only, confidence from max + agreement. The ledger IS
   the field-as-object trust model: sources/history/conflicts are the
   accumulated entries, `last_checked` lives on each entry, staleness is
   DERIVED from it at read time (never stored). `*_source`/`*_confidence`
   columns become projections of the ledger.
5. **Events wiring + KPI ladder**: log `enriched` and `qualified` events;
   `lead_discovered` payloads carry the raw discovery record (the cheap
   seed that makes future replay possible); migrate the Wilson/learning
   loop to read `events` instead of `outreach_outcomes`. Funnel metric
   endpoint over the full ladder: evidence quality → deliverability →
   replies → positive replies → meetings booked → meetings held → closed
   → revenue. Revenue is the business objective; booked meetings remain
   the optimization target (ADR-0006) — the distinction guards against
   optimizing for junk meetings once autonomy rises.
6. **Stage-tagged observability**: every pipeline log line carries its
   stage (`[STAGE:hunt|enrich|score|gate|send|reply|outcome]`);
   `/api/pipeline/health` summarizes last-N failures per stage so no
   manual log digging is needed.

## Sequencing gates
- Steps 1–6 start only after: Render deploys are green AND #88 verified
  ("Blake" + evidence ledger live on the re-imported 5 leads).
- The revenue learning loop (step 5's payoff) additionally needs real
  sends — the first campaign email precedes any learning claims.

## Rejected
- Full pipeline rewrite / named-agent state machine now (target model
  stays ADR-0006's incremental blackboard; no big-bang).
- New enrichment sources or AI models during the consolidation week.
- LLM-generated lead discovery (hallucination front door — permanently
  rejected; discovery stays SerpAPI/Maps-fed).
- A separate "Data Trust Layer" ADR/abstraction — the per-field evidence
  ledger (step 4) IS the trust model; a parallel layer would duplicate it.
- Contracting types that don't exist in code (Campaign, Organization) —
  contracts codify reality, not aspiration.

## Deferred (with the trigger that un-defers them)
- **Scoring engine extraction** — when a second real scoring module
  exists (e.g. evidence-quality score after step 4), extract the engine;
  today it would be a framework with one plugin.
- **Replay harness** — enrichment re-execution hits live websites (replay
  = re-crawl) and volume is 5 leads on a 250/mo SerpAPI quota. The raw
  discovery payloads captured in step 5 make a true replay system
  buildable later without archaeology; `reenrich_stored_leads` +
  the upgrade-only ledger already provide re-run-and-diff semantics.
- **ADR-0012 "Deterministic AI behavior"** — when real customers exist:
  codify which decisions must be deterministic (discovery, evidence,
  scoring, state transitions) vs probabilistic (drafting, replies), with
  thresholds and approval requirements. Today's de-facto split already
  follows this; the ADR formalizes it when stakes justify it.

## Linked
- [[0009-persistent-decision-maker-waterfall]] · [[0008-lead-intelligence-provenance]] · [[0007-prospect-event-log]] · [[0006-sdr-refocus-and-subtraction]]
