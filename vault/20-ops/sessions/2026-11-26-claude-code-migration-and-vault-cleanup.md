---
name: 2026-11-26-claude-code-migration-and-vault-cleanup
description: Moved OROVA's agent setup from Codex to Claude Code, adopted the master brief, cleaned up the vault
type: session
created: 2026-11-26
status: done
---

# 2026-11-26 — Codex → Claude Code migration and vault cleanup

## What changed (committed on branch `claude/affectionate-fermi-3bgi1v`; not merged, not deployed)

**Claude Code setup**
- `CLAUDE.md` is now the single agent entry point. It covers the session-start reading order, the brief's hard boundaries, cloud-session limits, the Codex `AGENTS.md` engineering rules merged in, and corrected test instructions.
- `AGENTS.md` became a 6-line pointer to `CLAUDE.md`, so Codex/Cline/Kilo read the same rules (single source of truth).
- New project skill `.claude/skills/orova-start/` (`/orova-start`) runs the read-only session-start checklist.
- Mark's master continuation prompt was adopted as [[operating-brief]]. The Sheet link and local Windows path were left out because the repo is public.

**Vault cleanup**
- [[active-context]] went from 484 lines (a stack of dated callouts) to a short current-state note with a verification-date status board. Nova's planner reads its first ~2,000 chars, so the key facts now sit at the top. The old stack is preserved as [[active-context-history-2026-07-to-10]].
- 15 superseded docs moved to `90-docs/archive/` with frontmatter and an "archived" banner: the Electron/HuggingFace/Oracle guides, the May 2026 "production ready" reports, the full-code export, an unrelated model system-prompt dump, and the root `claude-desktop-prompt.txt`.
- 13 notes that had no frontmatter now carry it.
- 60 broken wikilinks were fixed (mostly a `session-` prefix the filenames never had).
- [[Home]] was rewritten: Claude instead of Codex, all 23 ADRs, no links to non-existent folders, and auto-generated `vault_pull` folders explained.
- [[90-docs/README|Docs index]] was rebuilt.
- `STATUS`, both `progress` notes and `roadmap` are frozen as historical, with a pointer banner.

## Verified today
- Full suite: **1,807 passed, 1 skipped** (Python 3.13 container). Knowledge gate and secrets gate are clean.
- Without `pytest-asyncio`, 122 async tests fail spuriously. CI installs it separately, and `CLAUDE.md` now says so.

## Environment set up (later the same day)
- Created a personal Claude Code environment, **orova-nova**. It allows `orova-nova.onrender.com` plus package registries, and its setup script installs the requirements, `pytest` and `pytest-asyncio`. The script is unproven until a fresh session starts on it.
- **Render `/health` live-verified 07:29 UTC:** Operational, build `deb59605cfa5`, db ok, memory ok.
- The dashboard key (a network secret for the `X-API-Key` header) is not yet saved. Mark is fetching it from Render's Environment page. The lead reconciliation needs it.

## Could not verify (blocked in this cloud session)
- **Canonical Google Sheet:** both Drive connectors were unavailable (one needs re-sign-in, one has an auth incompatibility). The lead reconciliation has not started.
- **OneDrive vault:** no computer attached. Notes written there after 2 Oct (e.g. the Oct 16–20 deploy verification, `2026-09-28-instagram-offline-manager`) are **not in the repo**. They need to be copied into `vault/` locally and committed.

## Unresolved links (target notes exist only locally, or never existed)
`handoff-2026-08-02`, `handoff-2026-08-09`, `handoff-2026-08-10`, `2026-08-09-the-write-was-overwriting-row-two`, `session-2026-07-17-sunday-return-plan`, `drive-oauth-token-expired`, `groq-gemini-free-tier-limits`. The `strategy-snapshot` link resolves after the first `vault_pull.py`.

## Next action (exactly one)
Mark: in the OneDrive checkout, pull this branch once merged, commit any vault notes written there since 2 Oct, then re-sign-in to Google Drive in the claude.ai connector settings. The next session can then do the Sheet-vs-DB lead reconciliation.
