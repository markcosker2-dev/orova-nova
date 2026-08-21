#!/usr/bin/env python
"""One command for operating Nova.

Written 2026-08-21 after a session that answered "is anything broken?" with
about fifteen separate curl invocations, and still missed two live defects
until someone looked on purpose: the production dashboard key sitting in the
current tree of a public repo, and a booking link that returned a confident
404 while every health check stayed green.

The point is not a prettier dashboard — mission-control and /api/morning_brief
already exist. The point is that the checks a human will actually run are the
ones that take one command, and the two bugs above were both invisible to
every check that existed.

    python scripts/nova.py                 status + today's call sheet
    python scripts/nova.py status          is anything broken, what's on me
    python scripts/nova.py calls           who to ring, in what order
    python scripts/nova.py leaks           secrets + what the internet can see
    python scripts/nova.py gates           the three CI gates, locally
    python scripts/nova.py hunt --state WA --niche "kitchen remodel" --location Seattle
    python scripts/nova.py outcome 12 talked "backlog is 3 weeks"

Stdlib only, on purpose: this has to run when the venv is wrong, and a tool
you reach for while something is already broken cannot have its own
dependencies.

NEVER prints a secret. `leaks` reports whether a value is exposed, never what
it is — reproducing a burned credential to prove it is burned is the mistake
that caused the second leak.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 60          # Render free tier cold-starts; short timeouts read as outages

OK, ACT, BAD, HOLD, DIM = "OK", "ACTION", "BROKEN", "HELD", "--"


# ── plumbing ────────────────────────────────────────────────────────────────
def git(*args: str) -> str:
    # S603: argv is a fixed list built in this file, shell=False, and no
    # caller passes user input — every call site uses literal git subcommands.
    try:
        return subprocess.run(["git", *args], cwd=ROOT,  # noqa: S603
                              capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except Exception:                                        # noqa: BLE001
        return ""


def _env_path() -> Path | None:
    """Find .env, including when this runs from a git worktree.

    .env is gitignored, so it exists only in the main checkout. Run from
    .claude/worktrees/<name>/ it is simply absent, and the first version of
    this script reported that as production being unreadable — the same
    mistake the 2026-08-16 note records: a missing local credential read as
    missing remote data.
    """
    here = ROOT / ".env"
    if here.exists():
        return here
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        main_checkout = Path(common).parent / ".env"
        if main_checkout.exists():
            return main_checkout
    return None


def load_env() -> dict[str, str]:
    """Read .env without importing dotenv (stdlib-only rule)."""
    env: dict[str, str] = {}
    p = _env_path()
    if p is not None:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k, v in os.environ.items():          # a real env var wins over .env
        env.setdefault(k, v)
    return env


ENV = load_env()
BASE = (ENV.get("RENDER_EXTERNAL_URL") or "https://orova-nova.onrender.com").rstrip("/")
KEY = ENV.get("DASHBOARD_API_KEY", "")


def http(path: str, method: str = "GET", body: dict | None = None,
         base: str | None = None, auth: bool = True, timeout: int = TIMEOUT):
    """Return (status_code, parsed_json_or_text). Never raises for HTTP errors."""
    url = (base or BASE) + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    # Some hosts (cal.com among them) reject urllib's default agent with 403.
    # Without this the booking check reports BROKEN on a link that works, and
    # a tool that cries wolf is a tool nobody runs.
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; orova-nova-cli/1.0)")
    req.add_header("Accept", "*/*")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if auth and KEY:
        req.add_header("X-API-Key", KEY)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:                                   # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def row(label: str, state: str, detail: str = "") -> None:
    print(f"  {label:<9} {detail:<44} {state}")


def header(text: str) -> None:
    print(f"\n  {text}")
    print("  " + "-" * 66)


# ── status ──────────────────────────────────────────────────────────────────
def cmd_status(_args) -> int:
    now_utc = datetime.now(timezone.utc)
    mnl = now_utc + timedelta(hours=8)
    pt = now_utc - timedelta(hours=7)
    print(f"\n  NOVA — {mnl:%Y-%m-%d %H:%M} Manila  ·  {pt:%a %H:%M} PT")
    print("  " + "=" * 66)

    problems: list[str] = []

    # build vs origin/main
    code, health = http("/health", auth=False)
    build = (health or {}).get("build", "") if isinstance(health, dict) else ""
    git("fetch", "origin", "--quiet")
    head = git("rev-parse", "origin/main")
    if code != 200:
        row("BUILD", BAD, f"/health returned {code or 'no response'}")
        problems.append("production is not answering")
    elif build and head.startswith(build[:7]):
        row("BUILD", OK, f"{build} = origin/main")
    else:
        row("BUILD", ACT, f"{build or '?'} vs origin/main {head[:12] or '?'}")
        problems.append("production is not running origin/main")

    if isinstance(health, dict):
        for field in ("db", "memory"):
            val = health.get(field)
            if val and val != "ok":
                row(field.upper(), BAD, f"{field} reports '{val}'")
                problems.append(f"{field} is {val}")

    # data — the field-level check, because a row count reconciles either way
    code, leads = http("/api/leads")
    if code == 200:
        rows = leads.get("leads", leads) if isinstance(leads, dict) else leads
        rows = rows if isinstance(rows, list) else []
        cover = sum(1 for x in rows if (x.get("insurance_amt") or 0) > 0)
        solo = sum(1 for x in rows if (x.get("principal_count") or 0) == 1)
        phone = sum(1 for x in rows if x.get("phone"))
        scores = {x.get("icp_score") or x.get("score") or 0 for x in rows}
        row("DATA", OK if rows else BAD,
            f"{len(rows)} leads · {cover} cover · {solo} solo · {phone} phone")
        # A single distinct score is the tell that the scorer is receiving nothing.
        if len(rows) > 3 and len(scores) == 1:
            row("SCORER", BAD, f"every lead scores {scores.pop()} — scorer has no input")
            problems.append("flat score across all leads")
    elif code in (401, 403):
        # Not an outage. The gate is working and this machine lacks the key.
        row("DATA", ACT, "no valid DASHBOARD_API_KEY here — cannot read")
        problems.append("set DASHBOARD_API_KEY in .env (production may be fine)")
    else:
        row("DATA", BAD, f"/api/leads returned {code}")
        problems.append("cannot read the lead list")

    # booking link — resolved, then actually fetched
    code, bl = http("/api/booking_link")
    link = bl.get("booking_link", "") if isinstance(bl, dict) else ""
    if code in (401, 403):
        row("BOOKING", DIM, "unknown — needs a key to ask")
    elif not link:
        row("BOOKING", ACT, "no link — a yes has nowhere to land")
        problems.append("CAL_COM_EVENT_SLUG unset in Render")
    else:
        st, _ = http("", base=link, auth=False, timeout=30)
        short = link.replace("https://cal.com/", "cal.com/")
        if st == 200:
            row("BOOKING", OK, f"{short[:42]} 200")
        else:
            row("BOOKING", BAD, f"{short[:38]} -> {st}")
            problems.append(f"booking link returns {st}")

    # the burned key
    if KEY and _is_burned(KEY):
        # The repo is public by decision, so a burned value is not merely
        # known-bad — it is readable in history by anyone, right now.
        row("KEY", BAD, "DASHBOARD_API_KEY is burned AND the repo is public")
        problems.append("rotate DASHBOARD_API_KEY — it is readable in public history")
    elif not KEY:
        row("KEY", ACT, "DASHBOARD_API_KEY missing from .env")
    else:
        row("KEY", OK, "not a known-burned value")

    # gates that stay closed on purpose — reported, never 'fixed'
    row("GATES", HOLD, "CALLS_AUTOPILOT=0 until the ADAD question is answered")

    header("BLOCKED ON YOU" if problems else "NOTHING BLOCKING")
    for i, p in enumerate(problems, 1):
        print(f"  {i}. {p}")
    if not problems:
        print("  Everything green. The only thing left is a phone call.")
    return 1 if any("not answering" in p or "cannot read" in p for p in problems) else 0


def _is_burned(value: str) -> bool:
    """Ask check_secrets, so there is one list of burned values, not two."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import check_secrets                                  # noqa: PLC0415
        return any(b in value for b in check_secrets.BURNED_LITERALS)
    except Exception:                                         # noqa: BLE001
        return False


