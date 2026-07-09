---
name: 0004-obsidian-brain-and-skill-improvement
description: live vault brain + continuous per-skill improvement design
type: decision
created: 2026-07-05
status: active
---

# ADR-0004 — Live bidirectional Obsidian brain + continuous per-skill improvement

## Context

ADR-0001 made `vault/` the shared brain but explicitly one-directional: production
knowledge reaches the vault through `scripts/vault_pull.py` polling the dashboard
API, "never via git pushes from Render" (Render's disk is ephemeral and has no git
credentials — that constraint still holds and this design does not challenge it).
Today's read side is also thin: agents never *read* the vault before acting; they
only read three DB-backed context sources injected by `app/core/planner.py` at
`_build_messages()` — `MemoryDistiller.retrieve_context()` (semantic facts),
`self_learning_loop.get_learned_skills()` / `get_preference_model()` (learned
workflows + prefs), and `AgentSoul` (persona/tool catalog). None of these touch a
markdown file.

Three separate learning systems already exist in `app/`, at different levels of
wiring:

| System | File | DB tables | Scheduled? | Vault-aware? |
|---|---|---|---|---|
| `StrategyOptimizer` / `ImprovementLoop` | `app/core/self_improvement.py` | `outreach_outcomes`, `learned_strategies` | **Yes** — `worker.py` Lane 8, every 6h | Read-only, via `vault_pull.py` → `strategy-snapshot.md` |
| `SelfLearningLoop` | `app/core/self_learning.py` | `execution_traces`, `learned_skills`, `user_preferences` | **No** — `record_trace`/`persist_knowledge` fire per-task from `planner.py`, but `run_cycle()` (pattern detection → skill crystallization) is **never called from anywhere** — confirmed by repo-wide search | No |
| `PatternReinforcer` | `app/core/pattern_reinforcer.py` | `learned_patterns` | **Yes**, but as an `asyncio.create_task()` fired once at app startup (`main.py:224`), not a `worker.py` schedule lane — so it runs once per process boot, not on a cadence | No |

`skill_forge.py` is a separate, already-solid gate (static AST screening →
sandboxed subprocess smoke test → Telegram approval) for *proposing brand-new
Python skills*, but it has no outcome tracking after activation and nothing
records *why* a forged skill was written or how it's performing.

`vault_skill.py` is a naming collision worth flagging explicitly: it is **not**
related to the Obsidian `vault/` folder at all — it's the Google-Drive SQLite
backup/restore system ("OROVA Survivability Layer"). Any new module introduced by
this design must avoid the name `vault_skill` to prevent confusion; see naming
below.

On the HermesClaw side (`electron/`, `src/`), there is no existing memory or
vault integration of any kind — confirmed by search. It's an OpenClaw-based
desktop shell (`Agents`, `Skills`, `Cron`, `OrovaDashboard` pages) with its own
runtime-lifecycle services (`hermesclaw-local-integration-service.ts`,
`hermes-openclaw-bridge-service.ts`) but no agent-memory hooks. Critically,
HermesClaw runs **locally on Mark's machine**, on the same disk as the
OneDrive-synced `vault/` folder — unlike Nova on Render, it can read/write vault
files directly with no network hop.

### External patterns researched

