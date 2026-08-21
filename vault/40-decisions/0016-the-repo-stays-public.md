---
name: 0016-the-repo-stays-public
description: The repo is public on purpose — it is connected to Make.com. Recorded because the reason was never written down and the flag was flipped three times.
type: decision
created: 2026-08-22
status: active
tags: [decision, security, visibility, make-com]
---

# ADR-0016 — The repo stays PUBLIC

## Status

Accepted — owner decision, 2026-08-21.

## Context

`markcosker2-dev/orova-nova` was set **private** on 2026-08-15 as the agreed fix
for prospect PII in git history, then found public again, set private again on
2026-08-21, and found public again the same day.

Three flips, and **not one of them recorded a reason** — so every session that
opened the handoff treated public as an unexplained regression, re-derived the
whole PII argument from scratch, and flipped it back. The cost was never the
flag. It was that the reason lived only in Mark's head.

The reason: **the repository is connected to Mark's Make.com scenarios.**

## Decision

**The repo stays public.** Do not change repository visibility. If a future
session finds it public, that is the intended state — this ADR is the record.

## Consequences — accepted knowingly

- **Git history and merged PR diffs are world-readable.** A history rewrite
  does not reach PR diffs. Prospect PII in older diffs (notably #165) remains
  reachable and is accepted.
- **Any credential ever committed is permanently burned.** This raises
  `DASHBOARD_API_KEY` rotation from a chore to the top of the list: the burned
  value sits in 28 commits that anyone can read. #182 removed it from the
  current tree; nothing can remove it from history.
- **Never commit prospect PII or a live credential again.** `check_secrets.py`
  catches the second. Only a human catches the first.
- CodeQL is available again (free on public repos), so the #177 ruff gate and
  CodeQL now both run.
- Actions minutes are unmetered.

## Note

Make.com's GitHub connection authorises a GitHub app against selected
repositories and **does support private repos**, so public may not be strictly
required. Raised once, not pursued — the decision is the owner's and is not to
be re-litigated without him asking.

## Linked

[[handoff-2026-08-20]] · [[2026-08-21-a-redaction-that-leaves-the-recipe]] ·
[[active-context]]
