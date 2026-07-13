---
name: 0005-canonical-knowledge-facts-and-projection
description: single canonical fact layer + narrative split, build-time projection, compliance linter; relationship-graph and runtime Executive Brain deferred
type: decision
created: 2026-07-14
status: proposed
---

# ADR-0005 — Canonical knowledge: graph-ready facts + narrative, build-time projection

## Context

Business knowledge is duplicated across many stores with no canonical source, and
the duplication is already causing drift — verified, not hypothesized:

- **The `$4k/$5k` pricing fact lives in 7 files**: `app/core/business_context.json`,
  `vault/hermesclaw-orova/close-kit/service-agreement.md`,
  `vault/hermesclaw-orova/playbook/pricing-and-negotiation.md`,
  `vault/hermesclaw-orova/README.md`, `vault/10-brain/business-model.md`,
  `vault/10-brain/orova-playbook.md`, `vault/10-brain/profitability-plan.md`.
  A price change is a 7-file edit.
- **Positioning has already drifted**: `business_context.json` is lead-gen-framed
  ("only talk to qualified leads") while the Sales Intelligence skill and its
  `positioning.md` say "premium revenue growth." Flagged in PR #68.
- **Sync is manual and laptop-bound**: the Dockerfile copies only `app/` +
  `mission-control/` (not `vault/`), and `scripts/vault_pull.py` has no cron/CI
  caller — so production never reads/writes the vault, and the vault updates only
  when the founder runs the pull script locally (ties to ADR-0001's one-directional
  constraint and the ADR-0004 learning wiring).

The total curated knowledge surface is small (~2,000 lines). The duplication is
real but bounded, which rules *out* a heavyweight solution and rules *in* a minimal
one. An "Executive Brain + Knowledge Compiler" was proposed (owner directive,
2026-07-14). After a two-round adversarial design review it was judged
directionally right but over-scoped for a pre-revenue, $0, solo-founder,
free-tier-hosted system. (An external council cross-check via `/claude-council:ask`
was attempted; the only configured provider, Gemini, returned empty —
quota-exhausted, consistent with the 429s seen in production logs this session — so
this decision rests on the internal review.)

## Decision

Adopt a **hybrid, phased, build-time** canonical-knowledge model. Not a runtime
compiler, not a graph engine — yet.

1. **Facts vs narrative split (load-bearing).**
   - **Facts** — pricing, packages, ICP, positioning, cadence, compliance rules —
     live once in `knowledge/facts/*.yaml`, schema-validated, each with a **stable
     ID**. Any value reused in 2+ places becomes a **referenceable node**
     (`pricing.service_fee`) instead of a copy. *Normalize on evidence of reuse
     (2+), not on principle* — over-decomposition makes authoring a chore.
   - **Narrative** — ADRs, playbooks, postmortems, session notes — stays
     **human-authored markdown** that *references* fact IDs and is **never
     compiled**. Prose is authored, not generated.

2. **Build-time generator** (`scripts/compile_knowledge.py`, runs in CI, not at
   runtime): resolves references and projects facts into per-runtime artifacts,
   each receiving only what it needs — `business_context.json` (Nova), the Retell
   voice prompt, Claude Skill fact-blocks, CEO/exec reports. Idempotent, diff-only,
   PR-gated (like `vault_pull.py`). Rollback = `git revert`; versioning = git.

3. **Compliance linter** in CI (the keystone, valuable independently): validates
   `facts/` *and* every generated artifact — no wrong price, no forbidden phrase
   (e.g. the prior agency), no positioning drift, no leaked secret.

4. **Obsidian role is per-layer**: it **projects facts** (a read-only
   `10-brain/facts.md` rendered by the generator) and remains the **source for
   narrative**. The source/projection question is answered by layer — which is the
   facts/narrative split applied to authorship.

5. **Learning writes back to canonical facts, never to projections.** The existing
   Wilson champion/challenger loop (ADR-0004) proposes a winning variant as a **PR
   to `knowledge/facts/`**; CI + the linter + human review gate it; recompile
   propagates it everywhere. One write target prevents drift; the evidence gate
   preserves stability.

6. **Deferred until a real trigger** (a 2nd live LLM provider in production, OR a
   3rd paying client): a semantic **relationship-graph engine** and any runtime
   **"Executive Brain" service.** The fact layer is *graph-ready* now (IDs +
   references = the graph's latent edges), so these are reachable by addition, not
   rewrite. **Guardrail: every future graph edge must be consumed by a projection
   or a validator, or it is dead weight** (avoids the semantic-web
   ontology-nobody-reads failure).

## Consequences

**Easier:** the positioning drift dies now; pricing maintenance goes 7→1; adding a
future model/agent is "add a projection template," not a rewrite; one place to
enforce compliance; learning has a single, reviewed write-back target.

**Harder:** a schema + a build step to maintain; a real judgment call on every new
piece of knowledge ("is this a fact or narrative?"); the generator is a shared
dependency (mitigated: build-time only, CI-validated, PR-gated, revertible — its
blast radius is caught before merge, not in production).

**Explicitly giving up (for now):** the grand runtime compiler, the relationship
graph, and the Executive Brain *service*. We keep them as the north star and design
the fact layer to not block them; we do not build them before scale demands it. The
most senior call available pre-revenue is *smaller and later than proposed, with a
clear path to the larger vision*.

## Milestones

- **M1 (days):** `knowledge/facts/company.yaml` (pricing as the first node) + JSON
  Schema + compliance linter in CI + generate `business_context.json`; delete the 6
  duplicate pricing copies; render read-only `facts.md`.
- **M2:** project facts into the Retell prompt and the skill fact-blocks; align the
  lead-gen→revenue-growth positioning at the source.
- **M3 (trigger-gated):** relationship edges as projections begin to traverse them;
  per-runtime token trimming; server-side sync (a scheduled `vault_pull`, closing
  the laptop-off gap).

## Linked

- [[0001-adopt-obsidian]] · [[0004-obsidian-brain-and-skill-improvement]]
- Consumes: `app/core/business_context.json`, the Sales Intelligence skill,
  `vault/hermesclaw-orova/playbook/`, the Wilson loop in
  `app/core/self_improvement.py`.