# ── call sheet ──────────────────────────────────────────────────────────────
def cmd_calls(args) -> int:
    now_utc = datetime.now(timezone.utc)
    mnl = now_utc + timedelta(hours=8)
    pt = now_utc - timedelta(hours=7)

    # 6-9am Manila is 3-6pm Pacific: his morning, the contractor's afternoon.
    open_ = 6 <= mnl.hour < 9
    if open_:
        left = (mnl.replace(hour=9, minute=0) - mnl)
        window = f"OPEN — {left.seconds // 3600}h {(left.seconds // 60) % 60}m left"
    else:
        nxt = (mnl + timedelta(days=1)) if mnl.hour >= 9 else mnl
        until = nxt.replace(hour=6, minute=0, second=0) - mnl
        window = f"closed — opens in {until.seconds // 3600}h {(until.seconds // 60) % 60}m"

    print(f"\n  CALL SHEET — {mnl:%a %d %b %H:%M} Manila · {pt:%a %H:%M} PT")
    print(f"  Window (6-9am Manila = 3-6pm PT): {window}")
    print("  " + "=" * 66)

    code, leads = http("/api/leads")
    if code in (401, 403):
        print("  No valid DASHBOARD_API_KEY on this machine, so the list cannot")
        print("  be read here. That says nothing about production.")
        return 1
    if code != 200:
        print(f"  cannot read leads: {code}")
        return 1
    rows = leads.get("leads", leads) if isinstance(leads, dict) else leads
    rows = [r for r in (rows if isinstance(rows, list) else []) if r.get("phone")]

    worked = {"Archived", "Bad Number", "Meeting Booked", "Closed Won", "Closed Lost"}
    fresh = [r for r in rows if (r.get("status") or "New") not in worked]
    fresh.sort(key=lambda r: -(r.get("icp_score") or r.get("score") or 0))

    if not fresh:
        print("  Nothing unworked with a phone number.")
        return 0

    print(f"  {'id':>4}  {'score':>5}  {'cover':>7}  {'crew':<5}  {'business':<26}  phone")
    for r in fresh[: args.limit]:
        cover = r.get("insurance_amt") or 0
        crew = "solo" if (r.get("principal_count") or 0) == 1 else (
            str(r.get("principal_count") or "?"))
        money = f"${cover / 1_000_000:.1f}M" if cover >= 1_000_000 else (
            f"${cover / 1_000:.0f}K" if cover else "—")
        print(f"  {str(r.get('id','?')):>4}  "
              f"{int(r.get('icp_score') or r.get('score') or 0):>5}  "
              f"{money:>7}  "
              f"{crew:<5}  {str(r.get('business',''))[:26]:<26}  {r.get('phone','')}")

    top = fresh[0]
    header("AFTER EACH CALL — paste into Telegram")
    print(f"  /outcome {top.get('id')} talked <what he actually said>")
    print(f"  /outcome {top.get('id')} na | vm | gk | cb | ni | bad")
    print("\n  na=no answer  vm=voicemail  gk=gatekeeper  cb=call back"
          "  ni=not interested  bad=wrong number")

    header("THE ASK (playbook — diagnose before prescribing)")
    print("  Open:  \"When your crew finishes the job they're on, what's next?\"")
    print("  Never: a price. commercial_terms is UNRESOLVED.")
    print("  Never: \"we're AI-operated\" — worthless to him. (Answering")
    print("         \"are you a bot?\" honestly is different: always do that.)")
    return 0


