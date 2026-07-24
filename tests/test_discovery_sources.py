"""Discovery-source tests for app/skills/lead_gen_v3.py.

Two defects these lock down, both of which made the hunt look quota-starved
when it was actually starving itself:

1. `_source_serpapi_maps` sliced `[:count]` BEFORE filtering for a website, so
   it discarded website-bearing businesses already paid for (a SerpAPI page is
   billed whether or not it is read) and then reported a shortfall it had
   manufactured.
2. That manufactured shortfall triggered the DDG / Maps-scrape fallbacks, whose
   leads are a different KIND of result rather than a worse one: bare URL, no
   business name, no phone, no address. They can never be dialled and never
   reach the Secretary-of-State registry, so they cannot become customers.
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.skills import lead_gen_v3


class _Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


def _biz(i, website=True):
    b = {"title": f"Builder {i}", "phone": f"(408) 555-{1000 + i}",
         "address": f"{i} Main St, San Jose, CA 95124"}
    if website:
        b["website"] = f"https://builder{i}.com"
    return b


def _page(n, start=0, size=20):
    return {"local_results": [_biz(start + i) for i in range(n)]}


@pytest.fixture(autouse=True)
def _serp_key(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "test-key")
    # Ration always allows, so these tests measure logic not quota.
    with patch("app.skills.owner_finder._ration_check_and_increment",
               new=AsyncMock(return_value=True)):
        yield


def _run_maps(pages, count, max_pages=3):
    """Drive _source_serpapi_maps against a scripted sequence of pages."""
    calls = []

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def get(self, url, params=None):
            calls.append(params.get("start"))
            idx = len(calls) - 1
            return _Resp(pages[idx] if idx < len(pages) else {"local_results": []})

    with patch("httpx.AsyncClient", return_value=_Client()):
        out = asyncio.run(lead_gen_v3._source_serpapi_maps(
            "kitchen remodelers San Jose", count, max_pages=max_pages))
    return out, calls


# ─── The truncation defect ───────────────────────────────────────

def test_website_filter_runs_before_truncation():
    """THE REGRESSION. A page of 20 where only the last 5 have websites must
    still yield 5 — the old `[:count]` ran first and returned 0."""
    results = [_biz(i, website=False) for i in range(15)] + [_biz(100 + i) for i in range(5)]
    out, _ = _run_maps([{"local_results": results}], count=5, max_pages=1)
    assert len(out) == 5
    assert all(l["url"] for l in out)


def test_does_not_discard_results_already_paid_for():
    # 20 usable businesses on one page, caller wants 12 -> exactly 12, one call.
    out, calls = _run_maps([_page(20)], count=12, max_pages=3)
    assert len(out) == 12
    assert len(calls) == 1, "must not spend a second page when the first sufficed"


# ─── Pagination ──────────────────────────────────────────────────

def test_paginates_when_first_page_is_short():
    out, calls = _run_maps([_page(20), _page(20, start=20)], count=30, max_pages=3)
    assert len(out) == 30
    assert calls == [0, 20], "second page must be requested with start=20"


def test_stops_paginating_on_a_partial_page():
    # 8 < page size means the listing is exhausted; a further page is wasted spend.
    out, calls = _run_maps([{"local_results": [_biz(i) for i in range(8)]}],
                           count=50, max_pages=3)
    assert len(out) == 8
    assert calls == [0]


def test_respects_max_pages_ceiling():
    pages = [_page(20, start=i * 20) for i in range(5)]
    out, calls = _run_maps(pages, count=200, max_pages=2)
    assert len(calls) == 2, "a single hunt must not drain the shared monthly quota"
    assert len(out) == 40


def test_deduplicates_across_pages():
    dup = {"local_results": [_biz(1), _biz(1), _biz(2)]}
    out, _ = _run_maps([dup], count=10, max_pages=1)
    assert len({l["url"] for l in out}) == len(out) == 2


def test_quota_exhaustion_returns_what_it_already_has():
    """Ration denies the SECOND page — the first page's leads must survive."""
    calls = []

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            calls.append(params.get("start"))
            return _Resp(_page(20))

    allow = AsyncMock(side_effect=[True, False])
    with patch("httpx.AsyncClient", return_value=_Client()), \
         patch("app.skills.owner_finder._ration_check_and_increment", new=allow):
        out = asyncio.run(lead_gen_v3._source_serpapi_maps("q", 40, max_pages=3))
    assert len(out) == 20
    assert len(calls) == 1


def test_no_api_key_is_a_clean_skip(monkeypatch):
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    assert asyncio.run(lead_gen_v3._source_serpapi_maps("q", 10)) == []


# ─── Fallbacks are last-resort, not top-up ───────────────────────

def _run_find(serp_leads):
    async def _fake_enrich(url, business_name="", state="", score=0.0):
        return {"owner_name": "", "owner_title": "", "email": "", "phone": "",
                "owner_source": "", "email_source": "", "email_status": "",
                "phone_source": "", "phone_verified": False, "ad_signals": ""}

    ddg = AsyncMock(return_value=[])
    gmaps = AsyncMock(return_value=[])
    with patch.object(lead_gen_v3, "_source_serpapi_maps",
                      new=AsyncMock(return_value=serp_leads)), \
         patch.object(lead_gen_v3, "_source_duckduckgo", new=ddg), \
         patch.object(lead_gen_v3, "_source_google_maps", new=gmaps), \
         patch.object(lead_gen_v3, "enrich_lead_4step", new=_fake_enrich):
        asyncio.run(lead_gen_v3.find_leads_v3(count=10, query="remodelers San Jose"))
    return ddg, gmaps


def test_partial_serpapi_run_is_not_topped_up_with_url_only_leads():
    """3 real leads when 10 were asked for is still 3 REAL leads. Padding them
    with nameless, phoneless URLs adds dashboard rows and zero conversations."""
    serp = [{"business": f"Builder {i}", "url": f"https://b{i}.com",
             "phone": "+14085551000", "address": "1 Main St, San Jose, CA 95124",
             "source": "serpapi_maps"} for i in range(3)]
    ddg, gmaps = _run_find(serp)
    ddg.assert_not_awaited()
    gmaps.assert_not_awaited()


def test_fallbacks_still_fire_when_serpapi_yields_nothing():
    # No key / quota spent — a degraded source beats no pipeline at all.
    ddg, gmaps = _run_find([])
    ddg.assert_awaited()
    gmaps.assert_awaited()


def test_ddg_lead_shape_cannot_reach_outreach_ready():
    """Documents WHY the demotion matters, so nobody re-promotes the source:
    a DDG lead has no phone for Retell and no address, so the state stays empty
    and owner_finder can never route to the CA/WA/OR registry."""
    ddg_lead = {"business": "", "url": "https://otbaybuilders.com", "phone": ""}
    assert ddg_lead["phone"] == ""
    assert lead_gen_v3._state_from_address(ddg_lead.get("address", "")) == ""
    # Name degrades to the bare domain — what the call script would greet.
    assert (ddg_lead["business"]
            or lead_gen_v3.extract_domain(ddg_lead["url"])) == "otbaybuilders.com"
