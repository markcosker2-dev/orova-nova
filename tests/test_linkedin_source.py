"""Public-LinkedIn decision-maker source (2026-07-22). Parses public DuckDuckGo
result titles for linkedin.com/in profiles — never scrapes LinkedIn — and
requires a company match so a real person is never attached to the wrong lead.
"""
import asyncio

from app.skills.contact_waterfall import (
    _parse_linkedin_title,
    _company_matches,
    _source_linkedin,
)


# ── title parser (pure) ──────────────────────────────────────────────────────

def test_parse_name_role_company():
    assert _parse_linkedin_title(
        "Eric Curran - General Manager - West Coast Exotic Cars | LinkedIn"
    ) == ("Eric Curran", "General Manager")


def test_parse_name_company_only():
    assert _parse_linkedin_title("Jane Doe - West Coast Exotic Cars - LinkedIn") == ("Jane Doe", "")


def test_parse_role_at_company():
    assert _parse_linkedin_title("John Smith - Owner at West Coast Exotics | LinkedIn") == ("John Smith", "Owner")


def test_parse_empty():
    assert _parse_linkedin_title("") == ("", "")


# ── company match (anti-fabrication guard) ───────────────────────────────────

def test_company_matches_and_rejects():
    assert _company_matches("West Coast Exotic Cars", "Eric Curran - GM - West Coast Exotic | LinkedIn")
    assert not _company_matches("West Coast Exotic Cars", "Bob Jones - Owner - Acme Corp | LinkedIn")


# ── the source (patched SerpAPI search) ──────────────────────────────────────
import app.skills.contact_waterfall as _cw


def _patch_serp(monkeypatch, results):
    async def _fake(business):
        return results
    monkeypatch.setattr(_cw, "_serp_linkedin_search", _fake)


def test_source_extracts_matching_person(monkeypatch):
    _patch_serp(monkeypatch, [
        {"title": "Eric Curran - General Manager - West Coast Exotic Cars | LinkedIn",
         "link": "https://www.linkedin.com/in/eric-curran", "snippet": "West Coast Exotic Cars"},
    ])
    evs = asyncio.run(_source_linkedin({"business": "West Coast Exotic Cars"}))
    assert len(evs) == 1
    assert evs[0].value == "Eric Curran"
    assert evs[0].source == "linkedin_public"
    assert evs[0].title == "General Manager"
    assert evs[0].confidence == 68


def test_source_rejects_wrong_company(monkeypatch):
    # A real person, but their result names a DIFFERENT company → never attached.
    _patch_serp(monkeypatch, [
        {"title": "Bob Jones - Owner - Some Other Dealership | LinkedIn",
         "link": "https://www.linkedin.com/in/bob-jones", "snippet": "Some Other Dealership"},
    ])
    assert asyncio.run(_source_linkedin({"business": "West Coast Exotic Cars"})) == []


def test_source_skips_company_pages(monkeypatch):
    # /company/ URLs are not a person profile → skipped.
    _patch_serp(monkeypatch, [
        {"title": "West Coast Exotic Cars | LinkedIn",
         "link": "https://www.linkedin.com/company/west-coast-exotic-cars", "snippet": ""},
    ])
    assert asyncio.run(_source_linkedin({"business": "West Coast Exotic Cars"})) == []
