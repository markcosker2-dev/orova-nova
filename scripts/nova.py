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
    python scripts/nova.py brief 4         everything known, before you dial
    python scripts/nova.py brief --top 3 --research
    python scripts/nova.py leaks           secrets + what the internet can see
    python scripts/nova.py gates           the three CI gates, locally
    python scripts/nova.py logs --errors     what production is actually saying
    python scripts/nova.py deploy           watch a deploy land, verify data survived
    python scripts/nova.py config           which capabilities are live IN PRODUCTION
    python scripts/nova.py agents           lane status, or --run <lane>
    python scripts/nova.py sheet            resync the Leads sheet
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

# Windows consoles default to cp1252 and production logs are full of em-dashes
# and box characters. Without this the tool dies with UnicodeEncodeError while
# printing the very error you ran it to see.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

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

    # Production capability report. The vault records this as "genuinely
    # unverified either way" because it only printed at boot and rotated out of
    # the 100-line buffer — but /api/health carries it live. An earlier audit
    # reported 6/13 from a LOCAL boot with no .env, which measured the
    # auditor's laptop rather than Render. Ask production.
    code, h = http("/api/health")
    if code == 200 and isinstance(h, dict):
        env_c = (h.get("hardening") or {}).get("env_contract") or {}
        live, total = env_c.get("capabilities_live"), env_c.get("capabilities_total")
        disabled = env_c.get("disabled_capabilities") or {}
        if live is not None:
            row("CONFIG", OK if live == total else DIM, f"{live}/{total} capabilities live")
            for name in list(disabled)[:5]:
                print(f"      off: {name}")
        mem = h.get("memory") or {}
        if mem.get("critical"):
            row("MEMORY", BAD, f"{mem.get('memory_mb', 0):.0f}MB of {mem.get('limit_mb')}MB")
            problems.append("memory critical")
        if h.get("errors"):
            row("ERRORS", ACT, f"{h['errors']} in the last 24h — nova.py logs --errors")

    # gates that stay closed on purpose — reported, never 'fixed'
    row("GATES", HOLD, "CALLS_AUTOPILOT=0 until the ADAD question is answered")
    if "national DNC scrub" in str((h or {}) if isinstance(h, dict) else ""):
        row("DNC", HOLD, "no DNC scrub configured — is_dnc_registered fails OPEN")

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


# ── logs ────────────────────────────────────────────────────────────────────
_ERR_RE = re.compile(r"AI-FAIL|ERROR|CRITICAL|Traceback|Exception|failed|"
                     r"locked|no such table|invalid_grant|429|5\d\d ", re.IGNORECASE)


def cmd_logs(args) -> int:
    """What production is actually saying.

    The buffer is only ~100 lines, so a success message from twenty minutes ago
    is already gone. Twice in one session an absent log line was read as
    "the join failed silently" when it had simply rotated past. Absence here is
    not evidence.
    """
    code, res = http("/api/logs")
    if code in (401, 403):
        print("\n  No valid DASHBOARD_API_KEY on this machine.")
        return 1
    if code != 200:
        print(f"\n  /api/logs returned {code}")
        return 1
    lines = res.get("logs", []) if isinstance(res, dict) else []
    if isinstance(lines, str):
        lines = lines.splitlines()
    if args.grep:
        lines = [x for x in lines if args.grep.lower() in str(x).lower()]
    if args.errors:
        lines = [x for x in lines if _ERR_RE.search(str(x))]
    print(f"\n  LOGS  ({len(lines)} matching, buffer holds ~100 lines)")
    print("  " + "=" * 66)
    for line in lines[-args.n:]:
        if isinstance(line, dict):
            text = f"{line.get('ts', ''):>8}  {line.get('msg', line)}"
        else:
            text = str(line)
        print("  " + text.rstrip()[:160])
    if not lines:
        print("  Nothing matched. The buffer is small — absence is not evidence.")
    return 0


