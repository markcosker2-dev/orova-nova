# -*- coding: utf-8 -*-
"""
Vault Pull — sync production knowledge into the Obsidian vault.

Pulls from the live Render backend (dashboard API) and upserts markdown:
  - GET /api/leads   -> vault/30-leads/{slug}.md
  - GET /api/memory  -> entries with type "brief" -> vault/20-ops/briefs/{date}.md

Run locally: python scripts/vault_pull.py
Needs RENDER_EXTERNAL_URL (or VAULT_PULL_URL) and DASHBOARD_API_KEY in .env.

Idempotent: files are only written when content actually changed, so
re-running never churns OneDrive/git.
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parents[1]
LEADS_DIR = ROOT / "vault" / "30-leads"
BRIEFS_DIR = ROOT / "vault" / "20-ops" / "briefs"
STRATEGY_NOTE = ROOT / "vault" / "10-brain" / "strategy-snapshot.md"
SKILL_HEALTH_NOTE = ROOT / "vault" / "10-brain" / "skill-health.md"
IMPROVEMENT_LOG_NOTE = ROOT / "vault" / "20-ops" / "improvement-log.md"

BASE_URL = (os.getenv("VAULT_PULL_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
API_KEY = os.getenv("DASHBOARD_API_KEY", "")


def _slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9 ]+", "", text or "").strip().lower()
    return re.sub(r"\s+", "-", text) or "unnamed"


def _write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _lead_markdown(lead: dict) -> str:
    business = lead.get("business") or "Unknown Business"
    slug = _slug(business)
    created = (lead.get("created_at") or datetime.now().strftime("%Y-%m-%d"))[:10]
    email_status = lead.get("email_status") or "unknown"
    return (
        "---\n"
        f"name: lead-{slug}\n"
        f"description: Lead wiki for {business}\n"
        "type: lead\n"
        f"created: {created}\n"
        "status: active\n"
        "---\n\n"
        f"# Lead: {business}\n\n"
        f"> **Status:** {lead.get('status', 'New')}  \n"
        f"> **Score:** {lead.get('score', 0)}  \n"
        f"> **Vertical:** {lead.get('vertical', '')}  \n"
        f"> **Source:** {lead.get('url') or lead.get('website') or ''}\n\n"
        "## Owner / Decision Maker\n\n"
        f"- **Name:** {lead.get('owner') or 'Unknown'}\n"
        f"- **Title:** {lead.get('owner_title') or ''}\n"
        f"- **LinkedIn:** {lead.get('linkedin_url') or ''}\n\n"
        "## Contact Info\n\n"
        f"- **Email:** {lead.get('email') or ''} (status: {email_status})\n"
        f"- **Phone:** {lead.get('phone') or ''}\n"
        f"- **Website:** {lead.get('website') or ''}\n\n"
        "## Notes\n\n"
        f"{lead.get('notes') or '-'}\n\n"
        "---\n"
        "Part of the pipeline — see [[product-context]] · [[Home]]\n\n"
        "*Synced from production by scripts/vault_pull.py*\n"
    )


def _brief_markdown(entry: dict) -> str:
    date = entry.get("date") or "undated"
    return (
        "---\n"
        f"name: brief-{date}\n"
        f"description: CEO daily brief for {date}\n"
        "type: brief\n"
        f"created: {date}\n"
        "status: done\n"
        "---\n\n"
        f"# CEO Brief — {date}\n\n"
        f"{entry.get('content', '').strip()}\n"
    )


def _strategy_markdown(strategies: list) -> str:
    """Curated snapshot of what Nova has LEARNED — the Obsidian side of the
    self-improvement loop. Not a DB mirror: active strategies only, ranked."""
    lines = [
        "---",
        "name: strategy-snapshot",
        "description: What Nova has learned — active strategies ranked by Wilson score",
        "type: brain",
        f"created: {datetime.now().strftime('%Y-%m-%d')}",
        "status: active",
        "---",
        "",
        "# Strategy Snapshot (auto-synced)",
        "",
        "What the self-improvement loop currently believes, ranked by the",
        "small-sample-safe Wilson bound. Synced by `scripts/vault_pull.py` —",
        "do not edit by hand.",
        "",
        "| Type | Strategy | Win rate | Sample | Wilson | Confidence |",
        "|---|---|---|---|---|---|",
    ]
    for s in sorted(strategies, key=lambda x: x.get("wilson_score") or 0, reverse=True):
        lines.append(
            f"| {s.get('strategy_type', '')} | {s.get('strategy_value', '')} "
            f"| {round((s.get('win_rate') or 0) * 100, 1)}% | {s.get('sample_size', 0)} "
            f"| {round(s.get('wilson_score') or 0, 3)} | {s.get('confidence', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def _skill_health_markdown(skills: list) -> str:
    """Per-skill outcome rollup (ADR-0004 A2.1) — which skills are winning,
    which are degrading, straight from production's skill_outcomes table."""
    lines = [
        "---",
        "name: skill-health",
        "description: Per-skill production outcomes — win rate, Wilson bound, latency",
        "type: brain",
        f"created: {datetime.now().strftime('%Y-%m-%d')}",
        "status: active",
        "---",
        "",
        "# Skill Health (auto-synced)",
        "",
        "One row per (skill, version) from production's `skill_outcomes` table.",
        "Synced by `scripts/vault_pull.py` — do not edit by hand.",
        "",
        "| Skill | Version | Samples | Win rate | Wilson | Avg latency (ms) | Last used |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in skills:
        lines.append(
            f"| {s.get('skill_name', '')} | {s.get('version_id', '')} "
            f"| {s.get('n', 0)} | {round((s.get('win_rate') or 0) * 100, 1)}% "
            f"| {round(s.get('wilson') or 0, 3)} | {round(s.get('avg_latency_ms') or 0)} "
            f"| {s.get('last_used', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


_IMPROVEMENT_ID_RE = re.compile(r"^- `#(\d+)`", re.MULTILINE)

_IMPROVEMENT_LOG_HEADER = """---
name: improvement-log
description: Running changelog of what Nova promoted/retired and why
type: brain
created: {date}
status: active
---

# Improvement Log (auto-appended)

Reflexion-style trace (ADR-0004 A2.2): one line per promote/retire decision,
appended by id from production's `improvement_log` table by
`scripts/vault_pull.py`. Do not edit existing lines by hand.
"""


def _append_improvement_entries(path: Path, entries: list) -> int:
    """Append entries with id greater than the largest already in the file —
    idempotent by id, so re-running the pull never duplicates a line."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    seen_ids = [int(m) for m in _IMPROVEMENT_ID_RE.findall(existing)]
    last_seen = max(seen_ids) if seen_ids else 0
    fresh = [e for e in entries if isinstance(e, dict) and (e.get("id") or 0) > last_seen]
    if not fresh:
        return 0
    if not existing:
        existing = _IMPROVEMENT_LOG_HEADER.format(date=datetime.now().strftime("%Y-%m-%d"))
    lines = [
        f"- `#{e['id']}` {str(e.get('created_at', ''))[:10]} — "
        f"**{e.get('action', '')}** {e.get('subject_type', '')} "
        f"`{e.get('subject_name', '')}`: {e.get('rationale', '') or '(no rationale)'}"
        for e in fresh
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip("\n") + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return len(fresh)


def main() -> int:
    if not BASE_URL or not API_KEY:
        print("ERROR: set RENDER_EXTERNAL_URL (or VAULT_PULL_URL) and DASHBOARD_API_KEY in .env")
        return 1

    headers = {"X-Dashboard-Secret": API_KEY}
    new_leads = 0
    new_briefs = 0

    # Render free tier spins the service down after ~15 min idle, and a cold
    # start can take well over a minute. Poll /health a few times to wake it
    # before the real calls, so the sync doesn't fail just because the service
    # was asleep. Total wake budget ~5 min.
    with httpx.Client(timeout=120, headers=headers) as client:
        awake = False
        for attempt in range(5):
            try:
                r = client.get(f"{BASE_URL}/health")
                if r.status_code == 200:
                    awake = True
                    break
            except Exception as e:
                print(f"WARN: warmup ping {attempt + 1}/5 failed: {e}")
        if not awake:
            print("WARN: service did not wake in time; sync may return nothing.")
        # Leads -> vault/30-leads/
        try:
            res = client.get(f"{BASE_URL}/api/leads")
            res.raise_for_status()
            leads = res.json().get("leads", [])
            for lead in leads:
                if not isinstance(lead, dict) or not lead.get("business"):
                    continue
                path = LEADS_DIR / f"{_slug(lead['business'])}.md"
                if _write_if_changed(path, _lead_markdown(lead)):
                    new_leads += 1
        except Exception as e:
            print(f"WARN: leads pull failed: {e}")

        # Briefs (memories with type=brief) -> vault/20-ops/briefs/
        try:
            res = client.get(f"{BASE_URL}/api/memory")
            res.raise_for_status()
            memories = res.json().get("memories", [])
            for entry in memories:
                if not isinstance(entry, dict) or entry.get("type") != "brief":
                    continue
                date = entry.get("date") or "undated"
                path = BRIEFS_DIR / f"{date}.md"
                if _write_if_changed(path, _brief_markdown(entry)):
                    new_briefs += 1
        except Exception as e:
            print(f"WARN: briefs pull failed: {e}")

        # Learned strategies -> vault/10-brain/strategy-snapshot.md
        strategies_updated = False
        try:
            res = client.get(f"{BASE_URL}/api/learned_strategies")
            res.raise_for_status()
            strategies = res.json().get("strategies", [])
            if strategies:
                strategies_updated = _write_if_changed(STRATEGY_NOTE, _strategy_markdown(strategies))
        except Exception as e:
            print(f"WARN: strategies pull failed: {e}")

        # Skill health rollups -> vault/10-brain/skill-health.md
        skill_health_updated = False
        try:
            res = client.get(f"{BASE_URL}/api/skill_health")
            res.raise_for_status()
            skills = res.json().get("skills", [])
            if skills:
                skill_health_updated = _write_if_changed(SKILL_HEALTH_NOTE, _skill_health_markdown(skills))
        except Exception as e:
            print(f"WARN: skill health pull failed: {e}")

        # Improvement changelog -> vault/20-ops/improvement-log.md (append by id)
        new_improvements = 0
        try:
            res = client.get(f"{BASE_URL}/api/improvement_log")
            res.raise_for_status()
            entries = res.json().get("entries", [])
            if entries:
                new_improvements = _append_improvement_entries(IMPROVEMENT_LOG_NOTE, entries)
        except Exception as e:
            print(f"WARN: improvement log pull failed: {e}")

    print(
        f"vault_pull: {new_leads} lead file(s) updated, {new_briefs} brief(s) updated, "
        f"strategy snapshot {'updated' if strategies_updated else 'unchanged'}, "
        f"skill health {'updated' if skill_health_updated else 'unchanged'}, "
        f"{new_improvements} improvement-log entr{'y' if new_improvements == 1 else 'ies'} appended"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
