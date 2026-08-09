---
name: 2026-08-09-the-durability-mystery-was-a-duplicate-problem
description: The [DURABILITY] verifier had never once run — and the backup was never broken; the leads table duplicates and the sheet correctly dedupes
type: session
created: 2026-08-09
status: active
tags: [durability, data-quality, production, dedup]
---

# The durability mystery was a duplicate problem

> [!danger] CORRECTED LATER THE SAME DAY — this note's conclusion was wrong
> This note concluded that the backup was fine and the leads table was merely
> inflating with duplicates. **That was incomplete, and the missing half was the
> important one.** The deploy at 11:21 proved it: the boot restore found only
> **4 sheet rows** (3 of them `Acme` fixtures), and all five real WA contractors
> were destroyed. They had never been in the sheet at all.
>
> Duplicate collapse was real and does explain part of the count gap — 24 rows
> for 13 distinct businesses is verified. It does **not** explain a contractor
> reported as `Sheets: 4/4 leads synced` at 08:59 being absent from the sheet at
> 11:21. The write genuinely does not persist.
>
> Root cause found at 12:0x: `sheets_sync` identified the workbook **by title**
> (`client.open("OROVA CRM")`), never by ID, and silently **created** a
> duplicate on any failure. See
> [[2026-08-09-the-scorer-measures-the-search-query]] for the sibling lesson —
> and note the pattern repeating: *a confident mechanism that explains most of
> the evidence is still wrong if it cannot explain all of it.*
>
> Keep reading below for the duplicate-collapse analysis, which stands on its
> own. Do not treat its closing "nothing was lost" framing as true.

## What we went looking for

[[handoff-2026-08-09]] §4a named this the highest-value unknown in the system.
PR #153 deployed an instrument meant to print one of two lines on the next hunt:

```
✅ verified: sheet holds N rows for N leads
🚨 BACKUP INCOMPLETE — the database holds X but the sheet has Y
```

The first would mean *the read looks in the wrong place*; the second, *the write
is lying*. Those need opposite fixes.

## What production actually printed

```
08:59:42 [DURABILITY:hunt] 📋 Sheets: 4/4 leads synced
08:59:42 [DURABILITY:hunt] backup verification failed
         ('sqlite3.Row' object has no attribute 'get') — durability UNKNOWN this run.
08:59:42 [DURABILITY:hunt] Drive snapshot unavailable (invalid_grant...)
```

**Neither line. The instrument crashed on every run since it shipped.**

`DatabaseManager.fetchone` returns a `sqlite3.Row` (the pool sets
`row_factory = sqlite3.Row`), and `Row` has no `.get()`. `durability.py:99` did
`(db_row or {}).get("c")`. The reading was never taken.

`tests/test_durability_verification.py` passed throughout — it mocked `fetchone`
with a plain **dict**, a shape production never produces. This is the same
failure the handoff's §3 describes: *a test that only covers the shape that
already works cannot fail when the real shape is different.* The gate-at-the-
call-site trio and this bug are the same mistake wearing different clothes.

## The answer, which was a third option nobody had listed

Not "the write is lying." Not "the read looks in the wrong place."
**The two numbers were never comparable.**

| | dedups on | today |
|---|---|---|
| `leads` table (`save_lead`) | email **or** website domain | 24 rows |
| Leads sheet (`sync_lead_to_sheets`) | URL, falling back to business name | ~13 rows |

Verified from `/api/leads` on 2026-08-09:

- **24 lead rows, 13 distinct business names, 0 rows with a URL.**
- `FOREVER QUALITY CONSTRUCT LLC` ×4; `HAWK CONSTRUCTION`, `TA BUILDERS LLC`,
  `GOLAN CONSTRUCTION LLC`, `GOLDENKEY REMODELING LLC` ×3 each.

Licence-registry leads (WA L&I, OR CCB, CSLB — **now the primary source**) have
no email, no url and no website. So `save_lead` has **no dedup key at all** for
them and re-inserts the same contractor on every hunt. The sheet, which upserts
by business name, correctly collapses them.

So the "45 → 1" and "19 → 1" losses were, to a large degree, **duplicate
collapse being read as data loss.** Nothing was restoring wrongly; the database
had been inflating. `leads_found: 24` in `/api/metrics` counts rows, not
businesses — the real figure is 13.

> [!warning] This is not proof the historical losses were *entirely* dedup
> The mechanism is confirmed and sufficient to explain the shape. Whether every
> one of the 45 was a duplicate is not recoverable after the fact. Treat "mostly
> dedup" as the working explanation, not a closed case — the fixed verifier will
> settle it on the next hunt.

## What changed (branch `claude/orova-nova-handoff-09a8fa`, NOT merged)

1. `durability.py` — `dict(db_row)` before `.get()`, so the check runs.
2. `durability.py` — compare like with like. The check now asks **"does every
   distinct business have a row?"**, not "do the totals match?" Fixing only the
   crash would have printed `BACKUP INCOMPLETE — 24 vs 13` while nothing at all
   was missing, and a monitor that cries wolf gets ignored exactly when it is
   finally right.
3. `outreach_orchestrator.py:173` — **the same `Row`/`.get()` bug**, found by
   grepping the pattern. There the `AttributeError` was swallowed by a bare
   `except`, so `get_best_send_timing()` has silently always returned the 9am
   default and the learned send-timing has never once been applied.
4. Tests now construct a **real `sqlite3.Row`**, so this class of bug can fail.
   1194 pass (1191 baseline + 3).

## The bug class worth carrying forward

The handoff gave us "gates belong at the chokepoint, not the call site." This
session adds its sibling:

> **A mock that is easier to satisfy than production is not a test, it is a
> decoy.** Both bugs here were invisible to a green suite because the fixture
> was a friendlier type than the real one.

The grep that found the second instance, worth re-running on any `fetchone`:

```bash
grep -rn "fetchone" app/ | # then check every result for .get( on the row
```

## The real open item this exposes

**`save_lead` cannot dedup the lead source we now depend on.** That is a
data-quality defect under the three-things rule, and it is upstream of the
durability noise: fix the duplication and the backup arithmetic stops being
confusing. Suggested key: `lower(trim(business)) + state` when email and domain
are both absent. Not built — it changes ingest behaviour and wants Mark's call.

## Linked

[[handoff-2026-08-09]] · [[2026-08-07-california-owner-names-are-free]]