# ── deploy ──────────────────────────────────────────────────────────────────
def cmd_deploy(args) -> int:
    """Watch a deploy land, then check the data survived it.

    Render's disk is ephemeral: every deploy destroys the DB and restores from
    the Leads sheet. A reconciling ROW COUNT proves nothing about fields — cover
    went 30 -> 10 across one deploy while the count reconciled at 40/40 — so
    this compares the fields too, and says which ones moved.
    """
    import time                                              # noqa: PLC0415
    git("fetch", "origin", "--quiet")
    want = git("rev-parse", "origin/main")[:12]
    if not want:
        print("\n  Cannot read origin/main.")
        return 1

    before = _snapshot()
    print(f"\n  DEPLOY  waiting for {want}")
    print(f"  before: {_fmt(before)}")

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        code, h = http("/health", auth=False, timeout=30)
        build = h.get("build", "") if isinstance(h, dict) else ""
        if build and want.startswith(build[:7]):
            print(f"  live:   {build}")
            after = _snapshot()
            print(f"  after:  {_fmt(after)}")
            return _compare(before, after)
        time.sleep(args.interval)
    print(f"  timed out after {args.timeout}s — still not on {want}")
    return 1


def _snapshot() -> dict:
    code, leads = http("/api/leads")
    if code != 200:
        return {}
    rows = leads.get("leads", leads) if isinstance(leads, dict) else leads
    rows = rows if isinstance(rows, list) else []
    return {
        "leads": len(rows),
        "cover": sum(1 for x in rows if (x.get("insurance_amt") or 0) > 0),
        "solo": sum(1 for x in rows if (x.get("principal_count") or 0) == 1),
        "phone": sum(1 for x in rows if x.get("phone")),
        "email": sum(1 for x in rows if x.get("email")),
    }


def _fmt(s: dict) -> str:
    return " · ".join(f"{k} {v}" for k, v in s.items()) if s else "(unreadable)"


def _compare(before: dict, after: dict) -> int:
    if not before or not after:
        print("  Could not compare — one side unreadable.")
        return 1
    lost = {k: (before[k], after[k]) for k in before if after.get(k, 0) < before[k]}
    if not lost:
        print("  OK — nothing lost across the deploy.")
        return 0
    print("  DATA LOSS across the deploy:")
    for k, (b, a) in lost.items():
        print(f"    {k}: {b} -> {a}")
    print("  A field with no column in WORKSHEET_HEADERS['Leads'] cannot survive.")
    return 1


# ── config ──────────────────────────────────────────────────────────────────
def cmd_config(_args) -> int:
    """Which capabilities are live IN PRODUCTION — not on this laptop."""
    code, h = http("/api/health")
    if code in (401, 403):
        print("\n  No valid DASHBOARD_API_KEY on this machine.")
        return 1
    if code != 200 or not isinstance(h, dict):
        print(f"\n  /api/health returned {code}")
        return 1
    env_c = (h.get("hardening") or {}).get("env_contract") or {}
    live, total = env_c.get("capabilities_live"), env_c.get("capabilities_total")
    print(f"\n  PRODUCTION CAPABILITIES — {live}/{total} live")
    print("  " + "=" * 66)
    print("  (Asked of Render. A local boot with no .env reports missing")
    print("   capabilities by construction and measures nothing.)")
    missing = env_c.get("missing_required") or []
    if missing:
        print(f"\n  MISSING REQUIRED: {', '.join(map(str, missing))}")
    dis = env_c.get("disabled_capabilities") or {}
    if dis:
        print()
        for name, why in dis.items():
            print(f"  off   {name:<34} {why}")
    else:
        print("\n  Everything configured.")
    # A provider catalog that turns over under a hardcoded slug has now cost
    # this project twice — OpenRouter in 2026-07, Groq in 2026-08 — and both
    # times the symptom was silence, because every caller fails open. Ask the
    # provider whether the configured model still exists.
    _check_llm_model()

    sched = h.get("scheduler") or {}
    if sched:
        print("\n  LANES")
        for lane, state in sched.items():
            print(f"  {'ok ' if state == 'Active' else '-- '}  {lane:<20} {state}")
    return 0


