"""OR CCB licence registry as a discovery source (ADR-0014 seam 3).

ADR-0014 measured OR CCB as free, keyless, ~100% phone fill and 95.9% owner
fill — and then not one line of code called it for eight days. This wires it.

Every fixture below is taken VERBATIM from the live dataset on 2026-08-05
(https://data.oregon.gov/resource/g77e-6bhs.json, 55,931 rows), because the
three things that can go wrong here are all data-shape problems that a
synthetic fixture would hide:

  1. The dataset is "contractors who can legally work in Oregon", not "Oregon
     contractors" — 14.5% of rows are in another state.
  2. `license_type='RGC'` is a LICENCE CLASS, not a trade category, so it does
     not isolate remodelers the way a Yelp category does.
  3. 116 rows carry a placeholder instead of a person's name.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.skills.lead_gen_v3 import (
    LICENCE_REGISTRIES,
    _source_or_ccb_licences,
    licence_registry_for,
)
from app.skills.owner_finder import _person_from_principal, _is_plausible_name


# ── registration ────────────────────────────────────────────────────────────

def test_or_is_registered_as_a_jurisdiction():
    assert licence_registry_for("OR") is _source_or_ccb_licences
    assert LICENCE_REGISTRIES["OR"] is _source_or_ccb_licences


# ── the RMI name parser ─────────────────────────────────────────────────────
# OR CCB stores the RMI given-name-first with NO comma (measured: 0% of 6,000
# sampled rows contain one), so every Oregon row takes _person_from_principal's
# no-comma branch — which did not strip generational suffixes.

@pytest.mark.parametrize("raw,expected", [
    # Verbatim live rows that the old parser mangled. 3.18% of rmi_name values
    # (191/6000 measured) end in a suffix; each produced a name that passes
    # _is_plausible_name and would reach a Retell call script.
    ("DONALD JOSEPH ZEISE JR", "Donald Zeise"),
    ("THOMAS VICTOR KELLER JR", "Thomas Keller"),
    ("JAMES EDWARD JACOBSON SR", "James Jacobson"),
    ("KEVIN THOMAS WYNNE II", "Kevin Wynne"),
    ("CHARLES JACKSON OFFICER IV", "Charles Officer"),
    ("JOSE LUIS CONTRERAS JR", "Jose Contreras"),
    ("CURTIS MICHAEL CLE BERNIER II", "Curtis Bernier"),
    # Ordinary rows must be unaffected.
    ("EDWARD CARL BARRINGTON", "Edward Barrington"),
    ("ALEX JOHN MASSAR", "Alex Massar"),
    ("TIMOTHY MICHAEL HOFFMAN", "Timothy Hoffman"),
    # A LEADING 'MD' is a given name here (verbatim live row), not a doctorate.
    # Only TRAILING suffixes are stripped, so this must survive intact.
    ("MD SHAHRIAR SHAMIM", "Md Shamim"),
    # Two-token names must never be reduced below two tokens.
    ("KEVIN ACKERLUND", "Kevin Ackerlund"),
])
def test_rmi_name_parsing(raw, expected):
    assert _person_from_principal(raw) == expected


def test_suffix_never_becomes_the_surname():
    """The specific regression: 'Donald Jr' passed _is_plausible_name and was
    therefore a callable, fabricated-looking owner name."""
    for raw in ("DONALD JOSEPH ZEISE JR", "KEVIN THOMAS WYNNE II",
                "CHARLES JACKSON OFFICER IV"):
        out = _person_from_principal(raw)
        surname = out.split()[-1].upper()
        assert surname not in {"JR", "SR", "II", "III", "IV", "V"}, out


def test_wa_surname_first_format_still_parses():
    """The comma branch is WA L&I's and must not regress."""
    assert _person_from_principal("POWER, GREGORY MARK JR") == "Gregory Power"
    assert _person_from_principal("PETERSON, CHAD DEVIN") == "Chad Peterson"


# ── the source function ─────────────────────────────────────────────────────

