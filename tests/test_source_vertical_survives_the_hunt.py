"""A source's real trade must survive the hunt, not be replaced by the query.

## The bug (production, 2026-08-09)

`worker.py` did this immediately before saving every hunted lead:

    lead["vertical"] = niche

an unconditional overwrite with the SEARCH QUERY STRING. So a WA L&I lead
carrying its actual licensed trade (`specialtycode1desc` = "General") was
stored as "custom home builder california", and the Niche column in the Leads
sheet showed the thing we searched for rather than the thing the business is.

This is the same query-string-as-data confusion that made the ICP scorer rank
nytimes.com level with a real contractor: `vertical` was being used as though
it described the business when it described the search.

The fix keeps the fallback — sources like a web search genuinely have no trade
to report — but stops it overwriting a source that does.
"""
def _apply_hunt_default(lead: dict, niche: str) -> dict:
    """The exact expression worker.py uses before asave_lead."""
    lead = dict(lead)
    lead["vertical"] = lead.get("vertical") or niche
    return lead


def test_a_registry_trade_is_not_overwritten_by_the_search_query():
    lead = {"business": "ACCRETE CONSTRUCTION LLC", "vertical": "General"}
    out = _apply_hunt_default(lead, "custom home builder california")
    assert out["vertical"] == "General", (
        "the licensed trade was replaced by the search string")


def test_a_source_without_a_trade_still_gets_the_niche():
    """Web-search and Maps leads have no licensed trade — the fallback stays."""
    out = _apply_hunt_default({"business": "Some Remodeler"}, "luxury home remodeling washington")
    assert out["vertical"] == "luxury home remodeling washington"


def test_an_empty_vertical_is_treated_as_absent():
    out = _apply_hunt_default({"business": "X", "vertical": ""}, "roofing seattle")
    assert out["vertical"] == "roofing seattle"


def test_worker_uses_the_non_clobbering_form():
    """Pin the actual source line, so the overwrite cannot creep back."""
    import pathlib
    import app.worker as w
    src = pathlib.Path(w.__file__).read_text(encoding="utf-8")
    assert 'lead["vertical"] = lead.get("vertical") or niche' in src, \
        "worker.py no longer preserves the source's own vertical"
    assert 'lead["vertical"] = niche\n' not in src, \
        "the unconditional overwrite is back"


def test_the_leads_api_exposes_principal_count():
    """Sole-owner status is the field that picks the call script's branch —
    it has to be visible in /api/leads and the dashboard."""
    import pathlib
    import app.main as m
    src = pathlib.Path(m.__file__).read_text(encoding="utf-8")
    assert "principal_count" in src, "/api/leads cannot show sole-owner status"