def _check_llm_model() -> None:
    """Is the configured Groq model still on the account?"""
    key = ENV.get("GROQ_API_KEY", "").strip()
    if not key:
        return
    try:
        src = (ROOT / "app" / "core" / "ai_client.py").read_text(encoding="utf-8")
        m = re.search(r'GROQ_MODEL\s*=\s*["\']([^"\']+)["\']', src)
    except OSError:
        return
    if not m:
        return
    configured = m.group(1)
    req = urllib.request.Request("https://api.groq.com/openai/v1/models")
    req.add_header("Authorization", f"Bearer {key}")
    # Groq 403s urllib's default agent, exactly as cal.com does. Same lesson,
    # second time in this file: any request built outside http() has to carry
    # the User-Agent too, or the check reports a failure that is its own.
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; orova-nova-cli/1.0)")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            models = {x.get("id") for x in json.loads(r.read().decode()).get("data", [])}
    except Exception:                                        # noqa: BLE001
        print("\n  LLM       could not reach Groq to verify the model")
        return
    if configured in models:
        print(f"\n  LLM       {configured} is live on this key")
    else:
        print(f"\n  LLM       {BAD}: GROQ_MODEL '{configured}' is NOT on this key.")
        print("            Every Tier-1 call 404s and falls through silently.")
        chat = sorted(x for x in models
                      if not any(k in x for k in ("whisper", "guard", "orpheus")))
        print(f"            Available: {', '.join(chat[:6])}")


# ── agents ──────────────────────────────────────────────────────────────────
def cmd_agents(args) -> int:
    if args.run:
        print(f"\n  Running lane '{args.run}' ...")
        code, res = http("/api/agents/run", method="POST", body={"agent": args.run})
        print(f"  -> {code} {str(res)[:300]}")
        # 'ok' has meant 'did nothing' here before: a fire-and-forget task was
        # garbage collected and the error callback skipped cancelled tasks.
        print("  'ok' is not evidence of work — check `nova.py logs` next.")
        return 0 if code == 200 else 1
    code, res = http("/api/agents")
    if code != 200:
        print(f"\n  /api/agents returned {code}")
        return 1
    print("\n  AGENTS")
    print("  " + "=" * 66)
    items = res.get("agents", res) if isinstance(res, dict) else res
    print("  " + json.dumps(items, indent=2)[:2000])
    return 0


# ── sheet ───────────────────────────────────────────────────────────────────
def cmd_sheet(_args) -> int:
    """Resync the Leads sheet — a new column does not backfill itself."""
    print("\n  Resyncing the Leads sheet (paced inside Google's 60 reads/min) ...")
    code, res = http("/api/actions/resync-sheet", method="POST", body={})
    print(f"  -> {code} {str(res)[:300]}")
    return 0 if code == 200 else 1


# ── brief ───────────────────────────────────────────────────────────────────
# Everything outbound_dialer.py assembles for Retell, rendered for the human
# who is actually allowed to make the call.
#
# The AI caller has had a careful per-call context for months — business, owner
# first name, crew_status, niche, icebreaker — while CALLS_AUTOPILOT=0 keeps it
# from ever using it. Mark, who is not an ADAD and can dial today, had none of
# it. This is the same assembly pointed at the person instead of the machine.
#
# Two facts are read from their canonical owners rather than restated here:
#   · crew_status  -> app.skills.lead_validator (CLAUDE.md single-source rule)
#   · the pains    -> app/core/business_context.json
# Restating either would create a second writer of the same fact, which is the
# defect that put four different meeting durations into the copy at once.

