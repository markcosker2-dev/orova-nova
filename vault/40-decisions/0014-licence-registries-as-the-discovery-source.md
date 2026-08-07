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
| Yelp Fusion | 2026 free tier ambiguous; needs 1–2 day approval — **❌ WRONG, see correction below** |

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

> [!failure] ❌ CORRECTION 2 (2026-07-31) — **Yelp is not a dead end**
> The dead-ends table above lists Yelp Fusion as *"2026 free tier ambiguous;
> needs 1–2 day approval"*. **That is wrong.** Yelp is live via Composio with
> **no API key, no approval, and no payment**, verified by live query on
> 2026-07-31.
>
> | Metro | Contractors returned |
> |---|---|
> | Los Angeles | 20,000 |
> | Portland | 3,600 |
> | Seattle | 3,300 |
> | San Diego | 2,400 |
>
> It returns business name, phone, address, category, rating and **review
> count** — which is the business-size proxy this ADR flagged as unsolved
> ("no employee count... the datasets are full of one-person handymen...
> needs a proxy, and that proxy is unvalidated"). Review count plus an explicit
> category label is a better proxy than bond size or licence age, and it is free.
> It does **not** return a website or an email.

> [!warning] ⚠️ CONSEQUENCE — the sequencing below is no longer right
> This ADR ordered the work by **which state has a free registry API**: WA first,
> OR third, **CA last** because CSLB has no API. That put the **#1 ICP geography
> last for a purely technical reason**, and in practice it let tooling drive
> targeting instead of the ICP.
>
> Yelp dissolves that constraint — it works identically in every metro, and LA
> alone is 6× Seattle. **Discovery should be West Coast by default, not WA-only.**
>
> What remains genuinely state-specific is the **owner name**: Yelp does not
> supply one, and `outreach_ready` requires a decision-maker name on every
> channel. WA/OR get it from their registries; **CA needs it from the CSLB CSV or
> from website scraping** — and website scraping is seam 2 anyway, so *one crawl
> solves both the email gap and the California gap*.

> [!failure] ❌ CORRECTION 3 (2026-08-05) — **the CSLB personnel file is not free**
> The table above lists CA CSLB as *"no API — free CSV/XLS download incl. a
> personnel file"*. The personnel file is real; **it is not free.**
>
> CSLB sells fixed-block text files by mail order (CD/DVD or email) at
> **$235.00 each, non-refundable** — confirmed from CSLB's own order form and
> record layout, 2026-08-05:
>
> | File | Contains | Owner names? |
> |---|---|---|
> | **Business Principal File** (rec len 2610) | `LIC-NUMBER`, `NAME-TYPE` (P=Principal), `LAST-NAME`, `FIRST-NAME`, `MIDDLE-NAME`, `SFX-NAME`, `EMPL-TITL-CODE` | ✅ **yes** |
> | License Master File (rec len 700) | address, phone, status | ❌ *"DOES NOT provide license personnel information"* |
>
> The Business Principal File carries **no address**; the License Master File
> carries **no personnel**. CSLB states both explicitly.
>
> **The California path is therefore a JOIN, not a subscription:**
> the *free* Public Data Portal export (business + address + phone at 100%
> fill) ⟕ the **$235** Business Principal File, on `LIC-NUMBER`.
>
> Caveats before anyone spends: full files are cut in **January and July
> only** (order in August → you receive the July file), the format is
> fixed-width text requiring a parser, and there is no API — it is a paper
> form and a cheque. **$235 is a budget decision for the owner, not a code
> decision.** Nothing has been spent.

> [!success] ✅ CORRECTION 4 (2026-08-05) — **the size proxy is solved for Oregon**
> The Consequences section below says *"No employee count, so the 6-10-person
> ICP cannot be filtered directly... Needs a proxy... and that proxy is
> unvalidated."*
>
> OR CCB ships one: **`exempt_text`**, defined by the publisher as *"Whether
> this license holder is required to carry Workmans Compensation Insurance"* —
> i.e. whether the licensee **has employees**. `Nonexempt` is the ICP side.
> Measured live in the Portland metro: 9,867 RGC rows with owner + phone, of
> which **3,943 are Nonexempt**.
>
> It is a **SIZE** signal and explicitly **not an affordability** one, per the
> 2026-08-05 correction that `BusinessType` is a tax filing status and says
> nothing about revenue or headcount. WA L&I has no equivalent field.

> [!info] SEAM 3 SHIPPED (2026-08-05) — OR CCB is wired
> Sequencing step 3 below is done ([PR #134](https://github.com/markcosker2-dev/orova-nova/pull/134)),
> on top of a jurisdiction dispatch table
> ([PR #133](https://github.com/markcosker2-dev/orova-nova/pull/133)) that
> replaced deciding the registry by substring-matching a search query.
>
> Two findings that contradict the natural reading of this ADR:
>
> 1. **`license_type='RGC'` is a licence CLASS, not a trade category.** Over
>    1,200 real Portland-metro RGC rows, the narrow name filter accepts 80.7%
>    (noise) against the strict filter's 35.7%. RGC happily covers `SHAMBURG
>    HEATING`, `SEWER RENEWAL SPECIALISTS`, `AQUA TECH BACKFLOW`. **Oregon uses
>    the STRICT filter, exactly as WA does** — the narrow one is correct only
>    where a source publishes a genuine trade category (Yelp).
> 2. **The dataset is not Oregon-only.** It is *"contractors who can legally
>    work in Oregon"* — **14.5% (8,090/55,931) are based in another state**,
>    4,582 of them in Washington.
>
> Also: a **full sweep of the federated Socrata catalog across every US portal**
> (181 datasets carrying both an owner-like and a phone-like column) found
> **no third West-Coast contractor registry**. WA L&I and OR CCB are the
> complete set in this class; both are now wired. See
> [[session-2026-08-05-registry-by-state-and-or-ccb]].

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
