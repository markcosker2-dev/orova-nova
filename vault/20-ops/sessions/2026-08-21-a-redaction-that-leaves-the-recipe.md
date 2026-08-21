---
name: 2026-08-21-a-redaction-that-leaves-the-recipe
description: The replacement dashboard key leaked through the vault, not the code — invisible to every scanner rule by construction. And the handoff that withheld the literal explained how to derive it.
type: session
created: 2026-08-21
status: active
tags: [lesson, secrets, security, visibility, documentation]
---

# A redaction that leaves the recipe is not a redaction

> [!abstract] One line
> The `DASHBOARD_API_KEY` that replaced the 2026-08-05 leak spent two weeks in
> plaintext in **seven tracked markdown files on a public repo** — and the one
> document that carefully withheld the literal explained, in the next sentence,
> how to derive it from the key it replaced.

## What was actually true

The handoff framed the public-repo problem as prospect PII in merged PR diffs.
That was true and it was the smaller half. Verified unauthenticated:

```
raw.githubusercontent.com/.../main/vault/90-docs/handoff-2026-08-06.md -> 200
raw.githubusercontent.com/.../main/vault/90-docs/handoff-2026-08-20.md -> 200
```

Not history — the **current tree**. One of those lines annotated the key as
working and named the file it lived in. It gates `/api/leads`,
`/api/agents/run`, `/api/actions/hunt-leads`, `send-emails` and
`approve-email`. The gate itself was never broken: `403` unauthenticated,
verified. The key was simply published beside it.

## Why the scanner could not see it

Not an oversight. The value failed **three independent checks in turn**:

| rule | why it could not fire |
|---|---|
| `_ASSIGN_RE` | requires a *quoted* literal; `KEY=value` in markdown is unquoted |
| length floor | 20-char minimum; the value was 9 |
| `_looks_like_credential` | needs 3 character classes; the value had 1 |

Rule 2 is deliberately conservative and the module docstring says why — *"a
scanner that cries wolf gets disabled, and a disabled scanner is worse than
none"*. That reasoning is correct and should not be reversed. The burned-literal
rule exists precisely to cover the low-entropy case rule 2 must ignore. It had
simply never been told about this value.

> **The leak path was documentation.** `.env` is gitignored and has never been
> committed. Every control was aimed at code; the secret walked out through
> prose.

## The part that would have survived the fix

`handoff-2026-08-20.md` withheld the literal on purpose, with a good reason
given inline — and then wrote that the current key was *"that same string with
one segment removed"* from a blocklisted value printed at a named line number.

Redacting the seven literals and leaving that sentence would have produced a
tree that passes the scanner and still tells a reader the key.

> **A precise description leaks a secret as well as a paste does.** The scanner
> can only ever match values. Nothing will flag a recipe.

## Visibility: the timeline was wrong, and it mattered

The handoff recorded the repo as going public again *on 2026-08-20*. It didn't.
GitHub's public event stream carries exactly one `PublicEvent` for this repo,
and its `created_at` field is useless — it echoes the repo's **creation** date
(`2026-04-02`). Its **event id** is not:

| event id | timestamp | what |
|---|---|---|
| 13325780466 | 2026-08-15 08:49:22Z | #176 merged — last event before the gap |
| **13328350373** | — | **PublicEvent (private → public)** |
| 13348132160 | 2026-08-16 06:27:15Z | next repo activity |

Interpolating the id rate puts the flip at **≈ 2026-08-15 11:20Z ≈ 19:20
Manila** — about 2½ hours after the repo was set private. It was private for one
evening. `2026-08-20` was the date somebody *noticed*.

Five days of "the key is exposed but we're private" that never happened.

> **A timestamp field is not evidence of when something happened.** Two ID
> sequences are interleaved in that stream, so ordering only holds within one.

## Two things the state doc got wrong

- **"1417 tests pass"** is really **1417 tests exist**. A full local run gives
  `1407 passed, 10 failed`. All ten pass in isolation and pass when their three
  files run together, so it is order-dependent pollution, not a defect — and
  **CI on Linux is green**, so the baseline is real there. But `pytest tests -q`
  on Windows does not reproduce the number the docs claim.
- **CodeQL cannot be turned off by deleting a file.** #177 removed the workflow
  and CodeQL kept running: it is GitHub **default setup**, a dynamic workflow at
  `dynamic/github-code-scanning/codeql` with no file in the tree. On a private
  repo without GHAS it now fails on every push to `main`, and the REST endpoint
  to disable it returns `403` because the feature is unavailable. **Only the
  repo Settings UI can clear it.** A permanently red check trains you to ignore
  checks — the same failure mode `check_secrets.py` was written to avoid.

## The checklist this earns

When a credential is found in the tree:

1. Redact every literal — `git grep` the value, not just the files you expect
2. **Re-read the surrounding prose for a derivation**, not just the value
3. Add it to `BURNED_LITERALS` — substring match, no length floor, no quoting
4. Confirm the entry actually fires, and that the *other* rules provably could
   not, so a future tightening is not mistaken for coverage
5. Rotate it. Steps 1–4 stop it spreading; none of them un-burn it.

## Linked

[[2026-08-16-a-whitelist-is-a-silent-contract]] · [[handoff-2026-08-20]] ·
[[active-context]]