- **Reflexion** (Shinn et al., NeurIPS 2023 — [arxiv.org/abs/2303.11366](https://arxiv.org/abs/2303.11366),
  [github.com/noahshinn/reflexion](https://github.com/noahshinn/reflexion)):
  an agent converts scalar/binary outcome feedback into a short natural-language
  self-reflection, stored in episodic memory, and re-injected as context on the
  next attempt at the same/similar task — no weight updates. Maps directly onto
  "write a `## Why` note in the vault every time a strategy changes."
- **Voyager** (Wang et al. 2023 — [arxiv.org/abs/2305.16291](https://arxiv.org/abs/2305.16291),
  [github.com/MineDojo/Voyager](https://github.com/MineDojo/Voyager)): a skill
  library of small, composable, versioned functions, each indexed by an
  embedding of its natural-language description; on a new task the top-k most
  relevant skills are retrieved and injected into the prompt; every *successful*
  execution's code gets added back to the library. Maps onto skill-vault notes
  with a `description` frontmatter field good enough to retrieve on, plus
  "promote what wins, don't hand-curate."
- **Champion/challenger** (standard MLOps pattern — Snowflake, DataRobot,
  Databricks docs): champion = current best in production; challengers get a
  capped slice of traffic; a challenger that clears a statistical bar over
  enough samples is promoted; losers are retired. OROVA's `self_improvement.py`
  **already implements this exactly** (Wilson-lower-bound ranking +
  epsilon-greedy `select_strategy` + `evaluate_challengers` retirement) for
  strategy values (framework/send-hour/niche). The gap is only that (a) it isn't
  applied to *skills* (Python code, not string parameters) and (b) the
  champion/challenger *rationale* never reaches the vault.
- **Obsidian-as-agent-memory** (2025–2026 ecosystem scan): the dominant pattern
  is an MCP server exposing a vault as read/write/search tools over stdio, e.g.
  [bitbonsai/mcpvault](https://github.com/bitbonsai/mcpvault) (14 methods:
  `read_note`, `search_notes` with BM25, `write_note` with
  overwrite/append/prepend modes, `patch_note` surgical replace,
  `update_frontmatter`, zero auth, spawned as a local Node subprocess). This is
  a strong fit for **HermesClaw** (same machine as the vault) but does not
  solve **Nova's** problem: Nova runs on Render with no filesystem access to
  Mark's OneDrive vault and no ability to spawn a Node MCP subprocess against a
  path it can't see. Nova's write-back must keep going through its existing
  dashboard-API pattern (below).

## Decision

Two additive tracks, both building on code that already exists rather than
replacing it. **No existing table, lane, or file is removed.**

### Track A — Live bidirectional Obsidian brain

**Principle:** Nova (Render, ephemeral) never touches the vault directly. It
exposes what it knows over its existing dashboard API; a local sync step
(cron/scheduled task on Mark's machine, extending `vault_pull.py`) is the only
thing that writes vault files from Nova's side — preserving ADR-0001's "no git
push from Render" rule. HermesClaw (Electron, local) reads/writes the vault
**directly on disk**, no API hop needed, because it already runs on the same
machine as the vault folder.

**A1. Read side — Nova reads vault context before acting (new, small)**

Add `app/core/vault_context.py` (new file — deliberately not named
`vault_skill.py`, which is taken):

```python
# app/core/vault_context.py
"""Read-only vault context injector.

Loads a small, capped set of curated markdown notes from vault/ into the
planner's system prompt — the read half of the bidirectional brain. Runs
locally only: on Render, VAULT_DIR won't exist, so this degrades to "" with
no error (same fail-open posture as everything else in planner.py).
"""
import os
from pathlib import Path

VAULT_DIR = Path(os.getenv("VAULT_DIR", "vault"))
MAX_CHARS_PER_NOTE = 2000
ALWAYS_READ = [
    "10-brain/active-context.md",
    "10-brain/strategy-snapshot.md",
]

def get_vault_context(niche: str = "", client_id: int = 0) -> str:
    """Return a capped markdown digest for system-prompt injection.
    Sync + pure I/O — safe to call from an async context via asyncio.to_thread."""
    if not VAULT_DIR.exists():
        return ""  # Render: no local vault — fail open, silent
    chunks = []
    for rel in ALWAYS_READ:
        p = VAULT_DIR / rel
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_PER_NOTE]
            chunks.append(f"--- {rel} ---\n{text}")
    # niche-scoped skill note, e.g. vault/50-skills/find_leads.md
    if niche:
        skill_note = VAULT_DIR / "50-skills" / f"{niche}.md"
        if skill_note.exists():
            chunks.append(skill_note.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_PER_NOTE])
    return "\n\n".join(chunks)[:6000]  # hard cap: this is a supplement, not the context
```

Wire into `app/core/planner.py` `_build_messages()`, right next to the existing
`self_learning_loop` injection block (~line 425-441): call
`get_vault_context(...)` inside the same `try/except` pattern, append to
`system_content` as a `=== VAULT BRAIN ===` block. This is the only planner.py
change and it's additive (one more `try/except`-wrapped string append, same
shape as the block already there).

Because Render has no local `vault/` folder, this is a **local-only
enhancement** today — it activates automatically on Mark's dev machine and any
future non-Render/self-hosted deploy, and silently no-ops on Render. That's an
acceptable interim state (see Phase 2 below for closing the gap).

**A2. Write side — Nova's learnings reach the vault (extend, don't replace,
`vault_pull.py`)**

`vault_pull.py` already pulls `/api/leads`, `/api/memory` (briefs), and
`/api/learned_strategies` into markdown. Extend it with two more sections,
each following the exact `_write_if_changed` idempotent pattern already there:

1. **Skill performance digest** — new endpoint
   `GET /api/skill_health` in `app/core/hermesclaw_endpoints.py` (same file,
   same `_require_api_key` gate as the existing `/learned_strategies` route),
   returning per-skill outcome rollups (see Track B's `skill_outcomes` table).
   `vault_pull.py` writes `vault/10-brain/skill-health.md` — one row per
   skill: name, champion version, win rate, sample size, last-changed-and-why.
2. **Improvement rationale log** — every time `ImprovementLoop.run()` or the
   new skill-challenger cycle (Track B) promotes/retires something, it writes
   one row to a new `improvement_log` table (below) with a short AI-written
   "why" sentence (Reflexion-style verbal reflection, reusing
   `StrategyOptimizer.generate_improvement_report`'s existing prompt pattern).
   `vault_pull.py` appends new rows (by id, idempotent) to
   `vault/20-ops/improvement-log.md` as a running changelog — this is the
   vault-side Reflexion trace: short natural-language "what changed and why"
   entries an agent (or Mark) can read back before touching that skill again.

Both are additive GET endpoints behind the existing dashboard-API-key gate —
no new auth surface, no new connector.

**A3. HermesClaw reads/writes the vault directly (new, local-only)**

Because HermesClaw is a local Electron app on the same machine as the vault
folder, it does not need Nova's API round-trip. Add a small main-process
service `electron/runtime/services/vault-brain-service.ts` (new file) that:

- Resolves the vault path the same way `hermesclaw-local-integration-service.ts`
  resolves other local paths (via `getAllSettings()`/paths util — a new
  `vaultPath` setting, defaulting to `<repoRoot>/vault` in dev, user-configurable
  in packaged builds since the vault may not be co-located with the app install).
- Exposes two IPC-callable functions mirroring the read/write shape already
  used elsewhere in `electron/main/ipc-handlers.ts`: `vault:read(relPath)` and
  `vault:write(relPath, content, mode)` (mode: overwrite/append, mirroring
  mcpvault's pattern) using plain `node:fs` — no MCP subprocess needed for a
  same-machine, single-consumer case; that complexity only pays off if a
  *third* local process needs concurrent vault access.
- HermesClaw's own planner/agent-loop equivalent (wherever it assembles a
  system prompt — this needs its own short scoping pass in a future session,
  since it wasn't in scope to trace exhaustively here) calls `vault:read` on
  the same curated file list as `ALWAYS_READ` above before dispatching a task,
  and calls `vault:write` to append a session note
  (`vault/20-ops/sessions/YYYY-MM-DD-<slug>.md`, using the existing
  `_templates/session.md` template) after a task completes.
- If/when a shared vault-access daemon is wanted (e.g. a background HermesClaw
  process and Nova's local dev process both touching the vault at once), swap
  the direct-`fs` approach for spawning `mcpvault` as a child process — the
  interface (`read_note`/`write_note`/`search_notes`) is a drop-in replacement
  for the same call sites. Not needed for Phase 1.

**Format contract (both directions, both apps):** every note keeps the
frontmatter block CLAUDE.md already mandates
(`name`/`description`/`type`/`created`/`status`). Agent-written notes always
carry `status: active` and a trailing `*Written by <agent-id> on <ISO date>*`
line so a human skimming the vault can tell machine-authored notes from
Mark's own — this is the one new convention this ADR adds to CLAUDE.md's rules.

### Track B — Continuous per-skill improvement loop

**Principle:** reuse the champion/challenger machinery in
`self_improvement.py` verbatim — it's already correct (Wilson bound,
epsilon-greedy selection, sample-gated retirement) — but generalize its unit
from *a string parameter* (email framework name, send hour) to *a versioned
skill implementation*. Wire the already-built-but-unscheduled
`SelfLearningLoop.run_cycle()` into the schedule. Give `skill_forge.py` an
outcome-tracked lifecycle instead of "draft → approve → run forever unmeasured."

**B1. Schema — `skill_outcomes` + `skill_versions` (new tables)**

Add to `app/core/_db_base.py`, same file/pattern as the existing
`outreach_outcomes`/`learned_strategies` DDL block (~line 175-216):

```sql
CREATE TABLE IF NOT EXISTS skill_versions (
    id TEXT PRIMARY KEY,              -- e.g. "find_leads_v3.a1b2c3"  (name + code hash prefix)
    skill_name TEXT NOT NULL,         -- e.g. "find_leads_v3" — groups versions of one skill
    version_label TEXT NOT NULL,      -- "champion" | "challenger_1" | "challenger_2" ...
    code_hash TEXT,                   -- sha256 prefix, for forged skills; NULL for built-in skills
    source TEXT NOT NULL DEFAULT 'builtin',  -- 'builtin' | 'forged' | 'skill_creator'
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS skill_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    version_id TEXT NOT NULL,          -- FK -> skill_versions.id
    outcome TEXT NOT NULL,             -- 'success' | 'degraded' | 'error' | 'timeout'
    latency_ms REAL,
    client_id INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_skill_outcomes_name ON skill_outcomes(skill_name, version_id);

CREATE TABLE IF NOT EXISTS improvement_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,        -- 'strategy' | 'skill'
    subject_name TEXT NOT NULL,
    action TEXT NOT NULL,              -- 'promoted' | 'retired' | 'proposed' | 'activated'
    rationale TEXT,                    -- AI-written one/two-sentence why (Reflexion-style)
    client_id INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Every `run()`/`evaluate_challengers()` cycle (existing, in
`self_improvement.py`) already computes exactly the values needed to fill
`improvement_log` — this is a one-line `INSERT` added at each existing
retire/promote decision point, not new logic.

**B2. Wiring — three concrete code changes**

1. **Instrument skill call sites.** The natural interception point is
   `planner.py`'s existing tool-execution loop (wherever it calls a tool from
   `TOOLS`/`app/skills/definitions.py` and gets a result/exception back — this
   is the same loop that already builds `tool_call_history` for
   `_record_learning_trace`). Add one `OutcomeTracker`-style call
   (new `SkillOutcomeTracker.record(skill_name, version_id, outcome,
   latency_ms, client_id)` in `self_improvement.py`, sibling class to
   `OutcomeTracker`) right where `tool_call_history` already gets appended.
   Zero new call sites in skill files themselves — instrumentation lives in
   the one place that already sees every tool call.
2. **Schedule the missing cycle.** In `worker.py`, change `self_improvement_job`
   (Lane 8, already every 6h) to also call `self_learning_loop.run_cycle()`
   — the pattern-detection/skill-crystallization method that has existed
   since `self_learning.py` was written but is never invoked. This is a
   one-line addition to an existing function:
   ```python
   def self_improvement_job():
       logger.info("[LANE 8] Triggering Self-Improvement Loop...")
       from app.core.self_improvement import ImprovementLoop
       from app.core.self_learning import self_learning_loop
       loop = ImprovementLoop()
       _run_async(loop.run())
       _run_async(self_learning_loop.run_cycle())  # NEW: was defined, never scheduled
   ```
   Also move `PatternReinforcer.run_cycle()` off its startup-only
   `asyncio.create_task()` in `main.py` and into this same Lane 8 job (or its
   own `schedule.every(6).hours` line) — right now it only ever runs once per
   process boot, which on Render's free tier (frequent cold restarts) means
   it barely runs at all in practice.
3. **Champion/challenger for skill *code*, not just strategy *strings*.**
   Add `SkillChallengerEvaluator` (new class in `self_improvement.py`,
   sibling to `ImprovementLoop`) that runs in the same Lane 8 cycle:
   - Reads `skill_outcomes` grouped by `(skill_name, version_id)`, computes
     Wilson bound per version using the **existing** `wilson_lower_bound()`
     function (no new math).
   - If a `challenger_N` version's Wilson bound beats the current `champion`
     with sample_size ≥ 20 (same thresholds `evaluate_challengers` already
     uses for strategies): flip `version_label` — old champion becomes
     `retired` (`active=0`), challenger becomes `champion`. Write one
     `improvement_log` row with an AI-written rationale.
   - This only *selects between already-activated* versions — it does not
     write code. Where the challenger version comes from is Track B3/B4.

**B3. `anthropic-skills:skill-creator` as the authoring path for new/challenger
skills**

Today, `skill_forge.py`'s `propose_skill(name, description, code)` expects
Nova to hand it Python source directly — there's no structured authoring
step, just static screening of whatever code arrives. Insert
`anthropic-skills:skill-creator` (an installed skill in this Claude Code
environment, listed among available skills — not a library import) as a
**human/Claude-Code-session step**, not a runtime Nova capability:

- When Mark (or a Claude Code session working in this repo) decides a new
  skill or a challenger rewrite of an existing skill is worth trying, invoke
  `skill-creator` to scaffold/author it properly-versioned (SKILL.md-style
  frontmatter: `name`, `description` good enough for retrieval — directly
  reusing Voyager's "retrieve by embedding of description" idea for the
  future `50-skills/` vault notes in A1).
  Skill-creator produces the *design*; the actual runnable artifact for Nova
  still has to be a plain Python module because Nova's runtime executes
  `app/skills/*.py` files and `data/learned_skills/*.py` forged skills, not
  SKILL.md bundles (Nova is not itself a Claude-Code-style agent that loads
  SKILL.md at runtime — this is a documentation/design-authoring aid across
  sessions, not a new runtime dependency).
- Concretely: the workflow for "improve `find_leads_v3`" becomes (a) use
  skill-creator in a Claude Code session to draft the challenger's spec +
  code, informed by reading `vault/10-brain/skill-health.md` (from A2) for
  what's currently underperforming and why; (b) hand the resulting code to
  `skill_forge.propose_skill()` exactly as today (AST screen → sandbox smoke
  test → Telegram approval); (c) on activation, register it as
  `skill_versions(version_label='challenger_1', source='skill_creator')`
  instead of immediately replacing the champion; (d) B2's
  `SkillChallengerEvaluator` decides, from real production outcomes, whether
  it actually wins before it becomes champion.
- This keeps `skill_forge.py`'s three-gate safety model (screen → sandbox →
  human approval) completely intact — B3 only adds a better-curated
  *authoring* step before code ever reaches `propose_skill()`, and B2 adds a
  *measured* adoption step after activation instead of "activated = now live
  forever unmeasured."

**B4. Existing (non-forged) skills get improved safely — same loop, no
special-case**

For the 52 existing `app/skills/*.py` files, "improving a skill" almost never
means editing the file that ships to Render (that's a normal PR, out of this
design's scope). What Track B *does* let happen autonomously is:

- **Parameter-level improvement** (already shipped): `learned_strategies`
  already covers this — email framework, send hour, niche. No change needed.
- **Prompt/config-level improvement**: skills that call `UnifiedAIClient`
  with a hardcoded prompt (e.g. `content_writer.py`, `copywriting_skill.py`)
  can register *prompt variants* as `skill_versions` rows
  (`source='builtin'`, `version_label='challenger_N'`, code_hash pointing at
  a prompt-variant string stored in `learned_strategies`-style key/value,
  not actual new .py files) and go through the exact same B2 evaluator. This
  is the low-risk 80% case and needs zero sandboxing since no code changes —
  just a different prompt string selected the same epsilon-greedy way
  `select_strategy` already works.
- **Code-level improvement** (rarer, higher-value): goes through B3's
  skill-creator → skill_forge → challenger pipeline above. This is
  deliberately the *only* path that touches actual `.py` code, and it never
  touches the original file — the challenger lives in
  `data/learned_skills/` as its own module and `use_forged_skill`-style
  dispatch picks champion vs. challenger the same way `select_strategy`
  already does for strategy values.

## Phased rollout

**Phase 1 (ship first — pure additive, no new external dependency):**
1. `app/core/vault_context.py` (A1) + planner.py wiring (~10 lines).
2. `skill_outcomes`/`skill_versions`/`improvement_log` DDL in `_db_base.py` (B1).
3. `SkillOutcomeTracker` in `self_improvement.py` + one instrumentation call
   site in `planner.py`'s tool loop (B2.1).
4. Schedule fix: `self_learning_loop.run_cycle()` + `PatternReinforcer` into
   Lane 8 (B2.2) — this alone activates two already-written systems that are
   currently dead code paths.
5. `vault/10-brain/skill-health.md` + `vault/20-ops/improvement-log.md`
   sections added to `vault_pull.py`, plus the matching `/api/skill_health`
   GET route in `hermesclaw_endpoints.py` (A2).

Ship criteria: existing 150-test baseline still green, plus new tests for
`vault_context.get_vault_context()` (missing-dir fail-open, cap behavior) and
`SkillOutcomeTracker.record()`/`SkillChallengerEvaluator` (mirroring the
existing `test_owner_finder.py`-style coverage pattern).

**Phase 2 (skill challenger loop live):**
6. `SkillChallengerEvaluator` in `self_improvement.py`, wired into Lane 8
   (B2.3).
7. First real skill-creator → skill_forge → challenger cycle run manually
   end-to-end on one low-risk skill (candidate: a `content_writer.py` prompt
   variant — no sandboxing risk) to validate the full loop before trusting
   it on anything outreach-critical.

**Phase 3 (HermesClaw side + closing the Render gap):**
8. `electron/runtime/services/vault-brain-service.ts` + IPC read/write (A3).
9. Trace HermesClaw's own prompt-assembly path (not scoped in this
   research pass) and wire vault reads/session-note writes into it.
10. Decide whether to close Nova's Render-side vault-read gap (A1 currently
    no-ops on Render). Two options, both requiring something we don't have
    today: (a) a Render **persistent disk** add-on so `vault/` (or a curated
    subset) actually exists on the Render filesystem and can be periodically
    synced onto it — costs money, breaks the "$0 Render free tier" constraint
    in CLAUDE.md/active-context.md, needs Mark's explicit sign-off; or
    (b) a bundle-at-deploy approach (commit a curated `vault-digest.json`
    generated by a pre-deploy script, so Nova reads a frozen snapshot instead
    of a live vault) — no new cost, but the snapshot goes stale between
    deploys. Recommend (b) first since it needs no new spend.

## What needs a key/connector we don't have

- **Render persistent disk** (Phase 3, option a) — paid add-on, not available
  on the free tier Nova currently runs on. Not required for Phases 1-2.
- **A vector/embedding index for vault notes** — Voyager's retrieval
  (embed descriptions, fetch top-k) needs *some* embedding model. Nova
  already has `mem0_skill.py` and `UnifiedAIClient` in the repo; whether
  either currently has a live embeddings-capable key wasn't verified in this
  pass (the vault confirms all three LLM providers were dead as of
  2026-07-04 and Groq was just fixed 2026-07-05 — text-only). Phase 1-2 avoid
  this entirely by using a small fixed file list (`ALWAYS_READ`) instead of
  semantic retrieval; only revisit embeddings if the vault grows past what a
  hand-picked file list can cover.
- **mcpvault (or similar Obsidian MCP server) as a Node runtime** — not
  needed for Phase 1/3 as scoped (direct `node:fs` suffices for a
  single-consumer, same-machine case), but flagged in A3 as the drop-in
  upgrade path if a second local process needs concurrent vault access.
- Nothing in Track A or B requires a new paid API key beyond what's already
  in `.env`/Render env (`DASHBOARD_API_KEY`, `RENDER_EXTERNAL_URL` — both
  already required by `vault_pull.py` per CLAUDE.md).

## Consequences

- **+** Both learning systems that already exist but sit dormant
  (`self_learning_loop.run_cycle()`, `PatternReinforcer` past first boot)
  start actually running, with zero new architecture — just scheduling.
- **+** Champion/challenger, already proven correct for strategy *values*,
  extends to skill *code* and *prompts* via the same Wilson-bound math,
  same epsilon-greedy selection, same retirement rule — no new algorithm to
  validate.
- **+** The vault gains a genuine write-back path (`skill-health.md`,
  `improvement-log.md`) without breaking ADR-0001's no-git-push-from-Render
  rule — everything routes through the dashboard API exactly like leads and
  briefs already do.
- **+** `skill_forge.py`'s three-gate safety model (screen/sandbox/approval)
  is untouched; Track B only adds measurement before and after it, never
  weakens it.
- **−** Nova's vault *read* side is local-machine-only until Phase 3 resolves
  the Render gap — an honest limitation, not hidden.
- **−** HermesClaw's own prompt-assembly integration point needs its own
  scoping pass (not traced exhaustively in this read-only research session)
  before A3's IPC calls can actually be wired into a live system prompt.
- **−** Three new tables (`skill_versions`, `skill_outcomes`,
  `improvement_log`) plus two new vault files are one more thing to keep an
  eye on for the 512MB Render tier — small integer/text tables, low risk, but
  worth checking `PRAGMA page_count` after a few weeks live per the project's
  existing memory-hardening posture (`app/core/hardening.py`'s
  `memory_monitor`).

## Status

**Phase 1 shipped 2026-07-10** (all five items): `app/core/vault_context.py` +
planner injection; `skill_versions`/`skill_outcomes`/`improvement_log` DDL;
`SkillOutcomeTracker` + the planner tool-loop instrumentation;
`self_learning_loop.run_cycle()` + `PatternReinforcer` scheduled into Lane 8
(shipped earlier, PRs #23–30); `/api/skill_health` + `/api/improvement_log`
endpoints and the `skill-health.md`/`improvement-log.md` sections in
`vault_pull.py`. One deviation from the letter of A2.2: retire rationales are
deterministic sentences built from the Wilson numbers rather than an extra
LLM call — works LLM-dead, zero cost, same Reflexion content. Phases 2–3
remain open.

## Follow-ups

- Scope HermesClaw's own agent/prompt-assembly loop to find the exact call
  site for A3 (equivalent to `planner.py`'s `_build_messages()`).
- Decide Phase 3 option (a) vs (b) for Nova's Render-side vault-read gap —
  needs Mark's call given the cost/staleness tradeoff.
- Once `SkillChallengerEvaluator` has real production cycles under it,
  consider whether `outreach_outcomes`/`learned_strategies` and
  `skill_outcomes`/`skill_versions` should be unified into one schema — kept
  separate here deliberately (string-parameter strategies vs. code/prompt
  versions are different enough shapes to warrant it at launch) but the
  duplication (two Wilson-bound-ranked champion/challenger tables) is worth
  revisiting once both have mileage.
