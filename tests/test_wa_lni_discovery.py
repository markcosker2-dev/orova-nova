"""WA L&I licence registry as a discovery source (ADR-0014 seam 1).

SerpAPI is exhausted (250/250, 0 left) and is the only working discovery
source, so automated discovery is dead. This dataset is free, keyless and
unlimited, and it supplies the decision maker directly.

The ICP name filter is the part that needs proving. ADR-0014 assumed specialty
GENERAL|RESIDENTIAL isolated remodelers; reading real rows on 2026-07-30 showed
that bucket is full of landscapers, window cleaners, drywall and handymen. The
filter below is what actually separates them, so it is tested against real
naming patterns taken verbatim from the live dataset.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.skills.lead_gen_v3 import (
    _source_wa_lni_licences,
    wa_lni_icp_reason,
)

# Verbatim from the live dataset — these are real WA licence holders that the
# filter must KEEP (ADR-0012 custom home builders / high-end remodelers).
REAL_IN_ICP = [
    "100PLUS REMODELING LLC",
    "168 KITCHEN & BATH CORP",
    "206 HOME REMODELING LLC",
    "2S DESIGN BUILD LLC",
    "3:4:5 BUILDERS LLC",
    "360 HOUSE REMODELING LLC",
    "3A REMODELING",
    "COZY HOME REMODELING LLC",
    "2 BOXERS CARPENTRY LLC",
    "2M RESIDENTIAL LLC",
    "12 BROTHERS CONSTRUCTION LLC",
    "2K CONSTRUCTION",
    # Trade word present but a STRONG remodeling marker wins — a roofer who
    # also remodels is in-ICP, and a flat denylist wrongly dropped these.
    "ACTION ROOFING & REMODELING",
    "ARK ROOFING & RENOVATIONS LLC",
    "A + REMODEL&FLOORING",
]

# Verbatim from the live dataset — real rows the filter must DROP.
REAL_OFF_ICP = [
    "CORNERSTONE LANDSCAPING LLC",
    "COUTURE LANDSCAPING LLC",
    "5 STAR WINDOW CLEANING LLC",
    "CORNERSTONE ROOF CARE CO",
    "123 Electric Service Inc",
    "1ST TIER HVAC LLC",
    "1ST CLASS GLASS INC",
    "206PAINTERS LLC",
    "12 DECKS & FENCES LLC",
    "12TH HANDYMAN",
    "CR DRYWALL CORPORATION",
    "CRAFT TILE LLC",
    "ANDY TILE CONSTRUCTION LLC",
    "AFS CONSTRUCTION + HANDYMAN",
    "A & A MASONRY & CONSTRUCTION",
    "A & D LANDSCAPE SPRINKLERS",
    # Single-project / address-shell LLCs, not operating remodelers.
    "11210 LLC",
    "2419 MERCER LLC",
    "211-WLD KILBIRNIE LLC",
    "11737 40TH AVE NE LLC",
]


@pytest.mark.parametrize("name", REAL_IN_ICP)
def test_real_in_icp_names_pass(name):
    assert wa_lni_icp_reason(name) == "", f"dropped in-ICP remodeler {name!r}"


@pytest.mark.parametrize("name", REAL_OFF_ICP)
def test_real_off_icp_names_are_dropped(name):
    assert wa_lni_icp_reason(name), f"kept off-ICP row {name!r}"


def test_filter_separates_the_two_populations():
    """Owner rule: a signal firing near 100% or 0% across real inputs is noise.
    This one must split the corpus cleanly, not pass or reject everything."""
    kept_good = sum(1 for n in REAL_IN_ICP if not wa_lni_icp_reason(n))
    kept_bad = sum(1 for n in REAL_OFF_ICP if not wa_lni_icp_reason(n))
    assert kept_good == len(REAL_IN_ICP)
    assert kept_bad == 0


def test_empty_name_is_rejected():
    assert wa_lni_icp_reason("")
    assert wa_lni_icp_reason(None)


# ── The source function ──────────────────────────────────────────────────────

_ROWS = [
    {   # in-ICP, complete → must become a lead
        "businessname": "360 HOUSE REMODELING LLC",
        "primaryprincipalname": "PETERSON, CHAD DEVIN",
        "phonenumber": "2065550101", "address1": "123 PIKE ST",
        "city": "SEATTLE", "state": "WA", "zip": "98101",
        "contractorlicensenumber": "REMOD123NN",
        "licenseeffectivedate": "2025-08-15T00:00:00.000",
        "businesstypecodedesc": "Limited Liability Company",
    },
    {   # off-ICP trade → filtered out
        "businessname": "CORNERSTONE LANDSCAPING LLC",
        "primaryprincipalname": "SMITH, JOHN A",
        "phonenumber": "2065550001", "address1": "1 MAIN ST",
        "city": "KENT", "state": "WA", "zip": "98032",
    },
    {   # duplicate phone of row 1 → shared line, dropped
        "businessname": "168 REMODELING LLC",
        "primaryprincipalname": "LEE, MARIA",
        "phonenumber": "2065550101", "address1": "5 OAK AVE",
        "city": "KENT", "state": "WA", "zip": "98032",
    },
    {   # unparseable principal → never stored (no fabricated owner)
        "businessname": "2S DESIGN BUILD LLC",
        "primaryprincipalname": "LLC",
        "phonenumber": "2065550002", "address1": "9 ELM ST",
        "city": "BELLEVUE", "state": "WA", "zip": "98004",
    },
]


def _mock_client(rows, status=200):
    resp = type("R", (), {"status_code": status, "json": lambda self: rows})()
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_source_emits_only_the_clean_in_icp_row():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_wa_lni_licences(count=10)

    assert len(leads) == 1, [l["business"] for l in leads]
    lead = leads[0]
    assert lead["business"] == "360 HOUSE REMODELING LLC"
    assert lead["owner_name"] == "Chad Peterson"      # "LAST, FIRST MIDDLE" parsed
    assert lead["phone"] == "+12065550101"            # bare 10-digit -> E.164
    assert lead["state"] == "WA"
    assert lead["source"] == "wa_lni_licences"
    assert lead["owner_confidence"] == 90
    assert lead["phone_verified"] is True
    assert "SEATTLE" in lead["address"]
    assert "REMOD123NN" in lead["notes"]


@pytest.mark.asyncio
async def test_source_never_invents_email_or_website():
    """Licence data has neither. Fabricating either is the one unforgivable bug."""
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(_ROWS))):
        leads = await _source_wa_lni_licences(count=10)
    assert leads[0]["email"] == ""
    assert leads[0]["website"] == ""
    assert leads[0]["url"] == ""


@pytest.mark.asyncio
async def test_source_respects_count():
    rows = [dict(_ROWS[0], phonenumber=f"20655500{i:02d}",
                 businessname=f"{i} HOME REMODELING LLC") for i in range(20)]
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client(rows))):
        leads = await _source_wa_lni_licences(count=3)
    assert len(leads) == 3


@pytest.mark.asyncio
async def test_source_is_disabled_by_kill_switch():
    with patch.dict(os.environ, {"WA_LNI_DISCOVERY_ENABLED": "0"}):
        assert await _source_wa_lni_licences(count=5) == []


@pytest.mark.asyncio
async def test_http_error_returns_empty_not_an_exception():
    """Discovery failing must never take down the hunting lane."""
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_mock_client([], status=503))):
        assert await _source_wa_lni_licences(count=5) == []


@pytest.mark.asyncio
async def test_fetch_failure_returns_empty():
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(side_effect=RuntimeError("network down"))):
        assert await _source_wa_lni_licences(count=5) == []


@pytest.mark.asyncio
async def test_query_filters_to_active_construction_contractors():
    """The Socrata $where must carry every ICP filter — a missing clause here
    silently widens discovery to all 75K licences."""
    client = _mock_client([])
    with patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=client)):
        await _source_wa_lni_licences(count=5)
    where = client.get.call_args.kwargs["params"]["$where"]
    assert "contractorlicensestatus='ACTIVE'" in where
    assert "CONSTRUCTION CONTRACTOR" in where
    assert "'GENERAL','RESIDENTIAL'" in where
    assert "SEATTLE" in where
    assert "primaryprincipalname IS NOT NULL" in where
    assert "phonenumber IS NOT NULL" in where
