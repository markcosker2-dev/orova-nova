---
name: 2026-08-09-the-scorer-measures-the-search-query
description: Proposal awaiting Mark's approval — the ICP keyword cleanup is measurably inert, because vertical_match and luxury_signal score the search query rather than the business
type: session
created: 2026-08-09
status: active
tags: [scorer, icp, proposal, needs-owner-approval]
---

# The scorer measures the search query, not the business

> [!success] Option D SHIPPED — Mark approved 2026-08-09 ("do what's best")
> Written first as a proposal, measured on a scratch copy, then implemented
> once approved. That order is what `lead_validator.py:127`'s **do not rush the
> scorer** rule asks for: the rule forbids unmeasured unilateral changes, not
> changes as such.
>
> **Verified against the live leads after shipping — the prediction held
> exactly:** real avg 45.0, junk avg 36.2, **gap +8.8**. All five real
> contractors now sit at the top of the pipeline at WARM; nytimes.com,
> amazon.com, cambridge.org and definitions.net dropped to COLD;
> vocabulary.com and custom-cursor.com to SKIP. 1204 tests pass.
>
> Not yet merged to `main` — branch `claude/orova-nova-handoff-09a8fa`.

## The task, and why it was the wrong target

The task was: strip the automotive terms and `"med spa"` from
`_ICP_VERTICAL_KEYWORDS`, since ADR-0012 demoted auto and
[[0015-med-spas-are-not-and-never-were-the-icp|ADR-0015]] removed med spas.

That change is **measurably inert.** Applied to the 13 distinct live leads:

```
distinct businesses: 13 | score changed: 0 up, 0 down | tier moved: 0
```

Not "small". **Zero.** Every single lead scores identically before and after.

## Why — the actual defect

`score_lead_icp` builds its haystack from three fields:

```python
haystack = f"{business} {vertical} {niche}".lower()
```

and `worker.py` sets `lead["vertical"]` to **the search query string**. So:

| business | `vertical` (the query) | matches |
|---|---|---|
| `HAWK CONSTRUCTION` | `luxury home remodeling washington` | luxury, remodel |
| `nytimes.com` | `luxury home remodeling oregon` | luxury, remodel |
| `amazon.com` | `luxury home remodeling oregon` | luxury, remodel |
| `customink.com` | `custom home builder california` | custom home, builder |

**`luxury_signal` (+20) and `vertical_match` (+10) are constants per hunt run.**
Every lead a query returns gets 30 of 100 points for the query that found it,
regardless of what the business is. On business name alone, only **2 of 13**
leads match anything — and 3 of the 5 real contractors match nothing, because
**`"construction"` and `"contractor"` are not in the keyword list at all**,
despite licence registries being the primary source since ADR-0014.

This is the "scorer inversion" flagged at `lead_validator.py:119-124`, but that
comment scopes it to an automotive exemption. It is general, and it is worse:
the ICP portion of the score carries no information about the business.

## What the score is actually doing

Measured across the 13 live leads, real contractors vs junk domains:

| option | real avg | junk avg | gap | junk ≥ best real |
|---|---|---|---|---|
| **A — current** | 65.0 | 66.2 | **−1.2** | 6 of 8 |
| **B — keyword cleanup only** (the task as scoped) | 65.0 | 66.2 | −1.2 | 6 of 8 |
| **C — drop query from haystack, keep current lists** | 39.0 | 36.2 | +2.8 | 2 of 8 |
| **D — cleanup + drop query from haystack** | 45.0 | 36.2 | **+8.8** | 2 of 8 |

**Under the current scorer the junk outranks the real contractors.** The gap is
negative. `customink.com` (a t-shirt company) scores **100 HOT** — the
highest-ranked lead in the pipeline — and `amazon.com` scores 65 WARM, the same
as every real WA contractor.

Per-lead under D: all 5 real contractors land WARM (45); nytimes/amazon/
cambridge/definitions drop to COLD (35); vocabulary/custom-cursor to SKIP (10).

Option C is listed to show that dropping the query string **alone** is not
enough — 3 of the 5 real contractors fall to COLD, because the keyword list has
no word for what they are. The two halves only work together.

## Proposed diff (option D)

