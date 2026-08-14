---
name: 2026-08-14-the-icp-layer-was-decorative
description: The ICP scoring shipped in #165 never received data — a whitelist dropped the three signals the hunt had just ranked on. Seven PRs, and the ephemeral disk is the constraint nobody had named.
type: session
created: 2026-08-14
status: active
tags: [session, icp, hunt, dedup, durability]
---

# The ICP layer was decorative

> [!abstract] One line
> Every registry lead scored a flat **61**. Not because the scorer was wrong —
> because a hand-built dict in `find_leads_v3` silently dropped the three fields
> the hunt had just finished *ranking on*.

## What was wrong

`find_leads_v3` emits licence-registry leads through `licence_out`
(`lead_gen_v3.py:2363`). The comment above it says they "are emitted directly."
They are not — it is a **whitelist**, and it omitted exactly:

| Field | Drives |
|---|---|
| `principal_count` | `crew_status` → sole-owner status → which pain the call opens on |
| `insurance_amt` | affordability, up to 20 points — the largest scoring component |
| `vertical` | the licensed trade the registry publishes |

Everything upstream had always worked:

```
[WA_LNI] principals resolved for 25/25 businesses · 6 are sole operators
[WA_LNI] insurance resolved for 25/25 businesses · 1 carry above the $1M minimum
[WA_LNI] ranked 25 candidates — returning 5, 5 sole operators
```

**Five sole operators, selected on cover, handed to a projection that dropped
both signals it had just sorted by.** The flat 61 is the signature of a scorer
receiving nothing — the same failure `score_lead_icp` was created to fix when
every lead scored 50.

The data was never missing. Queried live:

```
J L REMODELING INC       ubi=602184407  principals=1  insurance_rows=1
FATBOY CONSTRUCTION INC  ubi=602174609  principals=1  insurance_rows=1
SCHULTE CONSTRUCTION LLC ubi=602167358  principals=1  insurance_rows=1
R G N CONSTRUCTION LLC   ubi=602075001  principals=1  insurance_rows=1
LEWCO CONTRACTING        ubi=602107224  principals=1  insurance_rows=1
```

All five sole operators. All five stored as unknown.

## What shipped

| PR | What |
|---|---|
| #163 | Machine truth stopped disqualifying sole operators (4 places); 12 skills; 4 agents |
| #165 | The three sheet/ICP commits + the seam bug between them |
| #166 | `insurance_amt` was never a **column** — fetched, scored on, discarded at INSERT |
| #167 | Fire-and-forget tasks were unanchored — `hunt-leads` was a silent no-op |
| #168 | The licence projection above |
| #169 | Heal on every dedup branch; expose cover in `/api/leads` |

After #168 the hunt worked end to end for the first time: **LEWCO 76 → 83,
SOLO, trade `General`** — arithmetic being affordability 10→20 ($2M) plus
urgency 6→3 (solo).

## The constraint nobody had named

Then a deploy reset it to 76.

Render free tier has an **ephemeral disk**. Every deploy destroys the SQLite
database, and the restore source is the Leads sheet:

```
16:40:34 ♻️ Restored 14/14 leads from Google Sheets
```

So **any column not in `WORKSHEET_HEADERS["Leads"]` cannot survive a deploy.**

- `principal_count` → `Principals` column exists (#161) → survives
- `insurance_amt` → **no column** → lost on every deploy, permanently
- `vertical` → `Niche` column exists but held the stale pre-heal value

This reframes the durability work. #160 fixed *losing rows*. Rows are safe.
What is not safe is any **field** the sheet does not carry — and that failure is
invisible, because the row count reconciles perfectly.

Five deploys today each silently reset the affordability signal.

**Decision needed:** add an `Insurance` column to the Leads tab (cheap, follows
the #161 pattern), or accept that cover re-heals on the next hunt and never
persists. Until then affordability is real for exactly as long as the container
lives.

## Lessons

> **A whitelist is a silent contract.** Three of today's bugs are the same
> shape: a hand-built dict that drops any field not named in it —
> `licence_out`, the `/api/leads` SELECT, and `insurance_amt` missing from the
> INSERT. None raised. All three read as "the data isn't there."

> **A cancelled task reports nothing.** `hunt-leads` returned
> `{"status":"ok"}` and did nothing, because `asyncio` holds only a weak
> reference to a running task and the error callback skipped
> `t.cancelled()`. Success and silence looked identical.

> **The decoy-mock lesson, again.** `test_source_vertical_survives_the_hunt.py`
> asserts on `_apply_hunt_default`, a *local re-implementation* of the one line
> `worker.py` runs. It passed throughout, because the field was already gone two
> layers upstream. It tested the fix, not the pipeline.

> **I diagnosed from an absence I created.** I reported the registry joins as
> "failing silently." They log success and failure correctly — the 100-entry
> buffer had rotated past them before I read it. Polling *during* the run
> settled in seconds what inference had got wrong twice.

## Still open

1. **`CAL_COM_EVENT_SLUG`** — `get_booking_link()` returns `""`. A prospect who
   says yes has nowhere to go. ~5 minutes, owner-only.
2. **Paste `retell_pitch` into Retell.** Nothing reads it from the repo — the
   sole-operator fixes are inert until pasted.
3. **The `Insurance` sheet column** — see above.
4. **`DASHBOARD_API_KEY` rotation** — still `nova_2026`.
5. **Drive OAuth** — still `invalid_grant`, still the optional tier.
6. **Zero conversations, ever.** Eight PRs today. None of them is a phone call.
   `LEWCO CONTRACTING` · Patrick Lewis · **+1 253 677 8727** · sole operator ·
   $2M cover · 25 years. 6–9am Manila = 3–6pm WA.

## Linked

[[handoff-2026-08-10]] · [[2026-08-09-the-write-was-overwriting-row-two]] ·
[[2026-08-09-the-scorer-measures-the-search-query]] ·
[[0015-med-spas-are-not-and-never-were-the-icp]]
