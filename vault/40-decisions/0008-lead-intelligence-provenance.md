---
name: 0008-lead-intelligence-provenance
description: Audit verdict on lead intelligence — keep the waterfall, thread provenance through it; every stored contact field carries source + verification
type: decision
created: 2026-07-20
status: active
---

# ADR-0008 — Lead intelligence: provenance over rewrite

## Status
Accepted (owner mandate 2026-07-20: "audit everything from first principles;
delete what doesn't serve the SDR; free tools until first client").

## Audit of the current system (verified against code + a live hunt)

**World-class for a $0 stack:**
- Discovery: SerpAPI Maps / Google Maps / DDG with per-niche queries; the
  2026-07-20 live hunt ("exotic car dealer California") returned real on-ICP
  dealers scored 90/75/65/50 by the deterministic ICP scorer.
- Owner finding (`owner_finder.py`): state-registry waterfall — **CA/WA/OR
  Secretary of State + OpenCorporates** (real officer names from legal
  filings, source-graded 0.7–0.9), cached 30 days, rationed. This is the
  same class of primary-source data ZoomInfo resells.
- Email verification: MX gate → Hunter/Apollo/Tomba/Prospeo → ranked pattern
  guessing → Verifalia deliverability; `email_status` verified/found/guessed.
- Since Phase 0: storage gate (no fabricated data can be stored), boot
  hygiene sweep, computed per-field confidence.

**Mediocre / defective (root causes, all fixed in PR #85):**
1. **Provenance destroyed at three joints.** `resolve_owner` returns
   `{source, confidence}` → `enrich_lead_4step` discarded them → 
   `find_leads_v3`'s output filter dropped any survivors → `save_lead` had
   no columns. A CA-SoS officer name and an AI text-mining guess were
   indistinguishable everywhere downstream. *This, not weak sources, is why
   lead quality felt untrustworthy.*
2. **Guessed emails masqueraded as found.** `enrich_lead_4step`'s
   `_guess_email` fallback returned guesses bare; `light_enrich` stamps
   unlabeled emails `'found'` (confidence 65 instead of 35).
3. **Phones: first-hit-wins, zero corroboration.** Any phone-shaped string
   from any page won; agreement between independent sources wasn't checked.
4. **Dead merge code.** The four "priority" loops in `enrich_lead_4step`
   were copy-paste identical — priority was an illusion.
5. **Double enrichment** (known, deferred): find_leads_v3 crawls each site,
   then worker's `enrich_lead_lite` crawls again. Wasteful, not incorrect.

## Research: why the top platforms produce trustworthy contacts

Principles behind Apollo / Clay / ZoomInfo / Instantly / 11x-class quality
(no scraping of their products — principles only):
- **Waterfall with per-field provider provenance** (Clay's core loop): each
  field records which provider produced it; low-confidence fields re-enter
  the waterfall rather than shipping.
- **Verification before use, not after** (Instantly/Lemlist): an email that
  isn't deliverability-checked is a bounce risk that poisons the domain;
  guessed ≠ found ≠ verified must stay distinct end-to-end.
- **Primary-source anchoring** (ZoomInfo): legal filings, registries, and
  the company's own site outrank third-party aggregation. We already have
  registries — free.
- **Cross-source agreement as verification** (everyone): two independent
  sources agreeing on a phone/email IS the verification signal for fields
  that have no oracle.
- **Confidence is a first-class column** (Clay/11x): displayed, filtered
  on, and used to gate outreach — not an afterthought.

OROVA NOVA can match the *trustworthiness* (not breadth) of these platforms
for its narrow ICP because CA/WA/OR SMBs are exactly the segment where
registry + own-site + Google Business coverage is near-total, and all three
are free.

## Decision

**Keep the existing waterfall architecture.** The sources are right for the
ICP and the price ($0). The defect was plumbing: provenance and verification
signals were produced and then thrown away. Therefore:

1. Thread `{owner_source, email_source, email_status, phone_source,
   phone_verified}` from every producer through `enrich_lead_4step` →
   `find_leads_v3` → `worker` → `save_lead` → `/api/leads` → Mission
   Control. New leads columns (canonical schema + reconciler migrates
   restored snapshots automatically).
2. True priority merge: registry > own site > BBB > Google Business, per
   field, with the winning source recorded.
3. Cross-source phone corroboration: 2+ independent sources agreeing on the
   E.164 number → `phone_verified=1` → confidence 90 (single source: 70).
   Maps phone vs enrichment phone agreement counts.
4. Guessed emails carry `email_status='guessed'` from birth. Never 'found'.
5. Confidence weights consume provenance: registry-sourced owner 85 base
   (cap 95); email 90/65/35 by verification status; phone 90/70/30.

**Rejected alternatives:** full rewrite of the scraping layer (the live
hunt proves discovery + scoring work; rewrite risk > wiring fix), paid
enrichment APIs (violates the $0 constraint until first client).

## Consequences & next steps (priority order)
1. ✅ PR #85 (this ADR): provenance thread + corroboration + confidence.
2. Merge `enrich_lead_4step` + `enrich_lead_lite` into one module — removes
   the double-crawl, halves hunt latency and quota burn (finding 5).
3. Low-confidence re-entry: leads with owner_conf < 60 loop back through
   the remaining strategies before scoring (Clay's re-waterfall pattern).
4. Surface source + confidence in Mission Control lead detail; gate
   autopilot outreach on minimum confidence when autopilot ever turns on.
5. Learning loop: join outcomes (replies/meetings from the events table)
   against per-source confidence to recalibrate the weights with real data.

## Risks
- Registry rationing/caching means owner coverage grows over days, not
  instantly; SerpAPI fallback is score-gated to protect quota.
- BBB/GBP scraping is brittle (fail-open, but coverage varies).
- New columns are write-forward: rows enriched before this ADR carry empty
  sources until re-enriched (the hygiene sweep does not fabricate history).

## Expected improvement
- Every displayed contact now answers "says who?" — the difference between
  a demo and a sales tool.
- Guessed-email inflation eliminated (was: every guess +30 confidence).
- Phone trust becomes graded (90/70/30) instead of binary-and-wrong.
- Zero new spend; zero new services.

## Linked
- [[0006-sdr-refocus-and-subtraction]] · [[session-2026-07-20-phase0-reliability]] · [[hermesclaw-orova-master]]
