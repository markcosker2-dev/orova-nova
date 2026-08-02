"""Yelp Fusion as a West-Coast discovery source (2026-07-31).

ADR-0014 listed Yelp as a dead end and then sequenced discovery by which state
has a free registry API — putting California, the #1 ICP geography, last for a
purely technical reason. Yelp works identically in every metro, so it removes
that constraint.

Fixtures below use the REAL Yelp Fusion v3 response shape, taken from live
queries against Seattle / LA / San Diego / Portland on 2026-07-31 — including
the genuine edge cases those returned (a 2.9-star builder, a landscaper tagged
as a contractor, countertop installers).
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

from app.skills.lead_gen_v3 import (
    _source_yelp_businesses,
    _yelp_row_to_lead,
    icp_business_name_reason,
    wa_lni_icp_reason,
)


def _biz(**kw):
    """A Yelp business in the real v3 shape, in-ICP by default."""
    base = {
        "name": "Cherry Design + Build",
        "phone": "+12065506026",
        "rating": 4.7,
        "review_count": 32,
        "is_closed": False,
        "categories": [{"alias": "contractors", "title": "General Contractors"}],
        "location": {"address1": "4202 S Spencer St", "city": "Seattle",
                     "state": "WA", "zip_code": "98118"},
    }
    base.update(kw)
    return base


def _fresh():
    return {"category": 0, "name": 0, "rating": 0, "reviews": 0, "phone": 0}


# ── Row-level ICP gates ──────────────────────────────────────────────────────

def test_in_icp_business_becomes_a_lead():
    lead = _yelp_row_to_lead(_biz(), _fresh(), set())
    assert lead is not None
    assert lead["business"] == "Cherry Design + Build"
    assert lead["phone"] == "+12065506026"
    assert lead["state"] == "WA"
    assert lead["source"] == "yelp"
    assert "4.7" in lead["notes"] and "32 reviews" in lead["notes"]


def test_never_invents_email_or_website():
    """Yelp supplies neither. Fabricating either is the unforgivable bug."""
    lead = _yelp_row_to_lead(_biz(), _fresh(), set())
    assert lead["email"] == ""
    assert lead["website"] == ""
    assert lead["url"] == ""
    assert lead["owner_name"] == ""      # resolved later, never guessed


def test_landscaper_rejected_by_category():
    """Real LA result: 'The Green Scene Landscaping and Pools'."""
    row = _biz(name="The Green Scene Landscaping and Pools", review_count=141,
               rating=4.8, categories=[{"alias": "landscaping", "title": "Landscaping"}])
    assert _yelp_row_to_lead(row, _fresh(), set()) is None


def test_secondary_off_icp_category_rejects():
    """A business tagged BOTH contractors and handyman is a handyman.
    Yelp returns categories unordered, so every alias must be checked."""
    row = _biz(categories=[{"alias": "contractors", "title": "General Contractors"},
                           {"alias": "handyman", "title": "Handyman"}])
    assert _yelp_row_to_lead(row, _fresh(), set()) is None


def test_countertop_installer_rejected():
    """Real Portland result: 'Quality Granite & Cabinets'."""
    row = _biz(name="Quality Granite & Cabinets", review_count=82, rating=4.5,
               categories=[{"alias": "countertopinstall", "title": "Countertop Installation"}])
    assert _yelp_row_to_lead(row, _fresh(), set()) is None


def test_no_in_icp_category_rejected():
    row = _biz(categories=[{"alias": "realestateagents", "title": "Real Estate Agents"}])
    assert _yelp_row_to_lead(row, _fresh(), set()) is None


def test_low_rating_rejected():
    """Real Portland result: Neil Kelly, 91 reviews but 2.9 stars. A builder with
    a delivery problem doesn't need leads — ads would amplify the reviews."""
    row = _biz(name="Neil Kelly", rating=2.9, review_count=91)
    skipped = _fresh()
    assert _yelp_row_to_lead(row, skipped, set()) is None
    assert skipped["rating"] == 1


