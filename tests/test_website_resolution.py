"""Website resolution for licence-registry leads (ADR-0014 seam 2).

Registry leads carry no domain, and `enrich_lead_lite` returns immediately on a
lead with no `url` — so ad signals, email discovery and owner verification never
run on them at all. This resolves a domain so they reach that machinery.

The whole risk here is a FALSE ACCEPT. Guessing `<businessname>.com` and
checking the name matches was measured live on 2026-08-05 at 87% "resolved" and
**7% correct** — the rest were same-named businesses in other states
(`cedarcreekconstruction.com` is a Pennsylvania firm, area code 610). Attaching
one of those would feed a stranger's homepage into ad-signal detection and
email extraction, on a lead Nova then calls.

So acceptance requires the licence phone printed on the page, and these tests
pin that bar using real captured page shapes.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.skills import website_resolver as wr
from app.skills.website_resolver import (
    candidate_domains, is_non_business_host, resolve_website, verify_page,
)

OR_PHONE = "+15035757663"          # VITAN CONSTRUCTION LLC, verbatim from OR CCB


def _page(title="", body="", phone=""):
    return f"<html><head><title>{title}</title></head><body>{body} {phone}" \
           f"<p>We build custom homes across the region. Call today for a free " \
           f"estimate on your remodel or new build project.</p></body></html>"


# ── candidate generation is generous; acceptance is what is strict ──────────

# `candidate_domains` returns a LIST, so `x in cands` is exact element
# membership, not a substring match. Written as an explicit `==` comparison
# because the `in` form trips CodeQL's py/incomplete-url-substring-sanitization
# rule, which assumes the right-hand side is a string. Keeping the assertion
# unambiguous is cheaper than carrying a permanently red security gate.
def test_candidates_strip_legal_suffixes():
    cands = candidate_domains("CEDAR CREEK CONSTRUCTION LLC")
    assert any(d == "cedarcreekconstruction.com" for d in cands)


def test_candidates_drop_a_generic_trailing_word():
    cands = candidate_domains("CEDAR CREEK CONSTRUCTION LLC")
    assert any(d == "cedarcreek.com" for d in cands)


def test_candidates_are_bounded():
    assert len(candidate_domains("A B C D E F G CONSTRUCTION LLC")) <= 3


def test_candidates_empty_for_junk():
    assert candidate_domains("") == []
    assert candidate_domains("LLC") == []


# ── the acceptance rule ─────────────────────────────────────────────────────

def test_registry_phone_on_page_is_accepted():
    html = _page("Vitan Construction", "Portland Oregon", "(503) 575-7663")
    v = verify_page(html, "VITAN CONSTRUCTION LLC", OR_PHONE)
    assert v["confidence"] == 0.95
    assert OR_PHONE in v["evidence"]


def test_phone_matches_in_any_format():
    for fmt in ("503-575-7663", "503.575.7663", "5035757663", "(503) 575 7663",
                "1-503-575-7663"):
        v = verify_page(_page("Vitan Construction", "", fmt),
                        "VITAN CONSTRUCTION LLC", OR_PHONE)
        assert v["confidence"] == 0.95, fmt


def test_same_name_different_state_is_REJECTED():
    """The exact live failure: cedarcreekconstruction.com is a Pennsylvania
    company. Name matches perfectly; the phone does not."""
    html = _page("Cedar Creek Construction | Outdoor Living",
                 "Serving Chester County", "(610) 557-1376")
    v = verify_page(html, "CEDAR CREEK CONSTRUCTION LLC", "+15032013017")
    assert v["confidence"] == 0.0
    assert "same-named" in v["evidence"]


def test_name_match_alone_is_never_enough():
    html = _page("Bright Construction", "Quality builders since 1998")
    assert verify_page(html, "BRIGHT CONSTRUCTION LLC", "+19716786618")["confidence"] == 0.0


def test_wrong_phone_on_page_is_rejected():
    html = _page("Vitan Construction", "", "(231) 632-9653")
    assert verify_page(html, "VITAN CONSTRUCTION LLC", OR_PHONE)["confidence"] == 0.0


@pytest.mark.parametrize("marker", [
    "This domain is for sale", "NameBright - Coming Soon",
    "A WebsiteBuilder Website - Home", "Under Construction",
    "HugeDomains.com", "Welcome to nginx",
])
def test_parked_and_placeholder_pages_are_rejected(marker):
    """All observed live on 2026-08-05 returning HTTP 200."""
    html = _page(marker, marker, "(503) 575-7663")
    v = verify_page(html, "VITAN CONSTRUCTION LLC", OR_PHONE)
    assert v["confidence"] == 0.0, marker
    assert "parked" in v["evidence"]


def test_empty_shell_page_is_rejected():
    assert verify_page("<html><head></head><body></body></html>",
                       "VITAN CONSTRUCTION LLC", OR_PHONE)["confidence"] == 0.0


def test_empty_html_is_rejected():
    assert verify_page("", "X CONSTRUCTION", OR_PHONE)["confidence"] == 0.0


def test_phone_in_a_script_block_does_not_count():
    """Analytics/config blobs routinely carry unrelated numbers."""
    html = ("<html><head><title>Vitan Construction</title></head><body>"
            "<script>var t='5035757663';</script>"
            "<p>We build custom homes and remodels for local families here.</p>"
            "</body></html>")
    assert verify_page(html, "VITAN CONSTRUCTION LLC", OR_PHONE)["confidence"] == 0.0


# ── directories are never "the business's website" ──────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.yelp.com/biz/vitan", "https://www.bbb.org/us/or/portland",
    "https://www.facebook.com/vitan", "https://buildzoom.com/contractor/vitan",
    "https://www.houzz.com/pro/vitan", "https://ccb.state.or.us/search",
])
def test_directories_rejected(url):
    assert is_non_business_host(url)


def test_a_real_business_host_is_allowed():
    assert not is_non_business_host("https://vitanconstruction.com/about")


# ── the resolver end to end ─────────────────────────────────────────────────

def _client_returning(pages: dict):
    """Fake httpx client; `pages` maps url-substring -> html."""
    class _Resp:
        def __init__(self, url, text):
            self.url, self.text, self.status_code = url, text, (200 if text else 404)

    client = AsyncMock()

    async def _get(url, **kw):
        for frag, html in pages.items():
            if frag in url:
                return _Resp(url, html)
        return _Resp(url, "")
    client.get = _get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
async def test_resolves_when_the_phone_matches():
    pages = {"vitanconstruction.com": _page("Vitan Construction", "Portland",
                                            "(503) 575-7663")}
    with patch.object(wr.httpx, "AsyncClient", return_value=_client_returning(pages)):
        hit = await resolve_website("VITAN CONSTRUCTION LLC", phone=OR_PHONE,
                                    city="Clackamas", state="OR")
    assert hit["website"] == "https://vitanconstruction.com"
    assert hit["confidence"] == 0.95
    assert hit["source"] == "domain_guess"


@pytest.mark.asyncio
async def test_returns_empty_rather_than_a_plausible_guess():
    """A miss must beat a wrong domain — this is the whole point of the module."""
    pages = {"cedarcreekconstruction.com": _page("Cedar Creek Construction",
                                                 "Chester County", "(610) 557-1376")}
    with patch.object(wr.httpx, "AsyncClient", return_value=_client_returning(pages)):
        hit = await resolve_website("CEDAR CREEK CONSTRUCTION LLC",
                                    phone="+15032013017", city="Oregon City",
                                    state="OR")
    assert hit["website"] == ""
    assert hit["confidence"] == 0.0


@pytest.mark.asyncio
async def test_no_candidates_returns_empty():
    with patch.object(wr.httpx, "AsyncClient", return_value=_client_returning({})):
        assert (await resolve_website("LLC", phone=OR_PHONE))["website"] == ""


@pytest.mark.asyncio
async def test_network_failure_is_swallowed():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=RuntimeError("boom"))
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch.object(wr.httpx, "AsyncClient", return_value=client):
        assert (await resolve_website("VITAN CONSTRUCTION LLC",
                                      phone=OR_PHONE))["website"] == ""


@pytest.mark.asyncio
async def test_env_kill_switch(monkeypatch):
    monkeypatch.setenv("WEBSITE_RESOLUTION_ENABLED", "0")
    assert (await resolve_website("VITAN CONSTRUCTION LLC", phone=OR_PHONE))["website"] == ""


# ── SerpAPI tier: OFF by default, and never its own quota counter ───────────

@pytest.mark.asyncio
async def test_serpapi_tier_is_off_by_default(monkeypatch):
    """SerpAPI's 250/month is ONE pool shared with owner_finder's decision-maker
    fallback. The hunt runs hourly at 5 leads, so an on-by-default search tier
    would drain a month of quota in ~2 days and starve the owner lookups."""
    monkeypatch.setenv("SERPAPI_KEY", "fake")
    monkeypatch.delenv("WEBSITE_RESOLUTION_SERPAPI", raising=False)
    assert await wr._serpapi_candidates("X CONSTRUCTION", "Portland", "OR", 99.0) == []


@pytest.mark.asyncio
async def test_serpapi_tier_respects_the_score_threshold(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "fake")
    monkeypatch.setenv("WEBSITE_RESOLUTION_SERPAPI", "1")
    assert await wr._serpapi_candidates("X CONSTRUCTION", "Portland", "OR", 10.0) == []


@pytest.mark.asyncio
async def test_serpapi_tier_uses_the_shared_ration_counter(monkeypatch):
    """A private counter here would silently overrun the real 250/month cap."""
    monkeypatch.setenv("SERPAPI_KEY", "fake")
    monkeypatch.setenv("WEBSITE_RESOLUTION_SERPAPI", "1")
    seen = {}

    async def _fake_ration(key, cap, period, amount=1):
        seen["key"], seen["cap"] = key, cap
        return False        # pretend the cap is spent

    with patch("app.skills.owner_finder._ration_check_and_increment", _fake_ration):
        await wr._serpapi_candidates("X CONSTRUCTION", "Portland", "OR", 99.0)

    assert seen["key"] == "owner_finder:serp_monthly", \
        "must share owner_finder's counter, not open a second one"
    assert seen["cap"] == 250
