---
name: orova-start
description: Session-start checklist for OROVA/Nova work. Reads the operating brief and active context, inspects git, re-checks reachable live state, and reports what is verified versus stale. Use at the start of any OROVA product, strategy, ops or architecture session, or when the user says "continue", "pick up where we left off", or "what's the state of OROVA".
---

# OROVA session start

Run this before changing anything. It is read-only: it never sends, deploys,
spends, publishes or edits live systems.

1. **Repo:** `git remote -v`, `git status`, `git branch --show-current`,
   `git log --oneline -10`. Note any uncommitted work and preserve it.
2. **Read, in order:** `vault/10-brain/operating-brief.md` (rules),
   `vault/10-brain/active-context.md` (state and verification dates), the 3
   newest files in `vault/20-ops/sessions/`, and the playbook under
   `vault/hermesclaw-orova/playbook/` if a judgment call is coming.
3. **Production learning:** if `.env` has `RENDER_EXTERNAL_URL` and
   `DASHBOARD_API_KEY`, run `python scripts/vault_pull.py` (idempotent).
   Otherwise say it was skipped.
4. **Live state, where reachable:** `python scripts/nova.py status` or
   `curl -s $RENDER_EXTERNAL_URL/health`. Compare the build SHA with
   active-context. If the host is blocked or a key is missing, report
   "unverified". Never guess.
5. **Report to Mark** in plain English, at most 10 lines: what's verified today,
   what's stale (with its last date), blockers, and exactly one recommended
   next action that fits the brief's priority order. Outreach stays paused
   unless he releases it.