# ── leaks ───────────────────────────────────────────────────────────────────
def cmd_leaks(_args) -> int:
    """What the internet can see. Reports exposure, never the value."""
    print("\n  LEAK CHECK")
    print("  " + "=" * 66)
    findings: list[str] = []

    # 1. the committed-secret scanner
    r = subprocess.run(  # noqa: S603 - fixed argv: this interpreter, a repo script
        [sys.executable, str(ROOT / "scripts" / "check_secrets.py")],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        row("TREE", OK, "no burned literals, no hardcoded credentials")
    else:
        row("TREE", BAD, "committed credential — see output below")
        findings.append("check_secrets failed")
        print(r.stdout)

    # 2. repo visibility, unauthenticated
    # PUBLIC IS DELIBERATE (owner decision, 2026-08-21): the repo is connected
    # to Mark's Make.com scenarios. It had been flipped private and back three
    # times because the reason was never written down anywhere, so it is
    # written here, in the tool that checks it.
    #
    # Public is therefore reported as POSTURE, not as a finding. What it does
    # change: the git HISTORY and merged PR diffs are world-readable, so any
    # credential ever committed is permanently burned, and prospect PII in old
    # diffs stays reachable. Those are the things worth flagging.
    slug = _repo_slug()
    if not slug:
        row("REPO", DIM, "no github remote found")
    else:
        code, _ = http(f"/repos/{slug}", base="https://api.github.com",
                       auth=False, timeout=30)
        if code == 200:
            row("REPO", DIM, "PUBLIC by decision (Make.com) — history is world-readable")
        elif code == 404:
            row("REPO", OK, f"{slug} is private (404 unauthenticated)")
        else:
            row("REPO", DIM, f"github returned {code}")

    # 3. live env values reachable in the tree.
    #    Presence only — printing the value to prove it is exposed is the
    #    mistake that caused the second leak.
    watch = ("DASHBOARD_API_KEY", "RETELL_API_KEY", "TELEGRAM_BOT_TOKEN",
             "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN", "AGENTMAIL_API_KEY",
             "META_APP_SECRET", "OPENAI_API_KEY", "GROQ_API_KEY", "OROVA_SECRET")
    tracked = [ROOT / p for p in git("ls-files").splitlines() if p.strip()]
    exposed: list[str] = []
    for name in watch:
        val = ENV.get(name, "").strip()
        if len(val) < 6:                       # too short to search for meaningfully
            continue
        for path in tracked:
            if path.name == "check_secrets.py" or not path.is_file():
                continue
            try:
                if val in path.read_text(encoding="utf-8", errors="ignore"):
                    exposed.append(f"{name} appears in {path.relative_to(ROOT)}")
                    break
            except OSError:
                continue
    if exposed:
        row("ENV", BAD, f"{len(exposed)} live value(s) in tracked files")
        for e in exposed:
            print(f"      - {e}")
        findings.extend(exposed)
    else:
        row("ENV", OK, f"none of {len(watch)} live values appear in tracked files")

    # 4. is .env itself safe
    if git("ls-files", "--error-unmatch", ".env"):
        row(".ENV", BAD, ".env is TRACKED by git")
        findings.append(".env is tracked")
    else:
        row(".ENV", OK, "gitignored, never committed")

    header("CLEAN" if not findings else f"{len(findings)} FINDING(S)")
    if not findings:
        print("  Nothing reachable that shouldn't be.")
    return 1 if findings else 0


def _repo_slug() -> str:
    url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]+([^/]+/[^/.]+)", url)
    return m.group(1) if m else ""


