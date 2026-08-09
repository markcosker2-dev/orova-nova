"""WA L&I discovery must select contractors who can AFFORD the retainer.

## What was wrong (measured on the live registry, 2026-08-09)

The source ordered `licenseeffectivedate DESC` — newest licences first — on the
reasoning that "a recently-licensed contractor is more likely to still be
building a client base." That optimises for who NEEDS leads, which is the
opposite of ADR-0012's qualifying test:

    Does ONE extra closed deal per month more than cover the ~$6.5-7.5K all-in
    monthly cost?

and it collides head-on with a kill signal in business_context.json:

    "No payroll (solo operator) - no urgency"

The three leads in production that could be verified against the registry were
licensed **3-4 days earlier**, every one single-principal and carrying the $1M
minimum insurance. The pipeline was systematically sourcing the least
qualified segment available.

Supply was never the reason: 11,105 active GENERAL/RESIDENTIAL contractors in
the target cities were licensed 3+ years ago, against an outreach rate of 5-10
per day.
"""
import re
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


def _capture_params(monkeypatch, **env):
    """Run the real discovery and capture the Socrata params it builds.

    Deliberately exercises the true code path rather than asserting on a
    hand-built string: the licence-age floor needs `datetime`/`timedelta`, and
    a missing import is a NameError that only appears at runtime. A test that
    rebuilt the query itself would have sailed straight past that.
    """
    import app.skills.lead_gen_v3 as lg
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return []

    class _Client:
        async def get(self, url, params=None, headers=None):
            seen["url"] = url
            seen["params"] = params
            return _Resp()

    with patch.object(lg, "_get_http_client", AsyncMock(return_value=_Client())):
        import asyncio
        asyncio.run(lg._source_wa_lni_licences(count=5))
    return seen


def test_the_query_excludes_newly_licensed_contractors(monkeypatch):
    where = _capture_params(monkeypatch)["params"]["$where"]
    m = re.search(r"licenseeffectivedate < '(\d{4}-\d{2}-\d{2})'", where)
    assert m, f"no licence-age floor in the query: {where}"

    cutoff = datetime.strptime(m.group(1), "%Y-%m-%d")
    age_days = (datetime.now() - cutoff).days
    assert age_days > 365 * 2.5, (
        f"floor is only {age_days} days back — a contractor licensed this "
        f"recently cannot cover a $6.5-7.5K/mo retainer")


def test_oldest_licences_come_first(monkeypatch):
    """Longevity is the free proxy for 'has survived, has a book of business'."""
    order = _capture_params(monkeypatch)["params"]["$order"]
    assert "licenseeffectivedate" in order
    assert "ASC" in order.upper(), f"newest-first sources the least qualified segment: {order!r}"
    assert "DESC" not in order.upper()


def test_institutional_contractors_are_excluded_too(monkeypatch):
    """The over-correction this caught, live.

    A floor plus oldest-first returned W G CLARK (1963), ABSHER (1966) and
    TURNER CONSTRUCTION COMPANY (1977, $5M cover) — national commercial GCs
    with marketing departments, as far outside the ICP as the day-old solo
    operators were. The selection needs an upper bound as well as a lower one.
    """
    where = _capture_params(monkeypatch)["params"]["$where"]
    m = re.search(r"licenseeffectivedate > '(\d{4}-\d{2}-\d{2})'", where)
    assert m, f"no upper bound on licence age — 1960s institutions get through: {where}"
    ceiling = datetime.strptime(m.group(1), "%Y-%m-%d")
    years = (datetime.now() - ceiling).days / 365.25
    assert 5 < years < 60, f"implausible ceiling of {years:.0f} years"


def test_self_declared_sole_proprietors_are_excluded(monkeypatch):
    """business_context.json: "No payroll (solo operator) - no urgency" is a
    kill signal. The registry states it outright for 9,325 businesses, and
    reading it costs no extra API call."""
    where = _capture_params(monkeypatch)["params"]["$where"]
    assert "businesstypecodedesc != 'Individual'" in where


def test_the_band_is_tunable_from_env(monkeypatch):
    where = _capture_params(monkeypatch, WA_LNI_MAX_LICENCE_YEARS="12")["params"]["$where"]
    ceiling = datetime.strptime(
        re.search(r"licenseeffectivedate > '(\d{4}-\d{2}-\d{2})'", where).group(1), "%Y-%m-%d")
    years = (datetime.now() - ceiling).days / 365.25
    assert 11 < years < 13, f"env override ignored — ceiling is {years:.1f} years"


def test_the_floor_is_tunable_without_a_code_change(monkeypatch):
    """Runtime configuration lives in env (CLAUDE.md single-source-of-truth)."""
    where = _capture_params(monkeypatch, WA_LNI_MIN_LICENCE_YEARS="10")["params"]["$where"]
    cutoff = datetime.strptime(
        re.search(r"licenseeffectivedate < '(\d{4}-\d{2}-\d{2})'", where).group(1), "%Y-%m-%d")
    age_days = (datetime.now() - cutoff).days
    assert age_days > 365 * 9, f"env override ignored — floor only {age_days} days back"


def test_the_existing_icp_filters_are_untouched(monkeypatch):
    """Adding a qualifier must not quietly drop the gates already in place."""
    where = _capture_params(monkeypatch)["params"]["$where"]
    for clause in ("contractorlicensestatus='ACTIVE'",
                   "CONSTRUCTION CONTRACTOR",
                   "primaryprincipalname IS NOT NULL",
                   "phonenumber IS NOT NULL"):
        assert clause in where, f"lost an existing filter: {clause}"
