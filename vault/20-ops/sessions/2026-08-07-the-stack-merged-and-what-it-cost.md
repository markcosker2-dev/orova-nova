---
name: session-2026-08-07-the-stack-merged-and-what-it-cost
description: All 18 PRs merged and deployed; the redeploy wiped the ephemeral DB and exposed that the Sheets backup held only 4 rows, 3 of them fixtures. Drive OAuth is dead again.
type: session
created: 2026-08-07
status: done
tags: [merge, deploy, durability, data-loss, retell]
---

# Session: the stack merged, and what it cost (2026-08-07)

Companion to [[session-2026-08-07-retell-tool-hallucination-and-the-reverse-landmine]].

## The merge

All 18 open PRs merged to `main` on owner instruction ("fix what you can fix,
merge what you can merge"), which suspended the standing *Mark merges, the
agent verifies* rule for this task only.

Order held: `129 → 130 → 132 → 127 → 128 → 131`, then `133 → 134 → 136`, then
`138 · 137 · 139 · 140 · 141 · 142 · 143 · 144 · 135`.

**Result: 0 open PRs. `1116 tests pass` on merged main; knowledge gate clean.
Production deployed and healthy.** All 5 stranded vault docs are now on main,
so the fragmentation that made every new chat start blind is resolved.

### Two things went wrong in the merge itself

**1. #134 and #136 were a stacked chain and I did not check base branches.**
#134's base was `fix/registry-by-state` — #133's branch — not `main`. Merging
#133 with `--delete-branch` deleted that base, and **GitHub auto-closed #134**.
A PR closed that way cannot be reopened even after restoring the base ref
(tried; `reopenPullRequest` refuses). The OR CCB work went in as **#145**
instead, from the same branch, rebased, 947 tests passing. #136 was retargeted
to `main` before it could cascade the same way.

**Lesson: check `baseRefName` on every PR before merging a stack, and do not
pass `--delete-branch` while any other PR still targets that branch.**

**2. #136 failed CodeQL** on two `py/incomplete-url-substring-sanitization`
alerts in `tests/test_website_resolution.py`. False positive —
`candidate_domains()` returns a **list**, so `"x.com" in cands` is element
membership, not a substring check. Rewritten as explicit `==` comparisons
rather than dismissing the alert; gate went green.

## What the deploy cost — 45 leads → 1

Render free tier has an **ephemeral disk**, so the redeploy came up on an empty
SQLite file. Production logs, verbatim:

```
♻️ Database appears empty. Attempting Google Drive snapshot restore...
[Vault] Restore failed: ('invalid_grant: Token has been expired or revoked.')
[LEAD-GATE] REJECTED lead: fixture/sample business name: 'Acme Remodeling Co'  ×3
♻️ Restored 1/4 leads from Google Sheets (leads only — learning data starts fresh)
```

**The deploy was the trigger; it was not the cause.** The Sheets tier held only
**4 rows, 3 of them test fixtures.** There was never a real backup of those 45
leads. The old ladder ran Sheets only `if not drive`, so every run where Drive
still worked *suppressed* the Sheets copy — and when Drive's token expired
there was nothing behind it. Render spins free-tier instances down on idle and
restores them on a fresh filesystem, so **any restart would have done this.**
The merge only made it happen while someone was watching.

**#127, merged in this same batch, is the fix**: Sheets is now Tier 1 and
unconditional, Drive demoted to an optional bonus tier. Verified after the
second deploy (#146): the surviving lead was restored from Sheets correctly.

What is actually gone is the learning data — memories and learned strategies —
which only the Drive snapshot carries. With 0 conversations ever, there was
nothing in it worth much. The leads themselves are re-discoverable: WA L&I and
OR CCB are free, keyless public registries.

> [!warning] Every deploy costs the learning data until Drive OAuth is fixed
> `invalid_grant` is the documented 7-day expiry, unresolved since 2026-07-29.
> The consent screen sits in **Testing**, which is why the token keeps dying.
> Re-authorising is not enough on its own — the consent screen must be
> **published** or this recurs every week.

## #146 — a real bug the review bot found, and got wrong

Kilo flagged `_person_from_principal` on #145 after merge.

**Its stated symptom was wrong.** It claimed `"SMITH JR, JOHN"` returned
`"John Jr"`. Running it, the actual output was **`"John Smith jr"`** — the
surname is not replaced; the suffix is appended and lowercased by
`.capitalize()`. **The underlying defect was real**: the comma branch filtered
suffixes out of the given-name half but never the surname half, while WA L&I
writes them on either side of the comma.

| input | before | after |
|---|---|---|
| `SMITH JR, JOHN` | `John Smith jr` | `John Smith` |
| `OBRIEN III, PATRICK` | `Patrick Obrien iii` | `Patrick Obrien` |
| `JR, JOHN` | `John Jr` | `""` |

These pass `_is_plausible_name` and get **spoken on a Retell call**. Fixed in
#146, 7 new parametrized cases, **1123 tests pass**.

**Still open, deliberately not fixed:** `.capitalize()` lowercases everything
after the first character, so `VAN DYKE, PETER` → `Peter Van dyke` and
`JUAREZ JUAREZ, ALVARO` → `Alvaro Juarez juarez`. That behaviour is *asserted*
in `test_wa_lni_registry.py`, so changing it is an owner decision rather than a
bug fix. It also reaches a call script.

## Follow-ups

- [ ] **Re-authorise Drive OAuth AND publish the consent screen.** Until then
      every deploy and every idle restart loses all learning data.
- [ ] **Repopulate the leads** — WA/OR registry discovery is free and keyless.
      Awaiting owner OK in case a paid lookup path is touched.
- [ ] **Decide on the `.capitalize()` surname mangling** (`Peter Van dyke`).
- [ ] **Approve the line-type lookup** (<$1) — 38 geographic numbers were
      queued before the wipe; re-derive after repopulation.
- [ ] **Rotate `<redacted>`.**
- [ ] **Sync `retell_pitch`/`retell_inbound` to the live Retell prompt
      verbatim** — now unblocked, #138 has merged. The repo is the stale copy.
- [ ] **Find the Cloudflare account holding `orova.io`** before 2026-09-28.