def _business_context() -> dict:
    try:
        return json.loads((ROOT / "app" / "core" / "business_context.json")
                          .read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return {}


def _pain_guidance() -> str:
    """The painkiller framing, verbatim from the canonical business context."""
    bc = _business_context()
    return ((bc.get("outreach") or {}).get("initial_email_framework") or {}).get("value", "")


def _crew_status(lead: dict) -> str:
    """Delegate to the canonical implementation; never guess.

    UNKNOWN is a real answer. 58.9% of WA contractors are single-principal, so
    a default is a coin flip that opens the call on the wrong pain — which
    burns the one question the opener gets.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from app.skills.lead_validator import crew_status   # noqa: PLC0415
        return crew_status(lead)
    except Exception:                                        # noqa: BLE001
        n = lead.get("principal_count")
        try:
            n = int(n or 0)
        except (TypeError, ValueError):
            return "unknown"
        return "unknown" if n <= 0 else ("solo" if n == 1 else "has_crew")


async def _research(lead: dict) -> dict:
    try:
        sys.path.insert(0, str(ROOT))
        from app.skills.dossier import build_dossier         # noqa: PLC0415
        return await build_dossier(lead) or {}
    except Exception as e:                                   # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def cmd_brief(args) -> int:
    code, data = http("/api/leads")
    if code in (401, 403):
        print("\n  No valid DASHBOARD_API_KEY on this machine.")
        return 1
    if code != 200:
        print(f"\n  /api/leads returned {code}")
        return 1
    rows = data.get("leads", data) if isinstance(data, dict) else data
    rows = rows if isinstance(rows, list) else []

    if args.lead_id:
        picked = [r for r in rows if str(r.get("id")) == str(args.lead_id)]
        if not picked:
            print(f"\n  No lead with id {args.lead_id}.")
            return 1
    else:
        worked = {"Archived", "Bad Number", "Meeting Booked", "Closed Won", "Closed Lost"}
        picked = [r for r in rows
                  if r.get("phone") and (r.get("status") or "New") not in worked]
        picked.sort(key=lambda r: -(r.get("icp_score") or r.get("score") or 0))
        picked = picked[: args.top]

    if args.research:
        billable = [r for r in picked if (r.get("website") or "").startswith("http")]
        if not billable:
            print("\n  None of these have a website to research.")
        else:
            print(f"\n  Researching {len(billable)} website(s). This calls the "
                  f"scraper and an LLM.")
            if not args.yes and input("  Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                print("  Skipping research; showing stored data only.")
                args.research = False

    for lead in picked:
        _print_brief(lead, args)
    return 0


def _print_brief(lead: dict, args) -> None:
    import asyncio                                           # noqa: PLC0415

    lid = lead.get("id")
    crew = _crew_status(lead)
    cover = lead.get("insurance_amt") or 0
    owner = (lead.get("owner") or "").strip()
    first = owner.split()[0] if owner else ""
    score = int(lead.get("icp_score") or lead.get("score") or 0)

    print("\n  " + "=" * 66)
    print(f"  LEAD {lid} — {str(lead.get('business', '')).upper()}"
          f"{' ' * max(1, 46 - len(str(lead.get('business', ''))))}score {score}")
    print("  " + "=" * 66)
    print(f"  Owner    {owner or '(unknown)':<28} ask for {first or '(no first name)'}")
    print(f"  Phone    {lead.get('phone') or '(none)':<28} {lead.get('state') or ''}")
    money = f"${cover / 1_000_000:.1f}M" if cover >= 1_000_000 else (
        f"${cover / 1_000:.0f}K" if cover else "not on file")
    print(f"  Cover    {money:<28} {lead.get('vertical') or ''}")

    if crew == "solo":
        print("  Crew     SOLO — one named principal on the licence")
        print("           His deadline is his OWN calendar, not payroll.")
        print("           Solo is a DISCOUNT, not a disqualification: 42% of")
        print("           contractors above the $1M cover minimum are solo.")
    elif crew == "has_crew":
        print(f"  Crew     HAS CREW — {lead.get('principal_count')} named principals")
        print("           He feels payroll every Friday. That is the deadline.")
    else:
        print("  Crew     UNKNOWN — the registry named no principals")
        print("           ASK on the call. Do not guess: ~59% of WA contractors")
        print("           are single-principal, so either default is a coin flip")
        print("           that opens on the wrong pain.")

    site = lead.get("website") or ""
    print(f"  Site     {site or '(none on file)'}")

    ice = (lead.get("icebreaker") or "").strip()
    if args.research and site.startswith("http"):
        res = asyncio.run(_research(lead))
        if res.get("_error"):
            print(f"  Research FAILED — {res['_error']}")
            print("           (fail-open by design; the brief still stands)")
        elif res:
            ice = (res.get("icebreaker") or ice).strip()
            for obs in (res.get("observations") or [])[:3]:
                print(f"  Observed {obs}")
            for sig in (res.get("premium_signals") or [])[:2]:
                print(f"  Premium  {sig}")
        else:
            print("  Research nothing usable found on the site")
    if ice:
        print(f"  Opener   \"{ice}\"")

    guidance = _pain_guidance()
    if guidance:
        print("\n  THE PAINKILLER (canonical, business_context.json)")
        for line in _wrap(guidance, 64):
            print(f"    {line}")

    print("\n  NEVER")
    print("    · state or imply a price — commercial_terms is UNRESOLVED")
    print("    · pitch \"we're AI-operated\" — worthless to him")
    print("      (answering \"are you a bot?\" honestly is different: always do that)")
    print("    · sell growth/more leads — that is a vitamin, and it loses to")
    print("      Angi's ~$400 anchor at 16x")

    print("\n  AFTER")
    print(f"    /outcome {lid} talked <what he actually said>")
    print(f"    /outcome {lid} na | vm | gk | cb | ni | bad")


def _wrap(text: str, width: int) -> list[str]:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


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

    b = sub.add_parser("brief", help="everything known about a lead, before you dial")
    b.add_argument("lead_id", nargs="?", help="one lead; omit for the top N")
    b.add_argument("--top", type=int, default=3)
    b.add_argument("--research", action="store_true",
                   help="scrape the site for an icebreaker (costs LLM calls)")
    b.add_argument("-y", "--yes", action="store_true", help="skip the research prompt")

    lg = sub.add_parser("logs", help="what production is actually saying")
    lg.add_argument("-n", type=int, default=40)
    lg.add_argument("--errors", action="store_true", help="only failure-shaped lines")
    lg.add_argument("--grep", help="substring filter")

    d = sub.add_parser("deploy", help="watch a deploy land, verify data survived")
    d.add_argument("--timeout", type=int, default=600)
    d.add_argument("--interval", type=int, default=20)

    sub.add_parser("config", help="capabilities live IN PRODUCTION")
    sub.add_parser("sheet", help="resync the Leads sheet")

    ag = sub.add_parser("agents", help="lane status, or --run <lane>")
    ag.add_argument("--run", help="lane name to trigger")

    o = sub.add_parser("outcome", help="log a call disposition")
    o.add_argument("lead_id"); o.add_argument("disposition")
    o.add_argument("notes", nargs="*")

    args = p.parse_args()
    if args.cmd in (None, "all"):
        rc = cmd_status(args)
        cmd_calls(argparse.Namespace(limit=10))
        return rc
    return {"status": cmd_status, "calls": cmd_calls, "leaks": cmd_leaks,
            "gates": cmd_gates, "hunt": cmd_hunt, "outcome": cmd_outcome,
            "logs": cmd_logs, "deploy": cmd_deploy, "config": cmd_config,
            "brief": cmd_brief,
            "agents": cmd_agents, "sheet": cmd_sheet}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