# ── gates ───────────────────────────────────────────────────────────────────
def cmd_gates(_args) -> int:
    """The three things CI will fail you on, run locally, in CI's own form."""
    print("\n  GATES")
    print("  " + "=" * 66)
    checks = [
        ("secrets", [sys.executable, "scripts/check_secrets.py"]),
        ("knowledge", [sys.executable, "scripts/compile_knowledge.py", "--check"]),
        ("ruff", ["ruff", "check", "--no-cache", "--select",
                  "S102,S301,S307,S506,S602,S603,S605,S608",
                  "app/", "scripts/", "tests/", ".claude/"]),
    ]
    failed = 0
    for name, cmd in checks:
        try:
            # S603: `cmd` comes from the literal `checks` list above, not input.
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True,  # noqa: S603
                               text=True, timeout=300)
        except FileNotFoundError:
            row(name, DIM, f"{cmd[0]} not installed")
            continue
        except subprocess.TimeoutExpired:
            row(name, BAD, "timed out")
            failed += 1
            continue
        if r.returncode == 0:
            row(name, OK, "passed")
        else:
            row(name, BAD, "FAILED")
            print((r.stdout or r.stderr).strip()[:600])
            failed += 1
    return 1 if failed else 0


# ── hunt ────────────────────────────────────────────────────────────────────
def cmd_hunt(args) -> int:
    """Kick a lead hunt. Spends budget, so it asks first unless -y."""
    body = {k: v for k, v in (("niche", args.niche), ("location", args.location),
                              ("state", args.state)) if v}
    print(f"\n  HUNT  {body or '(env rotation — TARGET_NICHE is stale-generic)'}")
    if not args.yes:
        print("  This calls LLM/registry APIs and spends budget.")
        if input("  Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("  Cancelled.")
            return 0
    code, before = http("/api/leads")
    n_before = len((before.get("leads", before) if isinstance(before, dict) else before) or [])
    code, res = http("/api/actions/hunt-leads", method="POST", body=body)
    print(f"  -> {code} {json.dumps(res)[:200] if not isinstance(res, str) else res[:200]}")
    if code != 200:
        return 1
    # A hunt returning ok proved nothing in the past; the lane was a silent
    # no-op for weeks. Count rows instead of trusting the status field.
    print(f"  leads before: {n_before}. Re-run 'nova.py status' in a minute"
          f" — 'ok' is not evidence that anything was saved.")
    return 0


# ── outcome ─────────────────────────────────────────────────────────────────
def cmd_outcome(args) -> int:
    """Log a disposition without opening Telegram."""
    text = f"/outcome {args.lead_id} {args.disposition}"
    if args.notes:
        text += " " + " ".join(args.notes)
    try:
        sys.path.insert(0, str(ROOT))
        import asyncio                                        # noqa: PLC0415
        from app.core.event_log import handle_outcome_command  # noqa: PLC0415
        reply = asyncio.run(handle_outcome_command(text))
        print(f"\n  {reply}")
        return 0
    except Exception as e:                                    # noqa: BLE001
        print(f"\n  Could not log locally ({type(e).__name__}: {e}).")
        print(f"  Send this to Nova on Telegram instead:\n    {text}")
        return 1


# ── entry ───────────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(
        prog="nova", description="Operate Nova from one command.")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("status", help="is anything broken, what is blocked on you")
    c = sub.add_parser("calls", help="who to ring, in what order")
    c.add_argument("--limit", type=int, default=10)
    sub.add_parser("leaks", help="secrets + what the internet can see")
    sub.add_parser("gates", help="the three CI gates, locally")

    h = sub.add_parser("hunt", help="kick a lead hunt (spends budget)")
    h.add_argument("--niche"); h.add_argument("--location"); h.add_argument("--state")
    h.add_argument("-y", "--yes", action="store_true", help="skip confirmation")

    o = sub.add_parser("outcome", help="log a call disposition")
    o.add_argument("lead_id"); o.add_argument("disposition")
    o.add_argument("notes", nargs="*")

    args = p.parse_args()
    if args.cmd in (None, "all"):
        rc = cmd_status(args)
        cmd_calls(argparse.Namespace(limit=10))
        return rc
    return {"status": cmd_status, "calls": cmd_calls, "leaks": cmd_leaks,
            "gates": cmd_gates, "hunt": cmd_hunt, "outcome": cmd_outcome}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
