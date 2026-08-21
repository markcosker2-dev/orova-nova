#!/usr/bin/env python3
"""Knowledge compiler (M1) — ADR-0005.

Reads the canonical facts (knowledge/facts/company.json), resolves {{ref:...}}
references, validates + lint-checks the runtime artifacts against them, and
projects a human-readable read-only view into the vault.

M1 scope (deliberately minimal — see ADR-0005):
  - resolve references so a value like the service fee lives in ONE node
  - lint business_context.json for PRICING DRIFT against canonical (hard gate)
  - lint the OUTBOUND COPY fields for spam words / forbidden phrases (hard gate)
  - generate vault/10-brain/facts.md (read-only projection)

Deferred to M2: generating business_context.json itself, projecting into the
Retell prompt / skill fact-blocks, and prose price consolidation.

Pure stdlib (no pyyaml / jsonschema) so it adds zero dependencies to the
free-tier image and runs in the existing CI pytest step.

Usage:
  python scripts/compile_knowledge.py --check   # validate + lint + assert facts.md current (CI)
  python scripts/compile_knowledge.py --write    # (re)generate facts.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FACTS_PATH = ROOT / "knowledge" / "facts" / "company.json"
BUSINESS_CONTEXT_PATH = ROOT / "app" / "core" / "business_context.json"
FACTS_MD_PATH = ROOT / "vault" / "10-brain" / "facts.md"

_REF_RE = re.compile(r"^\{\{ref:([a-zA-Z0-9_.]+)\}\}$")


# ── Canonical facts: load + resolve references ─────────────────────────────
def _lookup(root: dict, dotted: str) -> Any:
    node: Any = root
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"unresolved reference: {dotted}")
        node = node[part]
    return node


def resolve_refs(obj: Any, root: dict) -> Any:
    """Recursively replace '{{ref:dotted.path}}' strings with the referenced value."""
    if isinstance(obj, dict):
        return {k: resolve_refs(v, root) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_refs(v, root) for v in obj]
    if isinstance(obj, str):
        m = _REF_RE.match(obj.strip())
        if m:
            return resolve_refs(_lookup(root, m.group(1)), root)
    return obj


def load_facts(path: Path = FACTS_PATH) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return resolve_refs(raw, raw)


# ── Validation (structural — the "schema" is explicit, no jsonschema dep) ───
def validate(facts: dict) -> list[str]:
    errors: list[str] = []
    for key in ("company", "pricing", "packages", "compliance", "meeting"):
        if key not in facts:
            errors.append(f"facts: missing top-level key '{key}'")
    for pkg in facts.get("packages", []):
        for field in ("id", "name", "price_monthly_usd", "tiers_usd"):
            if field not in pkg:
                errors.append(f"package {pkg.get('id', '?')}: missing '{field}'")
        price = pkg.get("price_monthly_usd")
        if not isinstance(price, int):
            errors.append(f"package {pkg.get('id')}: price_monthly_usd must resolve to int, got {price!r}")
    return errors


# ── Lint: runtime artifacts must agree with canonical ──────────────────────
def _pkg_number(name: str) -> str | None:
    m = re.search(r"package\s*(\d+)", name, re.IGNORECASE)
    return m.group(1) if m else None


def lint_pricing(facts: dict, business_context: dict) -> list[str]:
    """business_context.json package prices/tiers MUST equal canonical."""
    errors: list[str] = []
    canonical = {}
    for pkg in facts["packages"]:
        n = _pkg_number(pkg["name"])
        if n:
            canonical[n] = {"monthly": pkg["price_monthly_usd"], "tiers": pkg["tiers_usd"]}
    for svc in business_context.get("services", []):
        n = _pkg_number(svc.get("name", ""))
        if not n or n not in canonical:
            continue
        exp = canonical[n]
        if svc.get("price_monthly_usd") != exp["monthly"]:
            errors.append(
                f"pricing drift: Package {n} monthly is {svc.get('price_monthly_usd')} "
                f"in business_context.json but {exp['monthly']} in canonical facts"
            )
        if svc.get("pricing_tiers_usd") != exp["tiers"]:
            errors.append(
                f"pricing drift: Package {n} tiers are {svc.get('pricing_tiers_usd')} "
                f"in business_context.json but {exp['tiers']} in canonical facts"
            )
    return errors


def _outbound_copy(business_context: dict) -> list[tuple[str, str]]:
    """(location, text) pairs of the actual OUTBOUND copy — not rule docs."""
    out: list[tuple[str, str]] = []
    outreach = business_context.get("outreach", {})
    for fw in ("initial_email_framework", "follow_up_email_framework"):
        ex = outreach.get(fw, {}).get("example")
        if isinstance(ex, str):
            out.append((f"outreach.{fw}.example", ex))
    for i, subj in enumerate(business_context.get("email_rules", {}).get("subject_formulas", [])):
        if isinstance(subj, str):
            out.append((f"email_rules.subject_formulas[{i}]", subj))
    return out


def lint_copy(facts: dict, business_context: dict) -> list[str]:
    """Outbound copy fields must contain no spam word / forbidden phrase."""
    errors: list[str] = []
    banned = [w.lower() for w in facts["compliance"].get("spam_words", [])] + \
             [p.lower() for p in facts["compliance"].get("forbidden_phrases", [])]
    for loc, text in _outbound_copy(business_context):
        low = text.lower()
        for term in banned:
            if term in low:
                errors.append(f"compliance: outbound copy {loc} contains banned term '{term}'")
    return errors


# The meeting length is a canonical fact, so copy that contradicts it is drift
# — the same failure lint_pricing exists to catch, in a different field.
#
# Discovered 2026-08-21: 24 prospect-facing strings claimed 10, 15 or "10-15"
# minutes while the live cal.com event was 30. Four different answers to "how
# long is this call", none of them checked. A prospect promised ten minutes and
# handed a thirty-minute booking page has been told two things by one company.
#
# Paths are GLOBBED, not listed. A hand-maintained file list is the silent
# contract that let insurance_amt vanish six times — a new copy module must be
# covered by default, not by remembering to add it.
_COPY_GLOBS = (
    "app/skills/*.py",
    "app/core/business_context.json",
    ".claude/skills/sales-intelligence/**/*.md",
)

# A duration is prospect-facing only when it modifies a call/chat/meeting.
# "auto-execute in 30 min" and "runs every 30 minutes" are timers and must
# never be flagged, so CONTEXT decides rather than the filename. Deliberately
# narrow, for the reason check_secrets.py gives: a linter that cries wolf gets
# switched off, and a switched-off linter is worse than none.
_DURATION_RE = re.compile(
    r"\b(?P<num>(?:\d{1,3})(?:\s*-\s*\d{1,3})?)[\s-]?(?:min|mins|minute|minutes)\b",
    re.IGNORECASE,
)
_MEETING_WORD_RE = re.compile(r"call|chat|meeting|conversation|version", re.IGNORECASE)

# "call the homeowner IN 5 minutes" is speed-to-lead — a latency, and the
# differentiator the entire pitch rests on. "a 15-minute call" is a length.
# Both sit beside the word "call", so the preposition is what separates them.
# Without this the linter flags the differentiator on every run, and a linter
# that cries wolf gets switched off (see check_secrets.py for the same rule).
_LATENCY_RE = re.compile(r"\b(?:in|within|under|every|after|takes?|lasts?)\s*$",
                         re.IGNORECASE)
_ALLOW_MARKER = "noqa: duration"      # a reviewed, intentional exception
_CTX = 40


def lint_meeting_duration(facts: dict) -> list[str]:
    """Prospect-facing copy must not state a call length other than canonical."""
    meeting = facts.get("meeting") or {}
    canon = meeting.get("duration_minutes")
    if not isinstance(canon, int):
        return ["facts: meeting.duration_minutes must be an int"]

    errors: list[str] = []
    seen: set[Path] = set()
    for pattern in _COPY_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            for m in _DURATION_RE.finditer(text):
                ctx = text[max(0, m.start() - _CTX): m.end() + _CTX]
                if not _MEETING_WORD_RE.search(ctx):
                    continue                       # a timer, not an ask
                if _LATENCY_RE.search(text[max(0, m.start() - 12): m.start()]):
                    continue                       # speed-to-lead, not a length
                if m.group("num") == str(canon):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                if _ALLOW_MARKER in text.split("\n")[line - 1]:
                    continue
                errors.append(
                    f"meeting drift: {rel}:{line} offers a "
                    f"'{m.group(0)}' call but canonical is {canon} minutes"
                )
    return errors


def lint(facts: dict, business_context: dict) -> list[str]:
    return (validate(facts) + lint_pricing(facts, business_context)
            + lint_copy(facts, business_context) + lint_meeting_duration(facts))


# ── Projection: read-only facts.md for humans (Obsidian) ───────────────────
def emit_facts_md(facts: dict) -> str:
    c = facts["company"]
    lines = [
        "---",
        "name: facts",
        "description: Canonical business facts (GENERATED — do not edit here)",
        "type: doc",
        "created: 2026-07-14",
        "status: active",
        "---",
        "",
        "# 🔒 Canonical Facts (generated)",
        "",
        "> [!warning] Generated by `scripts/compile_knowledge.py` from "
        "`knowledge/facts/company.json` (ADR-0005). **Do not edit this file** — "
        "change the source and recompile.",
        "",
        f"**{c['name']}** · CEO {c['ceo']} · agent {c['ai_agent']} · {c['timezone']}",
        "",
        "## Packages & pricing",
        "",
        "| Package | Monthly | 1-mo | 3-mo | 6-mo |",
        "|---|---|---|---|---|",
    ]
    for pkg in facts["packages"]:
        t = pkg["tiers_usd"]
        lines.append(
            f"| {pkg['name']} | ${pkg['price_monthly_usd']:,} | "
            f"${t['1_month']:,} | ${t['3_month']:,} | ${t['6_month']:,} |"
        )
    lines += [
        "",
        f"Recommended client ad spend: **${facts['pricing']['ad_spend_recommended_usd']}/mo** "
        "(paid by the client directly to Meta).",
        "",
    ]
    return "\n".join(lines) + "\n"


# ── CLI ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="HermesClaw knowledge compiler (M1)")
    ap.add_argument("--check", action="store_true", help="validate + lint + assert facts.md current; exit 1 on any failure")
    ap.add_argument("--write", action="store_true", help="(re)generate facts.md")
    args = ap.parse_args()

    facts = load_facts()
    business_context = json.loads(BUSINESS_CONTEXT_PATH.read_text(encoding="utf-8"))
    errors = lint(facts, business_context)

    rendered = emit_facts_md(facts)

    if args.write:
        FACTS_MD_PATH.write_text(rendered, encoding="utf-8")
        print(f"[compile] wrote {FACTS_MD_PATH.relative_to(ROOT)}")

    if args.check:
        current = FACTS_MD_PATH.read_text(encoding="utf-8") if FACTS_MD_PATH.exists() else ""
        if current != rendered:
            errors.append("facts.md is stale — run `python scripts/compile_knowledge.py --write`")

    if errors:
        print("KNOWLEDGE COMPILE FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    if args.check:
        print("[compile] OK — canonical facts valid, no drift, facts.md current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