def test_low_review_count_rejected():
    """Review count is the business-SIZE proxy ADR-0014 called unsolved."""
    row = _biz(review_count=3)
    skipped = _fresh()
    assert _yelp_row_to_lead(row, skipped, set()) is None
    assert skipped["reviews"] == 1


def test_closed_business_rejected():
    assert _yelp_row_to_lead(_biz(is_closed=True), _fresh(), set()) is None


def test_duplicate_phone_rejected():
    seen = set()
    assert _yelp_row_to_lead(_biz(), _fresh(), seen) is not None
    assert _yelp_row_to_lead(_biz(name="Other Co"), _fresh(), seen) is None


def test_missing_phone_rejected():
    assert _yelp_row_to_lead(_biz(phone="", display_phone=""), _fresh(), set()) is None


def test_malformed_rating_does_not_crash():
    """Yelp occasionally omits or nulls fields; a bad row must skip, not raise."""
    assert _yelp_row_to_lead(_biz(rating=None, review_count="x"), _fresh(), set()) is None
    assert _yelp_row_to_lead({}, _fresh(), set()) is None
    assert _yelp_row_to_lead(None, _fresh(), set()) is None


def test_unknown_state_is_emptied_not_stored_wrong():
    row = _biz(location={"address1": "1 X St", "city": "Y", "state": "ZZ", "zip_code": "1"})
    assert _yelp_row_to_lead(row, _fresh(), set())["state"] == ""


def test_name_filter_alias_still_works():
    """wa_lni_icp_reason was renamed; the alias keeps existing callers working."""
    assert wa_lni_icp_reason is icp_business_name_reason
    assert icp_business_name_reason("Bob's Handyman Service")


# ── Source-level behaviour ───────────────────────────────────────────────────

def _client(pages, status=200):
    """pages: list of business-lists, returned in order across paginated calls."""
    calls = {"n": 0}

    async def _get(url, **kw):
        i = min(calls["n"], len(pages) - 1)
        calls["n"] += 1
        return type("R", (), {"status_code": status,
                              "json": lambda self, _p=pages[i]: {"businesses": _p}})()
    c = AsyncMock()
    c.get = AsyncMock(side_effect=_get)
    return c


