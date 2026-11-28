---
name: session-2026-11-28-repo-hygiene-and-context-refresh
description: Claude Code session — GitHub inbox cleared, stale-branch audit, active-context refreshed to live truth
type: session
created: 2026-11-28
status: done
---

# Session: repo hygiene and context refresh (2026-11-28)

## What changed

- **PR #218 merged** (notes only). Render `/health` Operational, build `9a805746ffb0`, db ok, memory ok. **Live-verified 28 Nov 2026 06:23 UTC.**
- **GitHub inbox:** 0 open PRs, 0 open issues, CI green.
- **Stale branches audited (not yet deleted).** 63 remote branches date from before the history rewrite and share no history with `main`.
  - 56 point at exactly the head that was merged through their PR.
  - 7 do not, and each was checked:
    - `feat/ad-signal-detector` and `claude/orova-nova-handoff-09a8fa` only add commits merged elsewhere (#110, #158).
    - `feat/model-upgrade`, `docs/handoff-2026-08-09` and the `09a8fa` head were closed PRs, so GitHub keeps them on the PR.
    - `ci/build-repro` is a one-off July Render-diagnose workflow, never merged.
    - `claude/new-session-m7vlsn` and `docs/handoff-2026-08-02` are July/Aug handoff notes superseded by the current vault.
  - All 63 are safe to delete. Deleting `fix/redact-prospect-pii` and `security/scrub-leaked-key` also removes branch refs that still reach the old commits with prospect data and the leaked key.
  - **Blocked:** the cloud session can only push to its own branch (deletion returns 403), and the GitHub tools have no delete-branch call. Mark deletes them locally.
  - Keep: `main`, `gh-pages` (Pages site), `archive/electron-gui`, `master` (the original May 2026 codebase, kept as an archive).
- **`active-context.md` refreshed.** Its top ~2,000 chars feed Nova's planner. It still said:
  - build `abd922752dee`
  - "rotate the exposed dashboard key" as the next priority
  - the web stack as "Draft PR, not merged or deployed"
  - Telegram token rotation as pending

  All four were stale; they're corrected to the verified 28 Nov state.

## Why

Nova reads the top of active-context as current truth. Stale facts there become confident, wrong Telegram reports, the failure mode [[0022-learning-observations-and-no-age-only-pruning]] exists to prevent.

## Follow-ups

- [ ] Mark: delete the 63 stale branches (one command in the chat handoff, or the GitHub branches page) and enable Settings → General → "Automatically delete head branches".
- [ ] Mark: archive the live Instagram posts with unsupported claims (27 Aug "47 qualified calls" first).
- [ ] Mark: reconnect Meta in Make and Google Calendar.
