---
name: 0003-owner-name-first-lead-engine
description: Resolve owner names from free public registries before scraping websites
type: decision
created: 2026-07-04
status: active
---

# ADR-0003 — Owner-name-first lead engine (free public-records enrichment)

## Context

The old pipeline (`lead_gen_v3.find_leads_v3` → `light_enrich`) resolved a lead's
owner name by AI-scraping the business website's /about,/team pages. Yield is low:
most SMB sites don't publish the owner, and it depends on an LLM key that is
currently dead. Mark wants Apollo-like results — reliable owner/decision-maker
names — but on the project's $0, Render-free-tier constraints (HTTP only, no
browser, 512 MB, httpx pinned 0.27.2). Two read-only research agents produced
[[lead-engine-research]] (source audit + ranking) and [[skill-health-audit]].

Decision fork (Mark chose): **free public-records pipeline**, not a paid provider.

## Decision

New module `app/skills/owner_finder.py` — `resolve_owner(business, state, domain,
score)` with a registry-FIRST fallback chain, each stage wrapped so it never
raises and works with the LLM dead:

1. **State-routed registry** (structured, real legal names):
   WA → keyless SoS JSON API · CA → Statement of Information, **gated behind
   `CA_SOS_API_KEY`** (free-tier cost unconfirmed, default OFF) · OR → best-effort
   HTML parse · other → OpenCorporates (`OPENCORPORATES_API_KEY`, rationed 50/day).
2. **Website scrape** — delegates to the existing `lead_gen_v3._scrape_website`.
3. **SerpAPI** — `SERPAPI_KEY`, only for leads scoring ≥70, rationed ~250/month.

Cross-cutting: a state_store cache (**hits only**, 30-day TTL) and persistent
day/month ration counters (survive Render restarts). Wired into
`enrich_lead_4step` (registry result short-circuits the text-mining owner
strategies but still runs them for email/phone); state inferred from the hunt
query; `owner_title` added to the output and persisted.

Also in this change: closed the one unconditional double-enrichment (a guard on
`light_enrich` Step 2's website re-crawl); fixed two latent bugs found in the
audit (`gmail_skill` missing `logging` import → NameError on bounces;
`sheets_sync` reading `.value` off an un-awaited coroutine).

## Consequences

- **+** Real owner/officer names from legal filings when a registry has the entity;
  graceful degradation to the old text-mining when it doesn't.
- **+** $0, Render-safe (HTTP-only), no new dependencies, no LLM dependency.
- **−** The live request shapes for WA/CA/OR/OpenCorporates are **unverified** —
  they return empty (never crash) until checked against the real APIs + keys set.
  **WA is keyless → the first to validate live.** CA cost still needs a signup pass.
- **−** The ~9 unused/broken scraper modules were **NOT removed**: they're wired
  into `planner`/`pipeline`/`ceo_brain`/`competitive_intel`/`deep_research`/tests,
  so removal is its own scoped refactor (deferred, tracked in [[roadmap]]).
- Tests: **150 passing** (+26: `test_owner_finder.py`, `test_skill_bugfixes.py`).

## Follow-ups

- Verify WA/CA/OR/OpenCorporates live and set the free keys (see [[roadmap]]).
- Consider a paid people-match fallback slot (Apollo/Hunter) later — behind a key.
- Full `enrich_lead_4step` + `enrich_lead_lite` merge (TODO in `light_enrich.py`).
- Scoped removal of the dead scraper modules + their wiring.