_ROWS = [
    {   # in-ICP, complete → must become a lead (verbatim live row)
        "full_name": "CEDAR CREEK CONSTRUCTION LLC",
        "rmi_name": "TIMOTHY MICHAEL HOFFMAN",
        "phone_number": "5032013017", "address": "15065 S MITCHELL LANE",
        "city": "OREGON CITY", "state": "OR", "zip_code": "97045",
        "county_name": "Clackamas", "license_number": "234061",
        "orig_regis_date": "12/31/2020",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
    {   # off-ICP trade holding a Residential General Contractor licence —
        # the exact case that proves the endorsement is not a trade category.
        "full_name": "SHAMBURG HEATING LLC",
        "rmi_name": "SCOTT ARRON SHAMBURG",
        "phone_number": "5036925563", "address": "1 MAIN ST",
        "city": "BEAVERCREEK", "state": "OR", "zip_code": "97004",
        "county_name": "Clackamas", "license_number": "111111",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
    {   # placeholder RMI (verbatim) → must never become an owner name
        "full_name": "RARE & SNUG CONSTRUCTION LLC",
        "rmi_name": "RD - NO RMI RQRD",
        "phone_number": "5035550001", "address": "2 OAK AVE",
        "city": "PORTLAND", "state": "OR", "zip_code": "97211",
        "county_name": "Multnomah", "license_number": "222222",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
    {   # another placeholder spelling (verbatim)
        "full_name": "635 MARSHALL CONSTRUCTION LLC",
        "rmi_name": "RMI NOT RQ'D",
        "phone_number": "5035550002", "address": "3 ELM ST",
        "city": "PORTLAND", "state": "OR", "zip_code": "97212",
        "county_name": "Multnomah", "license_number": "333333",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
    {   # duplicate phone of row 1 → shared line, dropped
        "full_name": "SECOND CHANCE REMODELING LLC",
        "rmi_name": "MARIA ELENA LEE",
        "phone_number": "5032013017", "address": "5 PINE ST",
        "city": "PORTLAND", "state": "OR", "zip_code": "97213",
        "county_name": "Multnomah", "license_number": "444444",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
    {   # suffix row → must be parsed, not mangled
        "full_name": "ZEISE CUSTOM HOMES LLC",
        "rmi_name": "DONALD JOSEPH ZEISE JR",
        "phone_number": "5035550003", "address": "7 FIR LN",
        "city": "PORTLAND", "state": "OR", "zip_code": "97214",
        "county_name": "Multnomah", "license_number": "555555",
        "endorsement_text": "Residential General Contractor",
        "exempt_text": "Nonexempt",
    },
]


def _mock_client(rows, status=200):
    resp = type("R", (), {"status_code": status, "json": lambda self: rows})()
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_source_emits_only_clean_in_icp_rows():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_or_ccb_licences(count=10)

    names = [l["business"] for l in leads]
    assert names == ["CEDAR CREEK CONSTRUCTION LLC", "ZEISE CUSTOM HOMES LLC"], names

    lead = leads[0]
    assert lead["owner_name"] == "Timothy Hoffman"
    assert lead["owner_title"] == "Responsible Managing Individual"
    assert lead["owner_source"] == "or_ccb"
    assert lead["phone"] == "+15032013017"        # bare 10-digit → E.164
    assert lead["phone_source"] == "or_ccb"
    assert lead["phone_verified"] is True
    assert lead["state"] == "OR"
    assert lead["email"] == ""                    # licence data has none, ever
    assert lead["url"] == "" and lead["website"] == ""
    assert "234061" in lead["notes"]
    assert "Clackamas" in lead["notes"]


@pytest.mark.asyncio
async def test_placeholder_rmi_never_becomes_an_owner():
    """'RD - NO RMI RQRD' parses to 'Rd Rqrd', which passes _is_plausible_name.
    Without the guard, Retell asks for a person who does not exist."""
    # Confirm the trap is real before asserting the guard closes it.
    assert _is_plausible_name(_person_from_principal("RD - NO RMI RQRD"))

    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_or_ccb_licences(count=10)

    owners = [l["owner_name"] for l in leads]
    assert not any("Rqrd" in o or "Rmi" in o or "Rq" == o.split()[-1] for o in owners), owners
    assert "RARE & SNUG CONSTRUCTION LLC" not in [l["business"] for l in leads]


@pytest.mark.asyncio
async def test_suffix_row_yields_a_clean_owner_name():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_or_ccb_licences(count=10)
    zeise = [l for l in leads if l["business"] == "ZEISE CUSTOM HOMES LLC"][0]
    assert zeise["owner_name"] == "Donald Zeise"


@pytest.mark.asyncio
async def test_duplicate_phone_is_dropped():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_or_ccb_licences(count=10)
    phones = [l["phone"] for l in leads]
    assert len(phones) == len(set(phones))


@pytest.mark.asyncio
async def test_count_is_respected():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_or_ccb_licences(count=1)
    assert len(leads) == 1


@pytest.mark.asyncio
async def test_non_200_returns_empty_not_an_exception():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client([], status=503))):
        assert await _source_or_ccb_licences(count=5) == []


@pytest.mark.asyncio
async def test_fetch_failure_is_swallowed():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=client)):
        assert await _source_or_ccb_licences(count=5) == []


@pytest.mark.asyncio
async def test_env_kill_switch(monkeypatch):
    monkeypatch.setenv("OR_CCB_DISCOVERY_ENABLED", "0")
    assert await _source_or_ccb_licences(count=5) == []


# ── the query the source actually sends ─────────────────────────────────────

async def _captured_where(**kwargs):
    client = _mock_client([])
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=client)):
        await _source_or_ccb_licences(count=5, **kwargs)
    return client.get.call_args.kwargs["params"]["$where"]


@pytest.mark.asyncio
async def test_query_filters_out_of_state_licensees():
    """14.5% of rows (8,090/55,931) are licensed in Oregon but based elsewhere —
    4,582 in Washington alone. Without state='OR' an Oregon hunt returns
    Washington businesses."""
    assert "state='OR'" in await _captured_where()


@pytest.mark.asyncio
async def test_query_restricts_to_residential_general_contractors():
    where = await _captured_where()
    assert "license_type='RGC'" in where


@pytest.mark.asyncio
async def test_query_scopes_to_the_portland_metro_counties():
    where = await _captured_where()
    for county in ("Multnomah", "Washington", "Clackamas"):
        assert f"'{county}'" in where


@pytest.mark.asyncio
async def test_employee_filter_is_on_by_default_and_optional():
    """`exempt_text` is the publisher's own field for "required to carry
    Workmans Compensation Insurance", i.e. has employees. It is a SIZE proxy
    (ADR-0014 flagged the absence of one) — never an affordability proxy."""
    assert "exempt_text='Nonexempt'" in await _captured_where()
    assert "exempt_text" not in await _captured_where(require_employees=False)


@pytest.mark.asyncio
async def test_counties_are_configurable():
    where = await _captured_where(counties=("Lane",))
    assert "'Lane'" in where and "'Multnomah'" not in where
