---
name: 2026-08-09-the-write-was-overwriting-row-two
description: The backup bug that destroyed lead data for weeks — every Sheets append targeted A2:L2 — plus the ICP rework that followed
type: session
created: 2026-08-09
status: active
tags: [durability, sheets, icp, sole-owner, retell]
---

# The write was overwriting row two

The single most important finding in weeks, and the chain that led to it.

## The bug

```
15:03:22 append -> updatedRange='Leads!A2:L2' business='HEARTWOOD BUILDERS INC'
15:03:23 append -> updatedRange='Leads!A2:L2' business='PEAK BUILDERS INC'
15:03:24 append -> updatedRange='Leads!A2:L2' business='LEWCO CONTRACTING'
15:03:25 append -> updatedRange='Leads!A2:L2' business='ELLCO CONSTRUCTION INC'
15:03:26 append -> updatedRange='Leads!A2:L2' business='ACCRETE CONSTRUCTION LLC'
```

**Every append targeted the same cells.** Five distinct businesses, five
successful API calls, one row. `gspread.append_row` asks Google to detect where
the table ends starting from A1; that detection resolved to the header row and
returned row 2 every time.

So `Sheets: 5/5 leads synced` was **true and worthless simultaneously** — and
every restore ever recovered exactly one lead, not because the restore was
broken but *because there was only ever one row*.

The owner saw the same thing independently from the sheet side: *"it only stays
on row 2, it doesn't put the leads in the row below, just removes the second row
and replaces it."*

**Fix:** stop guessing. Column 2 is already read to match on business name, and
its length IS the last used row — write to that +1 explicitly, via the update
path that always worked for matched rows.

## How we got there — four wrong turns worth remembering

The handoff called this the highest-value unknown and framed it as *"is the
write lying, or is the read looking in the wrong place?"* It was neither, and
the route there went through three confident, wrong mechanisms:

1. **"Duplicate collapse."** Real (24 rows, 13 distinct businesses) and it
   explained most of the count gap — but not a contractor reported synced at
   08:59 being absent at 11:21. **Partial explanations are still wrong.**
2. **"Duplicate workbooks."** `sheets_sync` opened the CRM by TITLE
   (`client.open("OROVA CRM")`) and silently `create()`d a new one on any
   failure — a genuine ratchet, and worth fixing. But pinning `CRM_SHEET_ID`
   proved Nova was on the owner's own sheet all along.
3. **"A read-after-write race in my own verifier."** Ruled out by
   time-separated evidence: HAWK CONSTRUCTION was reported synced and was
   absent **2h22m** later.
4. Only then: **instrument it.** `append_row` returns `updates.updatedRange`
   and the code was throwing it away. One log line ended weeks of speculation.

> [!important] The lesson
> Three of those were reasoned from evidence that had already run out. The
> answer came from *capturing a field the API had been returning all along*.
> **When a mechanism explains most of the evidence but not all of it, it is
> wrong — instrument, don't theorise.**

## The verifier chain

Worth recording because each step was necessary:

| step | what it revealed |
|---|---|
| #153's verifier crashed on `sqlite3.Row` every run | it had **never executed**; tests mocked a dict |
| fixed it | `BACKUP INCOMPLETE` — real |
| pinned `CRM_SHEET_ID` | same document as the owner's, kills split-brain |
| logged `updatedRange` | **the row-2 collision** |
| fixed the write | `✅ verified: sheet holds 5 rows covering 5 distinct businesses` |

That green line is the first genuinely durable backup this system has had.
Deploys are no longer data-loss events.

## The ICP rework that followed

Once leads persisted, their quality became the question.

**The hunt was sourcing the least qualified contractors in Washington.** It
ordered `licenseeffectivedate DESC` — newest first — reasoning that a recently
licensed contractor "is still building a client base." That optimises for who
NEEDS leads; ADR-0012 qualifies on who can PAY. The three verifiable production
leads were licensed **3-4 days earlier**, single-principal, at the $1M minimum.

Inverting the sort **overshot**: W G CLARK (1963), ABSHER (1966), TURNER
CONSTRUCTION ($5M cover) — national commercial GCs. Only visible by running the
query live rather than reasoning about it. Selection is now a **band**.

### Solo is a discount, not a disqualification

`business_context.json` treats *"No payroll (solo operator) - no urgency"* as a
flat kill signal. That conflates two measurements:

| signal | measures | source |
|---|---|---|
| principal count | **urgency** (payroll = external deadline) | `4xk5-x9j6` |
| insurance cover | **affordability** (big jobs = can pay) | `ciwg-agsx` |

**Measured: of 300 contractors carrying above the $1M minimum, 126 (42%) are
sole operators.** They can afford the retainer; their urgency is personal
rather than institutional. Disqualifying them discards 42% of the demonstrably
affordable market.

So the Retell script **branches** instead: `has_crew` → payroll; `solo` → his
own income and calendar, and never mention payroll (instantly wrong to the
listener); `unknown` → ask, never assume.

### Free WA registry datasets — all keyless, all verified

| dataset | id | gives |
|---|---|---|
| Contractor licences | `m8qx-ubtq` | name, principal, phone, trade, entity type, UBI |
| Principals | `4xk5-x9j6` | every named principal per UBI — **58.9% have exactly 1** |
| Insurance | `ciwg-agsx` | GL cover — **88.4% carry exactly $1M, 7.9% carry more** |

Joined on `ubi`. There is **no free payroll signal** — WA's only workers-comp
dataset is aggregate claim rates, not per-employer.

## Other defects fixed the same day

- **The scorer measured the search query, not the business.** `worker.py` set
  `lead["vertical"] = niche` and the scorer read `vertical`, so every lead a
  query returned collected +30. Real-vs-junk separation was **−1.2**;
  `customink.com` was the highest-ranked lead in the pipeline. Fixed at the
  scorer, then at the write.
- **A bare domain is not a business name.** 8 of 13 distinct businesses were
  `amazon.com`, `nytimes.com`, `cambridge.org`… Added as the third sibling to
  the gate's phone-as-name and email-as-name rejections.
- **Licence-registry leads had no dedup key** — `save_lead` keyed on email or
  domain, and registry rows have neither.
- **Dedup discarded what it relearned.** "Same business" was treated as "ignore
  everything new", so restored rows could never heal.

## Linked

[[2026-08-09-the-durability-mystery-was-a-duplicate-problem]] ·
[[2026-08-09-the-scorer-measures-the-search-query]] ·
[[2026-08-09-a-bare-domain-is-not-a-business-name]] ·
[[0015-med-spas-are-not-and-never-were-the-icp]] · [[handoff-2026-08-10]]
