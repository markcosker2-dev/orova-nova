"""No unauthorised offer may live in business_context.json.

An unapproved "free two-week pilot" appeared in this file and reached BOTH
live Retell agents. It sat in five prospect-facing places — the outbound
script, the voicemail, two objection handlers and the inbound branch — while
the same file banned "free" as a spam trigger word and `commercial_terms`
described a *paid* $1,500-2,000/mo pilot. The file contradicted itself, and
the version the agents spoke was the one nobody authorised.

Nothing in the codebase reads `retell_pitch` / `retell_inbound`: they are the
human-maintained SOURCE OF TRUTH that gets pasted into Retell's dashboard.
That is precisely why a silent edit here reaches production speech with no
test, no review and no deploy.

So this test guards the words a prospect can actually hear.

The owner has NOT set an offer. Until they do, there is nothing to offer, and
these assertions should fail rather than be relaxed.
"""
import json
import re
from pathlib import Path

import pytest

CTX_PATH = Path(__file__).resolve().parent.parent / "app" / "core" / "business_context.json"
CTX = json.loads(CTX_PATH.read_text(encoding="utf-8"))

# Sections a prospect can hear or read.
PROSPECT_FACING = ("retell_pitch", "retell_inbound", "outreach", "email_rules",
                   "value_propositions", "sales_funnel")

# AFFIRMATIVE offer constructions. Deliberately not the bare word "free": the
# file legitimately contains prohibitions ("never say the word 'free'"), and a
# test that cannot tell a ban from an offer gets deleted the first time it
# cries wolf.
OFFER_RE = re.compile(
    r"""(
        \bfor\s+free\b
      | \b(?:is|it'?s|itself\s+is)\s+free\b
      | \bfree\s+(?:two|2)[-\s]?week
      | \b(?:two|2)[-\s]?week\s+(?:free|trial|pilot)
      | \bfree\s+(?:trial|pilot|month|week|run)
      | \bno\s+charge\b
      | \bowe\s+nothing\b
      | \byou\s+(?:don'?t|do\s+not|won'?t)\s+pay\b
      | \bwon'?t\s+cost\s+you\b
      | \btrial\s+run\b
      | \bseven[-\s]?fifty\b
      | \bseven\s+hundred\s+and\s+fifty\b
      | \$\s?750\b
      | \bmoney[-\s]?back\b
      | \brisk[-\s]?free\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def _is_internal(path: str) -> bool:
    """Rules and notes, not lines a prospect hears.

    Underscore-prefixed keys are internal directives, and `never_say` is a
    prohibition list. Both must be free to NAME the banned thing in order to
    ban it — "never say 'free two-week pilot'" is the fix, not the defect.
    """
    return (any(part.lstrip("[").startswith("_") for part in path.split("."))
            or "never_say" in path)


def _prospect_facing_strings():
    for section in PROSPECT_FACING:
        for path, val in _walk(CTX.get(section), section):
            if _is_internal(path):
                continue
            yield path, val


def test_business_context_is_valid_json():
    assert isinstance(CTX, dict) and CTX


def test_no_offer_language_in_prospect_facing_copy():
    """The regression itself: no affirmative offer anywhere a prospect hears."""
    found = [(p, OFFER_RE.search(v).group(0)) for p, v in _prospect_facing_strings()
             if OFFER_RE.search(v)]
    assert not found, (
        "Unauthorised offer language is back in prospect-facing copy: "
        + "; ".join(f"{p} -> {m!r}" for p, m in found)
    )


def test_no_price_is_quoted_in_the_call_scripts():
    """Nova must not voice a number. Money goes to Mark."""
    price = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?!\s*(?:,|\)|\s*$))|\b\d{3,5}\s*(?:a|per)\s*month\b",
                       re.IGNORECASE)
    offenders = []
    for path, val in _walk(CTX.get("retell_pitch"), "retell_pitch"):
        # Keys beginning with _ are internal notes/rules, not spoken lines, and
        # they legitimately name the forbidden numbers in order to forbid them.
        if any(part.startswith("_") for part in path.split(".")):
            continue
        if "never_say" in path or "objection_handling" in path:
            continue          # prohibition lists name the numbers to ban them
        if price.search(val):
            offenders.append((path, price.search(val).group(0)))
    assert not offenders, f"a price is quoted in a spoken line: {offenders}"


def test_the_hard_offer_rule_is_present():
    """The rule must exist explicitly, not merely be implied by absence."""
    rule = CTX["retell_pitch"].get("_offer_rule", "")
    assert "DOES NOT MAKE OFFERS" in rule.upper()
    for forbidden in ("price", "trial", "pilot", "discount", "free"):
        assert forbidden in rule.lower(), f"the offer rule does not name {forbidden!r}"


def test_never_say_leads_with_the_offer_ban():
    assert "NOT MAKE AN OFFER" in CTX["retell_pitch"]["never_say"][0].upper()


def test_commercial_terms_marks_the_offer_unresolved():
    """`first_client_pilot` is internal thinking, not an approved offer — the
    file must say so, because it previously read as an instruction to offer."""
    terms = CTX["commercial_terms"]
    assert "UNRESOLVED" in terms.get("_offer_status", "").upper()
    assert "NOT AN APPROVED OFFER" in terms.get("first_client_pilot", "").upper()


def test_voicemail_makes_no_offer():
    msg = CTX["retell_pitch"]["step_5_voicemail"]["message"]
    assert not OFFER_RE.search(msg), f"voicemail contains an offer: {msg!r}"
    assert "free" not in msg.lower()


def test_cost_objection_deflects_rather_than_answering():
    answer = CTX["retell_pitch"]["objection_handling"]["what_does_it_cost"]
    assert "DEFLECT" in answer.upper()
    assert not re.search(r"\$\s?\d", answer), "the cost objection quotes a number"


def test_no_fabricated_social_proof_claim_survives():
    """Adjacent hard line: there are zero clients, and nothing may imply otherwise."""
    claims = re.compile(r"\bour clients\b|\bcase stud(?:y|ies) show\b|\bclients have\b",
                        re.IGNORECASE)
    found = [(p, v) for p, v in _prospect_facing_strings() if claims.search(v)]
    assert not found, f"implies clients that do not exist: {found}"
