"""Tests for the WA L&I contractor-licence owner source.

Replaces the WA Secretary-of-State lookup, which was anti-bot gated and never
returned a name server-side (hence it shipped defaulted OFF). L&I publishes
licensed-contractor data on data.wa.gov via Socrata: no key, no quota, and
contractor-specific rather than all corporations.

The tests that matter most here are the STRICT-MATCH ones. Returning a real
person attached to the wrong company is fabricated lead data — the one
unforgivable failure in this project — so a miss must always beat a confident
wrong name.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.skills import owner_finder


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


def _client(payload, status=200):
    c = AsyncMock()
    c.get = AsyncMock(return_value=_Resp(payload, status))
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    return c


def _lookup(payload, business="Acme Roofing", status=200):
    with patch("app.skills.owner_finder.httpx.AsyncClient",
               return_value=_client(payload, status)):
        return asyncio.run(owner_finder._wa_registry_lookup(business))


def _row(businessname, principal, status="ACTIVE"):
    return {"businessname": businessname, "primaryprincipalname": principal,
            "contractorlicensestatus": status}


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv("WA_LNI_ENABLED", raising=False)  # defaults ON
    yield


# ─── Happy path ──────────────────────────────────────────────────

def test_resolves_principal_to_a_person_name():
    out = _lookup([_row("ACME ROOFING LLC", "SMITH, JANE MARIE")])
    assert out["owner"] == "Jane Smith"
    assert out["source"] == "wa_lni"
    assert out["title"] == "Licence Principal"
    assert out["confidence"] == 0.9


def test_legal_suffix_differences_still_match():
    # The scraped business name rarely carries the licence's legal form.
    for licensed in ("ACME ROOFING LLC", "ACME ROOFING, INC.", "ACME ROOFING CO"):
        out = _lookup([_row(licensed, "SMITH, JANE")], business="Acme Roofing")
        assert out["owner"] == "Jane Smith", licensed


def test_prefers_the_active_licence_when_duplicates_exist():
    rows = [_row("ACME ROOFING", "OLDPRINCIPAL, BOB", status="EXPIRED"),
            _row("ACME ROOFING", "NEWPRINCIPAL, ALICE", status="ACTIVE")]
    assert _lookup(rows)["owner"] == "Alice Newprincipal"


# ─── Strict matching — the fabrication guard ─────────────────────

def test_a_similar_but_different_company_is_rejected():
    """THE CRITICAL TEST. 'ACME ROOFING AND SIDING' is a different business
    from 'Acme Roofing'; returning its principal would attach a real person to
    the wrong company."""
    out = _lookup([_row("ACME ROOFING AND SIDING SPECIALISTS", "WRONG, PERSON")])
    assert out["owner"] == ""
    assert out["source"] == ""


def test_prefix_match_alone_is_not_accepted():
    # The Socrata query is a prefix search purely to keep the response small;
    # acceptance is decided client-side on exact normalized equality.
    out = _lookup([_row("ACME PLUMBING", "WRONG, PERSON")])
    assert out["owner"] == ""


def test_ambiguous_multi_principal_match_returns_nothing():
    """Two active licences under the same normalized name naming DIFFERENT
    people — picking either would be a coin flip presented as a fact."""
    rows = [_row("ACME ROOFING LLC", "SMITH, JANE"),
            _row("ACME ROOFING INC", "JONES, ROBERT")]
    out = _lookup(rows)
    assert out["owner"] == ""


def test_same_principal_under_two_licences_is_not_ambiguous():
    rows = [_row("ACME ROOFING LLC", "SMITH, JANE"),
            _row("ACME ROOFING INC", "SMITH, JANE M")]
    assert _lookup(rows)["owner"] == "Jane Smith"


# ─── Robustness ──────────────────────────────────────────────────

def test_no_rows_is_a_clean_miss():
    assert _lookup([])["owner"] == ""


def test_http_error_is_a_clean_miss():
    assert _lookup([], status=500)["owner"] == ""


def test_missing_principal_field_is_a_clean_miss():
    assert _lookup([_row("ACME ROOFING", "")])["owner"] == ""


def test_kill_switch_disables_the_source(monkeypatch):
    monkeypatch.setenv("WA_LNI_ENABLED", "0")
    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls:
        out = asyncio.run(owner_finder._wa_registry_lookup("Acme Roofing"))
    assert out["owner"] == ""
    client_cls.assert_not_called(), "must not spend a request when disabled"


def test_empty_business_name_is_a_clean_miss():
    assert asyncio.run(owner_finder._wa_registry_lookup(""))["owner"] == ""


def test_punctuation_only_business_name_does_not_build_a_wildcard_query():
    # A name that normalizes to nothing must not become a `like '%'` sweep.
    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls:
        out = asyncio.run(owner_finder._wa_registry_lookup("!!! ---"))
    assert out["owner"] == ""
    client_cls.assert_not_called()


# ─── Name parsing ────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("POWER, GREGORY MARK JR", "Gregory Power"),
    ("PASECHNIK, IAVIS", "Iavis Pasechnik"),
    ("JUAREZ JUAREZ, ALVARO", "Alvaro Juarez juarez"),
    ("ATKINSON, CONNOR OSLAND", "Connor Atkinson"),
    ("SULI, ANTOINETTE B", "Antoinette Suli"),
    ("MICHAEL BUEHS", "Michael Buehs"),          # already first-last
    ("", ""),
    ("SINGLENAME", ""),                           # cannot make a person of it
])
def test_person_from_principal(raw, expected):
    assert owner_finder._person_from_principal(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("Acme Roofing LLC", "ACME ROOFING"),
    ("ACME ROOFING, INC.", "ACME ROOFING"),
    ("A&B Builders Co", "A B BUILDERS"),
    ("  spaced   out  ", "SPACED OUT"),
])
def test_normalize_business(raw, expected):
    assert owner_finder._normalize_business(raw) == expected


# ─── Downstream scoring ──────────────────────────────────────────

def test_wa_lni_counts_as_a_registry_source_for_confidence():
    """A licence-board name is authoritative, so contact_confidence must score
    it as a registry (85 + title bonus), not as a text-mined guess (60)."""
    from app.skills.lead_validator import contact_confidence
    lead = {"owner": "Jane Smith", "owner_source": "wa_lni",
            "owner_title": "Licence Principal", "email": "", "phone": ""}
    scraped = dict(lead, owner_source="website")
    assert contact_confidence(lead)["owner"] > contact_confidence(scraped)["owner"]
    assert contact_confidence(lead)["owner"] >= 85


def test_single_token_business_name_is_refused():
    # LIVE FINDING (2026-07-25): the bare query "Acme" exact-matched a real WA
    # licence named "ACME" and returned its principal. Correct match, wrong
    # company — scraped names are often truncated, so one token is not enough
    # evidence to attach a person.
    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls:
        out = asyncio.run(owner_finder._wa_registry_lookup("Acme"))
    assert out["owner"] == ""
    client_cls.assert_not_called(), "must not even spend a request"


def test_suffix_only_padding_does_not_satisfy_the_two_token_rule():
    # "Acme LLC" normalizes to "ACME" — the suffix is stripped, so it is still
    # a one-token name and must be refused.
    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls:
        out = asyncio.run(owner_finder._wa_registry_lookup("Acme LLC"))
    assert out["owner"] == ""
    client_cls.assert_not_called()
