---
name: 0006-sdr-refocus-and-subtraction
description: "HermesClaw is an SDR: identity refocus, repository subtraction, GUI archival, channel rejections, north-star metrics"
type: decision
created: 2026-07-15
status: active
---

# ADR-0006 — HermesClaw is an SDR: identity refocus and repository subtraction

## Context

Owner directive (2026-07-14/15, final): HermesClaw's identity is **the best
autonomous AI SDR for OROVA's luxury-automotive-led ICP** — not a general AI
assistant, operating system, or desktop app. Three architecture reviews
converged on the same finding: **7 of the 9 worker lanes already ARE the SDR
pipeline** (hunt → enrich → outreach → replies → call escalation → reporting →
learning), so the refocus is ~80% subtraction of everything around the SDR and
~20% hardening of the weak stages (qualification, intelligence depth, learning
volume — the last blocked by send volume, not architecture).

## Decision

1. **North-star metrics** (in order): qualified prospects found → verified
   direct contacts → positive replies → **meetings booked** (the SDR's metric;
   closing is the founder's stage). Every change must move one of these.
2. **Repository subtraction** (this ADR's batch): delete `openclaw_instance/`
   (abandoned clone; its 7 orphan git-submodule links caused the standing CI
   warning), dead skills `meta_ads_skill.py` + `scheduler_skill.py` (zero
   callers since April; their advertised-but-undispatched tool schemas removed
   from `definitions.py`/`soul.py`), root artifacts (`google_debug.html`,
   `hermesclaw_files.txt`, `make_blueprint.zip`), `runtime.txt` (contradicted
   the Dockerfile's Python version), `src/pages/Setup/index.original.tsx`.
3. **Electron GUI archival** (owner-approved): `electron/`, `src/`,
   `HermesClaw/` mirrors and their build/CI surface leave this repo to an
   archive branch (`archive/electron-gui`). The repo becomes the SDR:
   `app/ + knowledge/ + vault/ + mission-control/ + scripts/ + tests/`.
   Rationale: not the revenue path; ~half the repo bulk; carried most of the
   51 high Dependabot findings; its CI (3-OS Electron E2E per push) cost real
   firefighting for a surface no prospect sees. Fully reversible from the
   archive branch.
4. **Channel rejections** (standing, with legal grounds): no LinkedIn
   *automation* (platform ToS → account-ban risk; AI-drafted/human-sent is the
   compliant path later); no cold SMS (TCPA). Email + voice (Retell) remain
   the channels; the 5-touch cadence law is unchanged.
5. **Qualification becomes deterministic** (shipped alongside this ADR):
   `score_lead_icp()` replaces the flat-50 scorer — scoring only on fields the
   pipeline actually collects, with documented weights. CSV import gives the
   Scout a second, quota-free source.
6. **The target architecture** is the Pipeline Blackboard design (2026-07-15
   session): a Prospect state machine with agents owning single transitions,
   communicating through the DB and a unified event log. Adopted as the north
   star; built incrementally (event log first, as ADR-0007 when implemented),
   never as a rewrite.

## Consequences

**Easier:** the repo reads as what it is (an SDR); CI is lighter and greener
(submodule warning gone; Electron E2E leaves with the GUI); the Dependabot
surface shrinks by the GUI's share; lead ranking is real, so "email the best
10" means something; new prospect sources don't depend on SerpAPI quota.

**Harder / given up:** the desktop GUI stops evolving in this repo (archive
branch preserves it; restoring = branch merge); the generalist-assistant
ambitions are explicitly dead; any future channel beyond email/voice needs a
compliance case before code.

## Linked

- [[0004-obsidian-brain-and-skill-improvement]] · [[0005-canonical-knowledge-facts-and-projection]]
- Owner directives 2026-07-14/15 (SDR refocus, execution approval)
- The Pipeline Blackboard design (session 2026-07-15; to become ADR-0007 with
  the event-log implementation)
