"""Jurisdiction is first-class data, not a substring of a search query.

Before this seam, `find_leads_v3` decided which legal licence registry to query
by substring-matching the free-text hunt query for "california"/"washington"/
"oregon", and the WA registry was reachable only through a hardcoded
`if state == "WA"` branch. Two consequences, both live in production:

  · A hunt whose niche omitted the geography got state="" and silently skipped
    every registry, dropping to the legacy scrapers that the module itself
    documents as producing leads that cannot be called.
  · Adding a second state meant editing the control flow of the main entry
    point rather than adding a row of data.

These tests pin the contract: an explicit `state=` wins, the dispatch is a
table, and the no-registry case is loud rather than silent.
"""
import asyncio
import logging

import pytest

from app.skills import lead_gen_v3


# ── the dispatch table ──────────────────────────────────────────────────────

def test_wa_is_registered_as_a_table_row_not_a_branch():
    """WA reaches its registry through LICENCE_REGISTRIES, not an if-branch."""
    assert "WA" in lead_gen_v3.LICENCE_REGISTRIES
    assert (lead_gen_v3.LICENCE_REGISTRIES["WA"]
            is lead_gen_v3._source_wa_lni_licences)


def test_licence_registry_for_is_case_and_space_insensitive():
    assert lead_gen_v3.licence_registry_for("wa") is not None
    assert lead_gen_v3.licence_registry_for("  Wa  ") is not None
    assert lead_gen_v3.licence_registry_for("") is None
    # CA has no free registry API (CSLB is a manual download) — absence is a
    # fact about the state, and must read as None rather than raise.
    assert lead_gen_v3.licence_registry_for("CA") is None


def test_register_licence_registry_adds_a_state(monkeypatch):
    """Adding a jurisdiction is data, not control flow."""
    monkeypatch.setattr(lead_gen_v3, "LICENCE_REGISTRIES",
                        dict(lead_gen_v3.LICENCE_REGISTRIES))

    async def _fake(count):
        return []

    lead_gen_v3.register_licence_registry("zz", _fake)
    assert lead_gen_v3.licence_registry_for("ZZ") is _fake


# ── explicit state beats query inference ────────────────────────────────────

def _run_with_stubs(monkeypatch, query, state, registry_states=("WA",)):
    """Run find_leads_v3 with every network source stubbed out.

    Returns the list of state codes whose registry actually got called.
    """
    called: list = []

    def _make(code):
        async def _src(count):
            called.append(code)
            return []
        return _src

    monkeypatch.setattr(lead_gen_v3, "LICENCE_REGISTRIES",
                        {c: _make(c) for c in registry_states})
    # Silence every other discovery source — this test is about routing only.
    async def _none(*a, **k):
        return []
    monkeypatch.setattr(lead_gen_v3, "_source_serpapi_maps", _none)
    monkeypatch.setattr(lead_gen_v3, "_source_google_maps", _none)
    monkeypatch.setattr(lead_gen_v3, "_source_duckduckgo", _none)
    monkeypatch.setattr(lead_gen_v3, "_source_yelp_businesses", _none)

    asyncio.run(lead_gen_v3.find_leads_v3(count=1, query=query, state=state))
    return called


def test_explicit_state_selects_the_registry(monkeypatch):
    assert _run_with_stubs(monkeypatch, query="remodelers", state="WA") == ["WA"]


def test_explicit_state_overrides_a_conflicting_query(monkeypatch):
    """The query says california, the caller says WA. The CALLER wins.

    This is the whole point of the seam: the hunt lane knows its jurisdiction,
    and a word in a search string must not be able to override it.
    """
    called = _run_with_stubs(monkeypatch, query="custom home builder california",
                             state="WA")
    assert called == ["WA"]


def test_state_is_normalised(monkeypatch):
    assert _run_with_stubs(monkeypatch, query="remodelers", state=" wa ") == ["WA"]


def test_query_inference_still_works_when_no_state_is_passed(monkeypatch):
    """Back-compat: existing callers that pass no state keep today's behaviour."""
    called = _run_with_stubs(monkeypatch, query="remodelers washington", state="")
    assert called == ["WA"]


def test_unregistered_state_runs_no_registry(monkeypatch):
    """California resolves a jurisdiction but has no registry — and must not
    silently borrow another state's."""
    called = _run_with_stubs(monkeypatch, query="remodelers", state="CA")
    assert called == []


def test_no_jurisdiction_runs_no_registry(monkeypatch):
    called = _run_with_stubs(monkeypatch, query="remodelers", state="")
    assert called == []


# ── the silent-fallthrough failure is now loud ──────────────────────────────

def test_missing_jurisdiction_is_logged_as_a_warning(monkeypatch, caplog):
    """A hunt with no jurisdiction skips every registry and lands on the
    scrapers. That used to happen silently; it must now be visible in
    /api/logs, because it is the difference between a callable lead and one
    that can never reach outreach_ready."""
    with caplog.at_level(logging.WARNING, logger=lead_gen_v3.logger.name):
        _run_with_stubs(monkeypatch, query="custom home builder", state="")
    assert any("NO JURISDICTION" in r.message for r in caplog.records), \
        "an unresolved jurisdiction must warn, not pass quietly"


def test_state_without_a_registry_is_logged(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger=lead_gen_v3.logger.name):
        _run_with_stubs(monkeypatch, query="remodelers", state="CA")
    assert any("no licence registry for state=CA" in r.message
               for r in caplog.records)


# ── provenance is not hardcoded to WA ───────────────────────────────────────

def test_licence_lead_provenance_comes_from_the_registry(monkeypatch):
    """A registry lead's state/source must come from the emitting registry.

    The emit block used to default owner_source/phone_source to "wa_lni" and
    state to "WA". With a second registry registered that mislabels every
    non-WA lead — attaching WA provenance to an Oregon record.
    """
    async def _or_like(count):
        return [{
            "business": "CEDAR CREEK CONSTRUCTION LLC",
            "owner_name": "Timothy Hoffman",
            "owner_title": "Responsible Managing Individual",
            "owner_source": "or_ccb",
            "owner_confidence": 90,
            "phone": "+15032013017",
            "phone_source": "or_ccb",
            "phone_verified": True,
            "state": "OR",
            "notes": "OR CCB licence 123456",
        }]

    monkeypatch.setattr(lead_gen_v3, "LICENCE_REGISTRIES", {"OR": _or_like})
    async def _none(*a, **k):
        return []
    for name in ("_source_serpapi_maps", "_source_google_maps",
                 "_source_duckduckgo", "_source_yelp_businesses"):
        monkeypatch.setattr(lead_gen_v3, name, _none)

    out = asyncio.run(lead_gen_v3.find_leads_v3(count=1, query="remodelers",
                                                state="OR"))
    lead = out["leads"][0]
    assert lead["state"] == "OR"
    assert lead["owner_source"] == "or_ccb"
    assert lead["phone_source"] == "or_ccb"
    # The specific regression: no WA fingerprints on an Oregon lead.
    assert "wa_lni" not in (lead["owner_source"], lead["phone_source"])
