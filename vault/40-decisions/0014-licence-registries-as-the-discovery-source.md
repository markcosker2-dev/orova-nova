---
name: adr-licence-registries-as-the-discovery-source
description: "ADR: state contractor licence boards become the primary discovery + decision-maker source, replacing quota-bound search"
type: decision
created: 2026-07-26
status: active
---

# ADR-0014: State contractor licence registries as the discovery source

## Context

Three things converged on 2026-07-26 to force this.

**1. SerpAPI is exhausted and it is the only working discovery source.**
Verified against SerpAPI's own account API, not inferred:

```
plan_name            Free Plan
searches_per_month   250
this_month_usage     250
plan_searches_left   0
```

A live Seattle hunt that day returned **0 leads** — HTTP 429, fell through to
the legacy sources, which produced nothing. Discovery is dead until the
monthly reset. The 250 is also shared three ways (discovery + `owner_finder`'s
SERP fallback + the LinkedIn source), so it was always the binding constraint.

**2. Every alternative commercial source is closed at $0.** All tested live,
all dead ends:

| Source | Verified result |
|---|---|
| Meta Ad Library API | `ad_type=ALL` is EU/UK-only for commercial ads; US remodelers invisible |
| Meta Ad Library UI | needs Chromium (impossible on Render free) + scraping risks the ad account the business runs on |
| Apollo.io free tier | `API_INACCESSIBLE` **plan-wide**; 0 export credits, so even manual research can't leave the UI |
| Composio → Facebook | Pages-only; `FACEBOOK_SEARCH_PAGES` returns Error #10 (Workplace-only since 2019) |
| WA Secretary of State | `ccfs-api.prod.sos.wa.gov` is anti-bot gated; never returned a name server-side |
| OpenCorporates | £2,250/yr |
| Yelp Fusion | 2026 free tier ambiguous; needs 1–2 day approval |

**3. Licence boards turn out to be strictly better than what we were
reaching for.** They supply the *decision maker* directly — the problem the
whole CALICO / waterfall effort exists to solve. Measured live:

| Source | API | Volume | Owner-name fill | Phone fill |
|---|---|---|---|---|
| WA L&I (`data.wa.gov`, Socrata) | free, no key | 75,515 ACTIVE | **100%** | **100%** |
| OR CCB (`data.oregon.gov`, Socrata) | free, no key | 56,087 active | 95.9% | 100% |
| CA CSLB | **no API** — free CSV/XLS download incl. a *personnel* file | — | — | — |

6,249 WA rows match ACTIVE + GENERAL|RESIDENTIAL + Seattle metro + owner +
phone. That is more on-ICP records than a year of SerpAPI quota could produce.

> ⚠️ **CORRECTION (2026-07-30, seam 1 implementation — PR #120).** The "6,249
> on-ICP rows" figure above **overcounts**, because it assumes
> `specialtycode1desc = 'GENERAL'` means "general contractor". It does not.
> Reading real rows shows the GENERAL bucket is full of landscapers, window
> cleaners, drywall, tile, masonry and one-person handymen. Two extra filters
> are needed — licence *type* and a business-name filter. Measured live against
> the dataset on 2026-07-30 (a wider metro city list than the original count):
>
> | filter | rows |
> |---|---|
> | `contractorlicensestatus='ACTIVE'` | 75,463 |
> | + specialty `GENERAL`\|`RESIDENTIAL` | 55,942 |
> | + Seattle metro + owner & phone present | 16,322 |
> | + `contractorlicensetypecodedesc='CONSTRUCTION CONTRACTOR'` | 15,069 |
> | **+ passes the ICP business-name filter** | **~4,280 (28.4%)** |
>
> Fill on `businessname` / `primaryprincipalname` / `phonenumber` /
> `address1` is confirmed at **100%**, as originally measured.
>
> ~4,280 is still far more on-ICP records than Nova can call, so the decision
> below stands unchanged — but the name filter is load-bearing, not optional,
> and anyone quoting a row count from this ADR should quote 4,280.

## Decision

**Adopt state contractor licence registries as the primary source for
discovery, owner name, phone and address; demote search to enrichment only.**

This inverts the pipeline. Today Nova discovers a business and then hunts for
its owner — the hard, unreliable, quota-burning direction. Licence data gives
the owner *first*, from a legal record, for free; the only remaining unknown
is the website (and from it, email + ad signals).

Per the extension-first rule this is an **extension, not a new abstraction**:
`owner_finder._registry_lookup` already routes WA/CA/OR by state. The WA leg
was swapped from the dead SoS endpoint to L&I on 2026-07-26 (PR #113) and is
live. What remains is using the same datasets as a *discovery* entry point,
not only a lookup.

Sequencing, one seam at a time:

1. **WA L&I as a discovery source** (`_source_wa_lni_licences`) — filter by
   status/specialty/city, emit the existing lead shape. Free, unlimited.
2. **Website resolution** for licence-sourced leads, since the datasets have
   no domain. This is the one step that still needs search, so it becomes the
   *only* rationed call in the chain.
3. **OR CCB** as the same shape (`rmi_name`, `phone_number`).
4. **CA CSLB** last — no API, so it needs an operator-run file import via
   `POST /api/leads/import-csv`. California is the #1 ICP geography and the
   only one without programmatic access; do not let that ordering surprise
   anyone.

## Consequences

**Easier.** Discovery stops being quota-bound. Owner name and phone arrive at
100% / 95.9% fill from a legal record rather than regex-mining a homepage, so
`outreach_ready` becomes reachable in volume and the Retell lane finally has
numbers to dial. Zero ToS or account risk — government open data. The CALICO
wait stops blocking WA and OR entirely.

**Harder.** Four real costs, none hypothetical:

- **No email, anywhere.** Licence data has none. Email remains the unsolved
  field and still must never be guessed.
- **No website**, so the ad-signal detector (the ADR-0012 "already paying for
  leads" qualifier) cannot run until a domain is resolved. That resolution is
  now the rationed step.
- **No employee count**, so the 6–10-person ICP cannot be filtered directly.
  The datasets are full of one-person handymen — the disqualified segment.
  Needs a proxy (bond/insurance amount, licence age) or manual triage, and
  that proxy is unvalidated.
- **Format work**: principals are `"LAST, FIRST MIDDLE"` in caps, phones are
  bare 10-digit. Both need normalising, and a careless match attaches a real
  person to the wrong company.

**Explicitly giving up.** Any pretence that a commercial B2B database is
reachable at $0 — Apollo, ZoomInfo and peers monetise exactly the export step
we need. Also giving up on the Meta Ad Library as an automated source
permanently, not just for now: the API cannot serve US commercial ads and
scraping risks the account the business depends on.

**Guardrail carried forward.** Strict matching is non-negotiable. The WA
lookup already refuses single-token business names after a live case where the
bare query `"Acme"` exact-matched a licence literally named `ACME` and returned
its principal — a correct string match to the wrong company. A miss must always
beat a confident wrong name.

## Linked

- [[0010-consolidation-before-features]] · [[0012-icp-rerank-and-pilot-pricing]]
- [[0009-persistent-decision-maker-waterfall]] · [[0008-lead-intelligence-provenance]]
- [[session-2026-07-26-merge-and-discovery-wall]]