@pytest.mark.asyncio
async def test_no_api_key_skips_cleanly():
    """Composio's Yelp credential lives in the operator's MCP session, not in
    Nova's runtime — so production genuinely has no key until one is set."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("YELP_API_KEY", None)
        assert await _source_yelp_businesses("remodeling", 10, "Seattle, WA") == []


@pytest.mark.asyncio
async def test_kill_switch():
    with patch.dict(os.environ, {"YELP_API_KEY": "k", "YELP_DISCOVERY_ENABLED": "0"}):
        assert await _source_yelp_businesses("remodeling", 10, "Seattle, WA") == []


@pytest.mark.asyncio
async def test_happy_path_filters_and_returns():
    pages = [[_biz(), _biz(name="Landscape Co", phone="+12065550001",
                           categories=[{"alias": "landscaping", "title": "L"}])]]
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client(pages))), \
         patch("app.skills.lead_gen_v3._yelp_resolve_owners", AsyncMock()):
        leads = await _source_yelp_businesses("remodeling", 10, "Seattle, WA")
    assert len(leads) == 1
    assert leads[0]["business"] == "Cherry Design + Build"


@pytest.mark.asyncio
async def test_respects_count_and_stops_paginating():
    page = [_biz(name=f"Builder {i} Construction", phone=f"+1206555{i:04d}")
            for i in range(50)]
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client([page]))), \
         patch("app.skills.lead_gen_v3._yelp_resolve_owners", AsyncMock()):
        leads = await _source_yelp_businesses("remodeling", 5, "Seattle, WA")
    assert len(leads) == 5


@pytest.mark.asyncio
async def test_rate_limit_stops_without_raising():
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client([[]], status=429))):
        assert await _source_yelp_businesses("remodeling", 10, "Seattle, WA") == []


@pytest.mark.asyncio
async def test_http_error_returns_empty():
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client([[]], status=500))):
        assert await _source_yelp_businesses("remodeling", 10, "Seattle, WA") == []


@pytest.mark.asyncio
async def test_network_failure_never_raises():
    """Discovery failing must never take down the hunting lane."""
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(side_effect=RuntimeError("network down"))):
        assert await _source_yelp_businesses("remodeling", 10, "Seattle, WA") == []


@pytest.mark.asyncio
async def test_empty_location_returns_empty():
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}):
        assert await _source_yelp_businesses("remodeling", 10, "") == []


@pytest.mark.asyncio
async def test_sends_bearer_auth_and_metro():
    client = _client([[]])
    with patch.dict(os.environ, {"YELP_API_KEY": "secret-key"}), \
         patch("app.skills.lead_gen_v3._get_http_client", AsyncMock(return_value=client)):
        await _source_yelp_businesses("remodeling", 10, "Los Angeles, CA")
    kw = client.get.call_args.kwargs
    assert kw["headers"]["Authorization"] == "Bearer secret-key"
    assert kw["params"]["location"] == "Los Angeles, CA"
    assert kw["params"]["limit"] == 50


# ── Owner resolution — what makes a Yelp lead contactable ───────────────────

@pytest.mark.asyncio
async def test_owner_resolved_from_state_registry():
    """Yelp has no decision-maker and outreach_ready requires a name on every
    channel, so without this a Yelp lead is discovered but not contactable."""
    hit = {"owner": "Marc Schock", "title": "Licence Principal",
           "source": "wa_lni", "confidence": 0.9}
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client([[_biz()]]))), \
         patch("app.skills.owner_finder._registry_lookup", AsyncMock(return_value=hit)):
        leads = await _source_yelp_businesses("remodeling", 5, "Seattle, WA")
    assert leads[0]["owner_name"] == "Marc Schock"
    assert leads[0]["owner_source"] == "wa_lni"
    assert leads[0]["owner_confidence"] == 90


@pytest.mark.asyncio
async def test_owner_lookup_failure_is_non_fatal():
    """A missing name is far better than a wrong one (ADR-0008). The lead is
    still returned; it simply is not outreach-ready yet."""
    with patch.dict(os.environ, {"YELP_API_KEY": "k"}), \
         patch("app.skills.lead_gen_v3._get_http_client",
               AsyncMock(return_value=_client([[_biz()]]))), \
         patch("app.skills.owner_finder._registry_lookup",
               AsyncMock(side_effect=RuntimeError("registry down"))):
        leads = await _source_yelp_businesses("remodeling", 5, "Seattle, WA")
    assert len(leads) == 1
    assert leads[0]["owner_name"] == ""


# ── Metro inference (Yelp needs "City, ST"; the hunt query is free text) ─────

@pytest.mark.parametrize("query,expected", [
    ("luxury home remodeling california", "Los Angeles, CA"),   # ADR-0012 #1 metro
    ("custom home builder los angeles", "Los Angeles, CA"),
    ("high end kitchen remodeler san diego", "San Diego, CA"),
    ("remodeling contractors seattle", "Seattle, WA"),
    ("design build portland", "Portland, OR"),
    ("whole home remodel washington", "Seattle, WA"),
    ("custom home builder oregon", "Portland, OR"),
])
def test_metro_inference(query, expected):
    from app.skills.lead_gen_v3 import _infer_yelp_location
    assert _infer_yelp_location(query) == expected


def test_metro_inference_returns_empty_when_unplaceable():
    """Skipping beats guessing — a wrong metro discovers leads in the wrong state."""
    from app.skills.lead_gen_v3 import _infer_yelp_location
    assert _infer_yelp_location("custom home builder texas") == ""
    assert _infer_yelp_location("") == ""
    assert _infer_yelp_location(None) == ""


def test_specific_metro_beats_bare_state():
    from app.skills.lead_gen_v3 import _infer_yelp_location
    assert _infer_yelp_location("remodeler san diego california") == "San Diego, CA"