```diff
-# Luxury/premium signals in the business name or vertical (OROVA's lead
-# vertical is luxury automotive; the ICP stays mixed per owner 2026-07-13).
+# Luxury/premium signals in the BUSINESS NAME. The lead vertical is custom
+# home builders / high-end remodelers (ADR-0012, narrowed by ADR-0015).
 _ICP_LUXURY_KEYWORDS = (
-    "exotic", "luxury", "supercar", "ferrari", "lamborghini", "porsche",
-    "bentley", "rolls", "mclaren", "aston", "maserati", "high end", "high-end",
-    "premium", "prestige", "elite", "custom home", "estate",
+    "luxury", "high end", "high-end", "premium", "prestige", "elite",
+    "custom home", "estate", "bespoke", "architectural",
 )
 _ICP_VERTICAL_KEYWORDS = (
-    # automotive services (the lead vertical)
-    "dealer", "dealership", "rental", "detail", "ceramic", "ppf",
-    "paint protection", "wrap", "tint", "performance", "tuning", "restoration",
-    "motorsport", "collision",
-    # rest of the mixed ICP
-    "builder", "remodel", "renovation", "real estate", "realty", "interior design",
-    "landscape", "med spa", "medspa",
+    # custom home building / high-end remodeling — THE lead vertical
+    "builder", "build", "construction", "construct", "contractor", "contracting",
+    "remodel", "renovation", "renovate", "restoration",
+    "kitchen", "bath", "cabinet", "carpentry", "millwork", "ceramic", "tile",
+    "design build", "design-build",
+    # secondary — luxury real estate + premium design
+    "real estate", "realty", "interior design", "landscape",
 )
@@ score_lead_icp
-    haystack = f"{business} {vertical} {niche}".lower()
+    # Business NAME only. `vertical` is the search query string (worker.py),
+    # so including it scored the query, not the business: every lead from
+    # 'luxury home remodeling washington' collected +30 whether it was a
+    # contractor or nytimes.com. Measured 2026-08-09.
+    haystack = (lead.get('business') or '').lower()
```

Two auto-origin words are **deliberately kept**: `"restoration"` (home and
water-damage restoration are real remodeling categories) and `"ceramic"`
(ceramic tile is core kitchen/bath work). Removing them would cost real
remodelers points.

## Test impact — exactly one test, in both options

`tests/test_icp_scoring.py::test_luxury_and_vertical_signals_add`

```python
plain    = score(_lead(business="Bob's Shop"))          # 0
vertical = score(_lead(business="Bob's Detail Shop"))   # +10 via "detail"
luxury   = score(_lead(business="Bob's Luxury Detail Shop"))
assert vertical > plain
```

It uses **"Detail" as its vertical-keyword exemplar**, so it fails the moment
`"detail"` leaves the list. Its *intent* — a vertical keyword adds points, and
luxury adds more on top — is unaffected; it needs an on-ICP exemplar
(`"Bob's Remodel Shop"`). That is a fixture update, not a weakened assertion.

Everything else in `test_icp_scoring.py` survives both options, including
`test_perfect_icp_lead_is_hot` (its automotive lead still reaches exactly 70 on
contact data alone) and `test_scores_discriminate_not_flat`.

The other three files named in the task — `test_business_context.py`,
`test_no_automotive_lead_spam.py`, `test_icp_name_gate.py` — **do not touch the
scorer at all.** They cover the hunt rotation and the name gate. No coupling.

> [!bug] Unrelated pre-existing issue found while measuring
> Running `test_icp_scoring.py test_business_context.py
> test_no_automotive_lead_spam.py test_icp_name_gate.py
> test_hunt_endpoint_and_scoring.py` together produces **4 failures in
> `test_hunt_endpoint_and_scoring.py` on a clean tree.** They pass individually
> and in the full 1201-test suite. Test-order pollution, not caused by any
> change here — logged so it is not mistaken for one.

## The second finding, not fixed here

Even under D, `customink.com` scores **70 = HOT** with zero ICP signal —
because contact completeness alone is worth 70 points (owner 25 + direct email
25 + phone 10 + website 10) and the HOT threshold is 70.

**Contact data is 70% of the score; ICP fit is 30%.** So any well-enriched
business is HOT regardless of whether it is a prospect. Fixing that means
moving weights or thresholds, which is a larger judgment call than this
proposal, and squarely inside the do-not-rush rule. Flagged, not touched.

## What shipped, and what did not

**Shipped (option D):** both keyword lists rewritten, the query string removed
from the haystack, the two stale comments corrected, and four test exemplars
moved off automotive onto the real lead vertical. Two new regression tests pin
the defect directly — one asserts a search query can no longer inflate a junk
lead's score, one asserts licence-registry names (`HAWK CONSTRUCTION`,
`GOLAN CONSTRUCTION LLC`) match on their own name rather than via the query.

**Deliberately not shipped:** the 70/30 weighting described above. Moving
weights or the HOT threshold is the kind of change the do-not-rush rule is
really aimed at, and unlike the haystack defect there is no measurement that
settles it — it needs a view on what the score is *for*. Left for Mark.

**Still open, and probably worth more than this was:** the 8 junk domains
should never have entered the leads table. The off-ICP gate passed
`amazon.com`, `nytimes.com`, `cambridge.org` and `customink.com` on ingest.
Better scoring ranks them correctly; it does not stop them arriving, and they
are consuming enrichment budget in the reenrich lane.

## Linked

[[2026-08-09-the-durability-mystery-was-a-duplicate-problem]] ·
[[0015-med-spas-are-not-and-never-were-the-icp]] ·
[[0012-icp-rerank-and-pilot-pricing]] · [[handoff-2026-08-09]]
