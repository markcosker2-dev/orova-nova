---
name: 2026-08-16-a-whitelist-is-a-silent-contract
description: One scoring field had to be named in SIX separate hand-built field lists before it worked. Each omission read as "the data isn't there" and none of them raised.
type: session
created: 2026-08-16
status: active
tags: [lesson, data-flow, whitelist, icp, durability]
---

# A whitelist is a silent contract

> [!abstract] One line
> Adding `insurance_amt` to the ICP scorer took **six** separate edits to six
> hand-built field lists across four PRs. Every missing one presented
> identically — as though the registry had no data — and not one of them raised
> an error or failed a test.

## The shape

Nova moves a lead through a long chain, and at almost every junction the lead
is **rebuilt** rather than passed along. Each rebuild is a hand-written list of
field names, and **anything not named is dropped in silence.**

That is a contract nobody signed and nothing enforces. Miss an entry and the
field does not arrive corrupted or absent-with-a-warning — it arrives as `0`,
which every downstream consumer correctly interprets as "not looked up".

## The six places one field had to be named

Live line numbers as of `d129b17`:

| # | Where | What it does | Missed in |
|---|---|---|---|
| 1 | `lead_gen_v3.py:2474` (`licence_out`) | discovery → caller | #168 |
| 2 | `_db_base.py:65` (`CANONICAL_SCHEMA_SQL`) | the column itself | #166 |
| 3 | `_lead_repo.py:357` (`INSERT INTO leads`) | write on insert | #166 |
| 4 | `_lead_repo.py:184` (`_backfill_registry_fields`) | heal on re-discovery | #166 |
| 5 | `main.py:878` (`/api/leads` SELECT) | show it at all | #169 |
| 6 | `sheets_sync.py:268/107/146` (header, cell, restore) | survive a deploy | #173 |

Numbers 1–5 are the same defect five times. Number 6 is the same defect twice
more in one file — the header and the row builder write it, the restore reads it
back — and it is the one that decides whether the field survives at all, because
Render's disk is ephemeral and the Leads sheet is the restore source.

## Why each one looked like something else

- **Missing from `licence_out`** → every registry lead scored a flat **61**. That
  reads as "the scorer's weights are wrong", not "the scorer is receiving
  nothing". It is the same signature as the flat 50 that `score_lead_icp` was
  created to fix.
- **Missing from the INSERT** → the score was right at hunt time and wrong on
  every recompute, because affordability fell back to neutral. `main.py:915`
  re-scores stored rows for the dashboard, so a $2M contractor displayed a
  weaker recommendation than his own stored score justified.
- **Missing from the API SELECT** → I read the absent key as a `null` value and
  reported the data as missing when it was stored correctly. **I diagnosed my
  own tooling gap as a production bug.**
- **Missing from the sheet** → cover went `30 -> 10` across one deploy while
  the row count reconciled at `40/40`. Rows were safe. Fields were not.

## The checklist this earns

When adding a field that a scorer, the sheet, or the call script reads:

1. `CANONICAL_SCHEMA_SQL` — the column (the reconciler ALTERs it in)
2. `save_lead`'s `INSERT` — written on create
3. `_backfill_registry_fields` — healed on re-discovery, **and re-score after**
4. The producing projection (e.g. `licence_out`) — survives leaving discovery
5. `/api/leads` SELECT — visible to you and the dashboard
6. `WORKSHEET_HEADERS["Leads"]` + row builder + `_lead_from_sheet_row` —
   survives a deploy

Then prove it end to end: run a hunt, **restart**, and confirm the value is
still there. Six of these were individually "done" and the feature still did
not work.

## The tell

> **A flat, identical score across every lead means the scorer is receiving
> nothing.** It has now happened twice — 50 before ADR-0012's rescoring, 61
> after. Both times the weights were blamed first and both times the input was
> the problem.

> **A row count that reconciles proves nothing about fields.** `40/40 restored`
> was true and worthless at the same moment 30 leads silently lost their cover.
> This is the field-level twin of the 2026-08-09 row-2 bug, where
> `Sheets: 5/5 leads synced` was true and the tab held one row.

## Trace forward, not backward

The debugging order that worked, after two wrong turns:

1. Confirm the source has the data — query the registry directly
2. Confirm the fetch worked — look for the success log
   (`[WA_LNI] principals resolved for 25/25`)
3. **Then walk every rebuild between the fetch and the consumer**

I twice concluded the joins were "failing silently" when they were logging
success correctly and the 100-line buffer had rotated past them. Polling
*during* a run settled in seconds what inference had got wrong twice.

## Linked

[[2026-08-14-the-icp-layer-was-decorative]] ·
[[2026-08-09-the-write-was-overwriting-row-two]] ·
[[2026-08-09-the-scorer-measures-the-search-query]]
