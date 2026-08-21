#!/usr/bin/env python
"""Fail the build if a live credential is committed.

Written after a real incident: the production `DASHBOARD_API_KEY` sat in 7
tracked files across 24 commits on a PUBLIC repo. It authenticated
`/api/actions/hunt-leads` — a money-spending endpoint — and one of those files
published a working POST recipe against it. The key was rotated 2026-08-05;
this exists so the next one cannot be committed at all.

Deliberately NARROW. A scanner that cries wolf gets disabled, and a disabled
scanner is worse than none, so this flags only two things:

  1. A known-burned literal (the leaked key) reappearing anywhere.
  2. A secret-shaped ASSIGNMENT — `API_KEY = "..."`, `TOKEN: "..."` — where the
     value is a plausible real credential rather than a placeholder.

It does NOT flag env reads (`os.getenv("API_KEY")`), placeholders, test
fixtures, or documentation that names a variable without giving its value.

The second incident (2026-08-21) is why rule 1 has no length floor and no
quoting requirement. The replacement key leaked through the VAULT, not through
code: seven tracked markdown files carried `DASHBOARD_API_KEY=<the value>`, one
of them noting that it worked. Rule 2 could not see it — the value was
unquoted, 9 characters, and single-character-class, so it failed the quoted-
literal match, the 20-char minimum and the entropy test in turn. A burned
literal is matched as a bare substring precisely so that the low-entropy case
rule 2 must ignore is still caught once the value is known to be burned.

The corollary rule 1 cannot enforce: do not DESCRIBE a live key either. The
same handoff that withheld the literal explained how to derive it from the
previous one, which leaks it just as well.

Usage:  python scripts/check_secrets.py [--all]
        (default scans tracked files; exit 1 on any finding)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Literals known to have been live and are now burned. A match is unambiguous:
# there is no legitimate reason for these to reappear in the tree.
BURNED_LITERALS = {
    "nova_admin_2026",          # DASHBOARD_API_KEY, leaked + rotated 2026-08-05
    "nova_2026",                # DASHBOARD_API_KEY, leaked + rotated 2026-08-21
}

# Known credential FORMATS. These are unambiguous — a string in one of these
# shapes is a credential, whatever variable it is bound to.
PROVIDER_PATTERNS = [
    (re.compile(r"\bsk_live_[A-Za-z0-9]{16,}"), "Stripe live secret key"),
    (re.compile(r"\brk_live_[A-Za-z0-9]{16,}"), "Stripe live restricted key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "GitHub personal access token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"), "GitHub fine-grained PAT"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI-style API key"),
    (re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "Google API key"),
    (re.compile(r"\bkey-[0-9a-zA-Z]{32}\b"), "Mailgun key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "private key block"),
]

# Secret-shaped assignment: a key-ish NAME bound to a quoted literal. Used only
# as a PRE-FILTER — the value must then also look like a real credential
# (_looks_like_credential), because the name alone is far too noisy. Live
# examples that a name-only rule flagged wrongly, all inert:
#   MAX_TOKENS = "max_tokens"                        (an enum member)
#   token_uri = "https://oauth2.googleapis.com/token" (a public endpoint)
#   DASHBOARD_SECRET_KEY = 'OROVA_DASHBOARD_SECRET'   (a sessionStorage key NAME)
_ASSIGN_RE = re.compile(
    r"""(?P<name>[A-Za-z0-9_\-]*(?:API_?KEY|SECRET|TOKEN|PASSWORD|PASSWD|
        ACCESS_?KEY|PRIVATE_?KEY|CLIENT_?SECRET|AUTH_?KEY)[A-Za-z0-9_\-]*)
        \s*[:=]\s*
        (?P<q>["'])(?P<val>[^"'\n]{8,})(?P=q)""",
    re.IGNORECASE | re.VERBOSE,
)

# Values that are obviously not credentials.
_PLACEHOLDER_RE = re.compile(
    r"""^(
        |.*\$\{.*\}.*            # ${VAR} interpolation
        |.*<.*>.*                # <your-key-here>
        |\$[A-Za-z_].*           # $DASHBOARD_API_KEY
        |.*(your|my|the)[-_ ]?(key|token|secret).*
        |.*(replace|example|sample|placeholder|changeme|change_me|dummy|fake
           |test|testing|mock|stub|redacted|removed|scrubbed|none|null|empty
           |xxx+|todo|tbd|insert|add[-_]?your|not[-_]?set|unset|default)\b.*
        |[-_x*.]+                # ---- / xxxx / ****
    )$""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[_\-][A-Za-z0-9]+)*$")


def _looks_like_credential(value: str) -> bool:
    """Does this literal have the shape of a real secret rather than a name?

    Real credentials are RANDOM: long, and mixing character classes without a
    word structure. Configuration identifiers are not — `max_tokens` and
    `OROVA_DASHBOARD_SECRET` are words joined by separators, in one case
    convention, and carry no entropy.

    Deliberately conservative: the burned-literal check above is what catches
    the known-bad low-entropy case, so this one can afford to only fire on
    things that genuinely look random.
    """
    v = value.strip()
    if len(v) < 20:
        return False
    if "://" in v or v.startswith(("/", "./", "../")):
        return False                       # a URL or a path, not a secret
    if " " in v:
        return False                       # prose
    classes = sum(bool(re.search(p, v)) for p in
                  (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    # A snake_case / SCREAMING_SNAKE identifier is a name, not a key — even a
    # long one. Requires BOTH cases present, or symbols beyond _ and -.
    if _IDENTIFIER_RE.match(v) and not (
            re.search(r"[a-z]", v) and re.search(r"[A-Z]", v)):
        return False
    return classes >= 3

# Paths where a literal is expected to be inert.
SKIP_DIRS = {".git", ".kilo", ".claude", "node_modules", "__pycache__",
             ".venv", "venv", "dist", "build", ".pytest_cache"}
SKIP_SUFFIXES = {".lock", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf",
                 ".woff", ".woff2", ".ttf", ".zip", ".gz", ".xlsx"}

# An inline `# noqa: secret` marks a reviewed, intentional literal.
ALLOW_MARKER = "noqa: secret"


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return [ROOT / p for p in out.split("\n") if p.strip()]


def is_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.match(value.strip()))


def scan_text(rel: str, text: str) -> list[str]:
    findings: list[str] = []
    lines = text.split("\n")

    for i, line in enumerate(lines, 1):
        if ALLOW_MARKER in line:
            continue

        for burned in BURNED_LITERALS:
            if burned in line:
                findings.append(
                    f"{rel}:{i}: BURNED CREDENTIAL — a known-leaked literal is "
                    f"back in the tree. It was rotated; do not reintroduce it "
                    f"even as an example."
                )

        for pat, label in PROVIDER_PATTERNS:
            if pat.search(line):
                findings.append(
                    f"{rel}:{i}: CREDENTIAL FORMAT — looks like a {label}. "
                    f"Move it to the environment and rotate it; anything "
                    f"committed must be treated as burned."
                )

        m = _ASSIGN_RE.search(line)
        if m:
            val = m.group("val")
            # An env read is not a hardcoded secret.
            if re.search(r"getenv|environ|process\.env", line, re.IGNORECASE):
                continue
            if not is_placeholder(val) and _looks_like_credential(val):
                findings.append(
                    f"{rel}:{i}: HARDCODED SECRET — {m.group('name')} is "
                    f"assigned a random-looking literal ({len(val)} chars). "
                    f"Read it from the environment instead, or append "
                    f"'# {ALLOW_MARKER}' if it is genuinely inert."
                )
    return findings


def main() -> int:
    findings: list[str] = []
    for path in tracked_files():
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        # This file necessarily contains the patterns it looks for.
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, IsADirectoryError):
            continue
        findings.extend(scan_text(str(path.relative_to(ROOT)).replace("\\", "/"),
                                  text))

    if findings:
        print("SECRET SCAN FAILED — %d finding(s):\n" % len(findings))
        for f in findings:
            print("  " + f)
        print("\nRotate anything real that was committed; git history is "
              "immutable, so a committed key is a burned key.")
        return 1

    print("[secrets] OK - no burned literals, no hardcoded credentials")
    return 0


if __name__ == "__main__":
    sys.exit(main())
