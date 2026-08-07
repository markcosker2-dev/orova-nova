"""The secret scanner that gates CI (scripts/check_secrets.py).

Exists because of a real incident: the live `DASHBOARD_API_KEY` sat in 7
tracked files across 24 commits on a PUBLIC repo, authenticating
`/api/actions/hunt-leads` — a money-spending endpoint.

The scanner's failure modes are asymmetric and BOTH are tested here:

  · a miss lets a live credential onto a public repo
  · a false positive gets the scanner disabled, which causes the first one

The second is the reason the name-based rule alone was not enough. Run against
the real tree it flagged `MAX_TOKENS = "max_tokens"` (an enum member),
`token_uri = "https://oauth2.googleapis.com/token"` (a public endpoint) and
`SESSION_TOKEN_KEY = 'OROVA_SESSION_TOKEN'` (a sessionStorage key NAME). Those
exact shapes are pinned below as must-not-flag.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "check_secrets",
    Path(__file__).resolve().parent.parent / "scripts" / "check_secrets.py",
)
cs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cs)


def scan(line: str) -> list:
    return cs.scan_text("f.py", line)


# Credential fixtures are ASSEMBLED AT RUNTIME rather than written as literals.
#
# Not cosmetic: the first version of this file spelled them out, and GitHub's
# push protection blocked the push, correctly identifying them as a Stripe key
# and a Slack token. The available escape hatch is an "allow this secret" URL,
# which trains the repo to wave pushes through — the opposite of what this
# file is for.
#
# Splitting the prefix keeps the literal out of the committed bytes while
# `scan()` still receives the fully-assembled string, so the scanner's regexes
# are genuinely exercised.
FAKE_STRIPE = "sk_" + "live_" + "51Hq8vTGxAbCdEfGhIjKlMnOp"
FAKE_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
FAKE_GITHUB = "ghp_" + "aB3dE5gH7jK9lM1nO3pQ5rS7tU9vW1xY3zA5"
FAKE_SLACK = "xoxb" + "-123456789012-abcdefghijklmno"
FAKE_GOOGLE = "AIza" + "SyD-aBcDeFgHiJkLmNoPqRsTuVwXyZ12345"
FAKE_PEM = "-----BEGIN RSA " + "PRIVATE KEY-----"
BURNED = "nova_admin" + "_2026"      # the rotated DASHBOARD_API_KEY
# High-entropy but matching no provider format — exercises the generic rule.
FAKE_RANDOM = "Xk9" + "$mQ2vRt7Lp4Wz8Nc3Hy6Bd1Fg5Js0"


# ── must FLAG: things that are actually credentials ─────────────────────────

def test_burned_literal_is_flagged_anywhere():
    """The rotated key must never reappear, even as documentation."""
    out = scan(f'# example: {BURNED}')
    assert out and "BURNED CREDENTIAL" in out[0]


def test_burned_literal_flagged_in_a_header():
    out = scan(f'curl -H "X-API-Key: {BURNED}" https://x/api')
    assert out and "BURNED CREDENTIAL" in out[0]


@pytest.mark.parametrize("literal,label", [
    (FAKE_STRIPE, "Stripe"),
    (FAKE_AWS, "AWS"),
    (FAKE_GITHUB, "GitHub"),
    (FAKE_SLACK, "Slack"),
    (FAKE_GOOGLE, "Google"),
])
def test_known_credential_formats_are_flagged(literal, label):
    out = scan(f'THING = "{literal}"')
    assert out, f"{label} key not flagged"
    assert "CREDENTIAL FORMAT" in out[0]


def test_private_key_block_is_flagged():
    out = scan(FAKE_PEM)
    assert out and "private key" in out[0]


def test_random_looking_literal_on_a_secret_name_is_flagged():
    out = scan(f'DASHBOARD_API_KEY = "{FAKE_RANDOM}"')
    assert out and "HARDCODED SECRET" in out[0]


# ── must NOT flag: the real false positives that made v1 unusable ──────────

@pytest.mark.parametrize("line", [
    'MAX_TOKENS = "max_tokens"',                                  # enum member
    'token_uri="https://oauth2.googleapis.com/token"',            # public URL
    "const SESSION_TOKEN_KEY = 'OROVA_SESSION_TOKEN';",           # storage key
    "const DASHBOARD_SECRET_KEY = 'OROVA_DASHBOARD_SECRET';",     # storage key
])
def test_real_inert_lines_are_not_flagged(line):
    assert scan(line) == [], line


@pytest.mark.parametrize("line", [
    'API_KEY = os.getenv("DASHBOARD_API_KEY", "")',
    'expected = os.getenv("DASHBOARD_API_KEY")',
    'key = process.env.DASHBOARD_API_KEY',
])
def test_env_reads_are_not_flagged(line):
    assert scan(line) == [], line


@pytest.mark.parametrize("value", [
    "<your-key-here>", "replace-with-a-long-random-secret", "changeme",
    "$DASHBOARD_API_KEY", "${DASHBOARD_API_KEY}", "test-dashboard-key",
    "placeholder", "xxxxxxxxxxxx", "your_api_key",
])
def test_placeholders_are_not_flagged(value):
    assert scan(f'API_KEY = "{value}"') == [], value


def test_review_marker_suppresses_a_line():
    """`# noqa: secret` documents a reviewed, inert literal."""
    assert scan(f'K = "{FAKE_STRIPE}"  # noqa: secret') == []


def test_prose_is_not_a_credential():
    assert scan('SECRET = "the secret sauce is good pizza dough"') == []


# ── the real tree must be clean ────────────────────────────────────────────

def test_repository_has_no_committed_credentials():
    """The gate itself: this is what CI runs."""
    assert cs.main() == 0, "scripts/check_secrets.py found credentials in the tree"
