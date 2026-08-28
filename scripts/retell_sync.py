#!/usr/bin/env python3
"""Retell agent sync — dump, render, push.

WHY THIS EXISTS
---------------
`business_context.json > retell_pitch / retell_inbound` is the source of truth
for what Nova says on the phone. The DEPLOYED prompt lives in Retell's
dashboard, and until now nothing connected the two, so they drifted: as of
2026-08-27 the deployed text still said "ten minutes" (canonical is 15) and
still described OROVA as ads-only (we sell three things).

Retell UPDATES AN LLM VERSION IN PLACE. There is no rollback pin. The prior
text exists only in whatever transcript happened to capture it. So this script
is deliberately three separate verbs, and `push` is the only one that writes:

    dump    read every agent + LLM config to a timestamped JSON file   (safe)
    render  build the prompt text from business_context.json, print it (safe)
    push    send the rendered prompt to Retell                  (WRITES, gated)

`push` refuses to run without --confirm, and always dumps first. Do not add a
"push everything" convenience verb; the whole point is that the write is
deliberate and preceded by a backup.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = ROOT / "app" / "core" / "business_context.json"
FACTS = ROOT / "knowledge" / "facts" / "company.json"
BACKUP_DIR = ROOT / ".retell-backups"
API = "https://api.retellai.com"


def _ctx() -> dict:
    return json.loads(CONTEXT.read_text(encoding="utf-8"))


def _key() -> str:
    key = os.getenv("RETELL_API_KEY", "").strip()
    if not key:
        sys.exit(
            "RETELL_API_KEY is not set.\n"
            "  dump/push need it; `render` does not and works offline.\n"
            "  Set it in .env or the environment and retry."
        )
    return key


def _client():
    import httpx
    return httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {_key()}"},
        timeout=30.0,
    )


# ── dump ────────────────────────────────────────────────────────────────────
def cmd_dump(args) -> int:
    """Read every agent and its LLM config to a timestamped file.

    This is the rollback that Retell does not give us. Run it BEFORE any push.
    """
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = BACKUP_DIR / f"retell-{stamp}.json"

    with _client() as c:
        agents = c.get("/list-agents")
        agents.raise_for_status()
        agents = agents.json()

        snapshot = {"_dumped_at": stamp, "agents": [], "llms": {}}
        for a in agents:
            snapshot["agents"].append(a)
            # Single-prompt agents carry a response_engine -> llm_id.
            engine = a.get("response_engine") or {}
            llm_id = engine.get("llm_id")
            if llm_id and llm_id not in snapshot["llms"]:
                r = c.get(f"/get-retell-llm/{llm_id}")
                if r.status_code == 200:
                    snapshot["llms"][llm_id] = r.json()
                else:
                    snapshot["llms"][llm_id] = {"_error": r.status_code, "_body": r.text[:500]}

    out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"dumped {len(snapshot['agents'])} agents / {len(snapshot['llms'])} LLM configs")
    print(f"  -> {out.relative_to(ROOT)}")
    for a in snapshot["agents"]:
        engine = a.get("response_engine") or {}
        print(f"  {a.get('agent_id')}  {a.get('agent_name')!r}  "
              f"engine={engine.get('type')} llm={engine.get('llm_id')}")
    return 0


# ── render ──────────────────────────────────────────────────────────────────
def _render_inbound(ctx: dict) -> str:
    """Build the inbound prompt from the canonical spec.

    Generated, not hand-maintained: a hand-copied prompt is exactly how the
    'ten minutes' / ads-only drift survived four months.
    """
    b = ctx["retell_inbound"]
    # Duration comes from CANONICAL facts, never from a copy in this file.
    # A second copy of the number is how "ten minutes" outlived the decision
    # to make the call fifteen.
    duration = json.loads(FACTS.read_text(encoding="utf-8"))["meeting"]["duration_minutes"]
    lines = [
        "## IDENTITY",
        b["identity"],
        "",
        "## THE ONE THING TO REMEMBER",
        b["the_frame"],
        "",
        "## GOAL",
        b["goal"],
        "",
        "## COMPLIANCE — NON-NEGOTIABLE",
    ]
    for k, v in b["compliance"].items():
        lines.append(f"- **{k}**: {v}")
    # `_opening_note` and the other underscore keys are DESIGN RATIONALE for
    # whoever edits this file next, not instructions for the agent. Rendering
    # them would spend live tokens telling Nova about a caller who hung up in
    # August. Underscore = internal, everywhere in business_context.json.
    lines += ["", "## OPENING", b["begin_message"], "",
              "## ROUTING — pick the branch that matches, do not recite them"]
    for k, v in b["branches"].items():
        lines.append(f"\n### {k}\n{v}")
    lines += ["", "## MUST CAPTURE BEFORE THE CALL ENDS"]
    for m in b["must_capture"]:
        lines.append(f"- {m}")
    lines += ["", "## THE ASK", b["the_ask"].replace("{{duration}}", str(duration)),
              "", "## NEVER"]
    for n in b["never_say"]:
        lines.append(f"- {n}")
    lines += ["", "## STYLE", b["_style"]]
    return "\n".join(lines)


def cmd_render(args) -> int:
    ctx = _ctx()
    text = _render_inbound(ctx)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"rendered -> {args.out}  ({len(text)} chars)")
    else:
        print(text)
    return 0


# ── push ────────────────────────────────────────────────────────────────────
def cmd_push(args) -> int:
    if not args.confirm:
        sys.exit(
            "REFUSED. `push` overwrites a live Retell LLM version IN PLACE and\n"
            "Retell keeps no rollback pin. Run `dump` first, read the rendered\n"
            "text with `render`, then re-run with --confirm if it is correct."
        )
    cmd_dump(args)  # never push without a backup on disk

    ctx = _ctx()
    text = _render_inbound(ctx)
    llm_id = args.llm_id
    body = {
        "general_prompt": text,
        "begin_message": ctx["retell_inbound"]["begin_message"],
    }
    with _client() as c:
        r = c.patch(f"/update-retell-llm/{llm_id}", json=body)
    if r.status_code != 200:
        print(f"FAILED {r.status_code}: {r.text[:600]}", file=sys.stderr)
        return 1
    print(f"pushed inbound prompt to {llm_id} ({len(text)} chars)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("dump", help="back up every agent + LLM config (safe)")
    r = sub.add_parser("render", help="build the prompt from business_context (safe, offline)")
    r.add_argument("--out", help="write to a file instead of stdout")
    u = sub.add_parser("push", help="WRITE the rendered prompt to Retell")
    u.add_argument("--llm-id", required=True)
    u.add_argument("--confirm", action="store_true")
    args = p.parse_args()
    return {"dump": cmd_dump, "render": cmd_render, "push": cmd_push}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
