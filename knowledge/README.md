# knowledge/ — canonical business facts (ADR-0005, M1)

The single source of truth for OROVA's **structured facts**. Edit values here;
everything downstream is validated or generated from them. See
[ADR-0005](../vault/40-decisions/0005-canonical-knowledge-facts-and-projection.md)
for the full decision and the deferred roadmap.

## Layout

```
knowledge/
└── facts/
    └── company.json     # canonical facts: company, pricing, packages, compliance
scripts/compile_knowledge.py   # the build-time compiler (pure stdlib, no deps)
```

Narrative (ADRs, playbook, session notes) is **not** here — it stays
human-authored markdown in `vault/` and merely references these facts.

## References, not copies

A value reused in 2+ places becomes one node and is referenced with
`"{{ref:dotted.path}}"`. Example: the service fee lives once in
`pricing.service_fee_p1_usd` and the package tiers reference it — change it in one
place, every projection updates. (This is the "graph-ready" substrate from
ADR-0005: the references are the edges. Normalize a value into a node only once it
is actually reused — not on principle.)

## The compiler

```bash
python scripts/compile_knowledge.py --check    # CI: validate + lint + assert facts.md current
python scripts/compile_knowledge.py --write     # regenerate vault/10-brain/facts.md
```

What it enforces (hard gates, run automatically via `tests/test_compile_knowledge.py`):
- **Pricing drift** — `app/core/business_context.json` package prices/tiers must
  equal canonical. A mismatch fails the build.
- **Compliance** — the outbound-copy fields (email templates, subject lines) must
  contain no spam word / forbidden phrase. Rule-documentation that *names* those
  terms is intentionally not scanned.
- **facts.md currency** — the generated read-only view must match source.

## Projections

| Target | Status |
|---|---|
| `vault/10-brain/facts.md` (read-only human view) | ✅ generated (M1) |
| `app/core/business_context.json` | 🛡️ guarded against drift (M1) — generation is M2 |
| Retell prompt · Claude Skill fact-blocks · CEO reports | ⏳ M2 |

## Adding a fact

1. Add it to `facts/company.json` (reference an existing node if the value already
   exists elsewhere).
2. If it appears in a runtime artifact, add a lint rule in `compile_knowledge.py`.
3. `--write` to refresh `facts.md`; run the tests.
