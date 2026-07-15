"""Dossier v1 — stage-gated Analyst research (SDR Stage 2/4). 2026-07-15.

Pins: gating inputs, extraction happy path (mocked fetch + AI), the
never-invent guard, and fail-open behavior everywhere."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.skills import dossier


def _lead(**kw):
    base = {"business": "Exotic Motors LA", "website": "https://exoticmotors.com"}
    base.update(kw)
    return base


def _run(lead):
    return asyncio.run(dossier.build_dossier(lead))


def test_no_website_or_business_returns_empty():
    assert _run(_lead(website="")) == {}
    assert _run(_lead(business="")) == {}
    assert _run(_lead(website="not-a-url")) == {}


def test_happy_path_extracts_icebreaker():
    page = {"html": "<html><body>" + ("Exotic Motors LA — home of the 2020 "
            "Lamborghini Aventador SVJ and Ferrari 488 Pista. Family owned "
            "since 2004, serving Beverly Hills collectors. " * 20) + "</body></html>"}
    ai_json = ('{"icebreaker": "Saw the Aventador SVJ in your showroom — serious inventory.",'
               '"observations": ["stocks Aventador SVJ", "family owned since 2004"],'
               '"premium_signals": ["serves Beverly Hills collectors"]}')
    fake_ai = MagicMock()
    fake_ai.write = AsyncMock(return_value=ai_json)
    with patch("app.skills.light_enrich._fetch_page", new=AsyncMock(return_value=page)), \
         patch("app.core.ai_client.UnifiedAIClient", return_value=fake_ai):
        d = _run(_lead())
    assert "Aventador" in d["icebreaker"]
    assert len(d["observations"]) == 2
    assert d["premium_signals"] == ["serves Beverly Hills collectors"]


def test_unfetchable_site_returns_empty():
    with patch("app.skills.light_enrich._fetch_page", new=AsyncMock(return_value=None)):
        assert _run(_lead()) == {}


def test_ai_garbage_returns_empty():
    page = {"html": "<p>" + "Lots of real page text about cars. " * 50 + "</p>"}
    fake_ai = MagicMock()
    fake_ai.write = AsyncMock(return_value="I couldn't find anything useful, sorry!")
    with patch("app.skills.light_enrich._fetch_page", new=AsyncMock(return_value=page)), \
         patch("app.core.ai_client.UnifiedAIClient", return_value=fake_ai):
        assert _run(_lead()) == {}


def test_overlong_icebreaker_is_dropped_but_observations_kept():
    page = {"html": "<p>" + "Real text. " * 100 + "</p>"}
    long_ib = " ".join(["word"] * 30)
    fake_ai = MagicMock()
    fake_ai.write = AsyncMock(return_value=(
        '{"icebreaker": "%s", "observations": ["a real fact"], "premium_signals": []}' % long_ib))
    with patch("app.skills.light_enrich._fetch_page", new=AsyncMock(return_value=page)), \
         patch("app.core.ai_client.UnifiedAIClient", return_value=fake_ai):
        d = _run(_lead())
    assert d["icebreaker"] == ""            # too long to be a real opener
    assert d["observations"] == ["a real fact"]


def test_fail_open_on_exception():
    with patch("app.skills.light_enrich._fetch_page",
               new=AsyncMock(side_effect=RuntimeError("network down"))):
        assert _run(_lead()) == {}          # never raises into the hunt lane
