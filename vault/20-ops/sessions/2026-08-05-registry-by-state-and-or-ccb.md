---
name: session-2026-08-05-registry-by-state-and-or-ccb
description: Jurisdiction made first-class, OR CCB wired as the second licence registry, and a live survey that prices the California owner-name gap at $235
type: session
created: 2026-08-05
status: active
tags: [session, discovery, licence-registries, adr-0014]
---

# Session — 2026-08-05 · registry-by-state, OR CCB, and the registry survey

> [!info] Shipped as three PRs, none merged
> **[#133](https://github.com/markcosker2-dev/orova-nova/pull/133)** jurisdiction as first-class data ·
> **[#134](https://github.com/markcosker2-dev/orova-nova/pull/134)** OR CCB (stacked on #133) ·
> this doc. They join the six already queued; #133 → #134 is the only ordering
> constraint among the new ones.

---

## 1. What was asked

Wire OR CCB (the "highest-value unbuilt thing"), fix registry-by-state so
jurisdiction stops being decided by substring-matching a search query, and
find more registries in the WA L&I class.

## 2. Jurisdiction is now data, not prose (#133)

`find_leads_v3` chose **which government licence registry to query** by
substring-matching the free-text hunt query for `"california"` /
`"washington"` / `"oregon"`, then reached the one working registry through a
hardcoded `if state == "WA"`.

The expensive part was not the if-chain, it was the **silence**. A query with
no recognised geography resolved `state=""`, skipped every registry, and fell
through to the legacy scrapers — which this same module documents as producing
leads with no name, no phone and no address. Nothing was logged. That is the
whole mechanism behind "California falls through to a scraper".

Now: an explicit `state=` parameter, a `LICENCE_REGISTRIES` dispatch table, and
a **loud** log on both failure modes (no jurisdiction / jurisdiction with no
registry). `location` stays a search term; `state` is a jurisdiction. Threaded
through `run_lead_hunt_slow_lane` and `POST /api/actions/hunt-leads`, plus a
`TARGET_STATE` env fallback.

Adding a state is now one `register_licence_registry()` line.

> [!warning] A latent bug caught on the way
> The licence emit block defaulted `owner_source` / `phone_source` to
> `"wa_lni"` and `state` to `"WA"`. Harmless with one registry — but it would
> have stamped **WA provenance onto every Oregon lead** the moment a second one
> registered. Found before wiring OR, pinned by a test.

## 3. OR CCB wired (#134)

`data.oregon.gov/resource/g77e-6bhs.json` — 55,931 rows, free, keyless.
Measured live: `phone_number` **100%** fill, `rmi_name` **97.3%**.

A live run returns 12/12 Portland-metro remodelers with owner name, E.164
phone and street address — **dialable with no enrichment**.

Three data-shape traps, each found by reading real rows rather than field
names:

**1. It is not an Oregon-contractors dataset.** It is *"contractors who can
legally work in Oregon"*. **8,090 of 55,931 (14.5%) are based elsewhere —
4,582 in Washington.** Without `state='OR'` an Oregon hunt returns Washington
businesses.

**2. The endorsement is a licence class, not a trade category.** The tempting
move was to trust `license_type='RGC'` the way the Yelp source trusts a Yelp
category, and use the narrow name filter. Measured over 1,200 real RGC rows in
the Portland metro:

| filter | accepts |
|---|---|
| `off_icp_trade_in_name` (narrow) | **80.7%** — fires on nearly everything, i.e. noise |
| `icp_business_name_reason` (strict) | **35.7%** |

The 45-point gap is real off-ICP work an RGC licence covers: `SHAMBURG
HEATING`, `SEWER RENEWAL SPECIALISTS`, `KRAFT SCREENS & WINDOW WASHING`, `AQUA
TECH BACKFLOW`, `PROPERTY MANAGEMENT NORTH WEST`. **OR uses the STRICT filter,
same as WA.**

**3. 116 rows carry a placeholder instead of a person** — `RD - NO RMI RQRD`,
`RMI NOT RQ'D`, `NO RMI ON FILE`. These parse to `Rd Rqrd` / `No Rmi`, **pass
`_is_plausible_name`**, and would have put a nonexistent person into a Retell
call script.

### The parsing bug OR exposed

`_person_from_principal` stripped generational suffixes only on the **comma**
path. OR CCB `rmi_name` has **0% commas**, so every Oregon row took the other
branch — and **3.18% end in a suffix** (191/6,000 measured):

| raw | before | after |
|---|---|---|
| `DONALD JOSEPH ZEISE JR` | `Donald Jr` ❌ | `Donald Zeise` |
| `KEVIN THOMAS WYNNE II` | `Kevin Ii` ❌ | `Kevin Wynne` |

All of them passed `_is_plausible_name`. **WA blast radius is effectively
nil** — 0.47% of WA rows take the no-comma path and exactly 1 in 6,000 carried
a trailing suffix. Verified, not assumed.

### The size proxy ADR-0014 called unsolved

ADR-0014: *"No employee count, so the 6–10-person ICP cannot be filtered
directly... needs a proxy, and that proxy is unvalidated."*

`exempt_text` is that proxy, from the publisher's own column definition —
**"Whether this license holder is required to carry Workmans Compensation
Insurance"**, i.e. has employees. Portland metro: 9,867 RGC rows with owner +
phone, **3,943** of them Nonexempt. Defaults on, parameterised.

Framed deliberately as a **size** signal, not an affordability one — per the
2026-08-05 correction that `BusinessType` is a tax status and says nothing
about revenue.

## 4. The registry survey — and what it settles

Swept the **federated Socrata catalog across every US portal** (not just the
ones already known) for datasets carrying both an owner-like and a phone-like
column. 181 unique datasets examined.

**Result: WA L&I and OR CCB are the only two in the contractor-registry class
on the West Coast.** Both are now wired. There is no third one hiding.

Everything else found was out-of-ICP geography or out-of-ICP data: NY's
Contractor Registry Certificate, New Orleans occupational licences, Henderson
NV business licences, Austin permits.

Non-Socrata probes (raw HTTP, from this sandbox):

| Target | Result |
|---|---|
| `data.ca.gov` CKAN | **403 Cloudflare 1009** (IP/region ban) |
| AZ ROC, UT DOPL, FL DBPR | **403 Cloudflare challenge** |
| `data.colorado.gov`, `data.texas.gov` | reachable, **no contractor licence dataset** (neither state licenses residential GCs at state level) |
| NV / ID open-data portals | DNS failure — URLs unconfirmed |

> [!caution] Blocked ≠ dead
> The Cloudflare 403s are **sandbox reachability**, not proof the source is
> unusable. This is exactly the NPPES pattern in reverse — worth Mark
> re-testing in his own Chrome before anyone writes them off. Recorded as
> unknown, not as dead ends.

## 5. California — the owner-name gap now has a price

This is the genuinely new finding, and it **corrects ADR-0014**.

ADR-0014 lists CSLB as *"no API — free CSV/XLS download incl. a personnel
file"*. The personnel file is real, but it is **not free**.

CSLB sells fixed-block text files by mail order (CD/DVD or email), **$235.00
each, non-refundable**:

| File | Contains | Relevant? |
|---|---|---|
| **Business Principal File** | `LIC-NUMBER`, `NAME-TYPE` (P=Principal), `LAST-NAME`, `FIRST-NAME`, `MIDDLE-NAME`, `SFX-NAME`, `EMPL-TITL-CODE` | ✅ **the owner names** |
| License Master File | address, phone, status | already free via the portal export |
| Workers' Comp / Action Codes / Complaint | — | no |

The Business Principal File explicitly carries **no address information**, and
the License Master File explicitly carries **no personnel information** — CSLB
says so in the order form.

**So the California path is a join, not a purchase of everything:**

```
free CSLB portal export  (business + phone 100% + address)
        ⟕  on LIC-NUMBER
$235 Business Principal File  (owner first/last/suffix + title)
        =  callable California leads with a named decision maker
```

Caveats worth knowing before spending: full files are cut in **January and
July only** (order in August → you get the July file), the format is
fixed-width text needing a parser, and there is no API — it is a paper form
with a cheque.

**$235 is a budget decision, not a code decision.** Nothing was spent, nothing
was committed. Recorded so the option is priced rather than vague.

> [!note] `SFX-NAME` exists in that layout
> CSLB stores `Jr., SR., II` in a dedicated suffix field — which is precisely
> what the `_person_from_principal` fix in #134 now handles correctly. The CSLB
> import would have hit the same bug.

## 6. Corrections to existing docs

1. **ADR-0014**: the CSLB personnel file is **$235, not free** (§5 above).
2. **ADR-0014**: the "no employee-count proxy" gap is **closed for Oregon** by
   `exempt_text`.
3. **[[handoff-2026-08-05]] read order** points at
   `vault/90-docs/pipeline-runbook-2026-08-03.md`, which **does not exist on
   `main`** — it lives only on the unmerged `docs/pipeline-runbook` branch
   (PR #131). A cold start following that read order hits a missing file.
4. `_or_registry_lookup` in `owner_finder.py` targets the **Oregon Secretary
   of State CBR HTML page**, not CCB, and returns a *Registered Agent* — often
   a law firm or registered-agent service, not the owner. It is a different
   and weaker source than the CCB registry wired in #134. Left alone this
   session; flagged as a follow-up.

## 7. Still open

- **Med spas (ICP vertical #2) still have no source.** The registry class does
  not cover them — licence boards are trade-specific and cosmetic/medical
  practices sit under medical boards. NPPES stays untouched per instruction.
- The shared ICP regex misses real remodelers whose names carry
  `HOME IMPROVEMENT`, `HOMES` or `GENERAL CONTRACTOR` without a
  build/remodel keyword (`BLAZER HOMES`, `JW HOME IMPROVEMENTS`,
  `ND NW GENERAL CONTRACTOR`). Precision-biased by design, and changing it
  moves WA's behaviour too — deliberately not touched in a PR about Oregon.

## Linked

[[0014-licence-registries-as-the-discovery-source]] ·
[[handoff-2026-08-05]] · [[0012-icp-rerank-and-pilot-pricing]] ·
[[active-context]]
