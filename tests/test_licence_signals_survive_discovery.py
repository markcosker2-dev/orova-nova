"""The ICP signals must survive the trip out of discovery.

## The bug (production, 2026-08-14)

`find_leads_v3` emits licence-registry leads through a hand-built dict at
`licence_out`. The comment above it says they "are emitted directly" — they are
not. They are projected through a WHITELIST, and that whitelist omitted exactly
three fields:

* `principal_count` — the urgency signal, and what `crew_status` derives
  sole-owner status from
* `insurance_amt`   — the affordability signal, worth up to 20 of the score
* `vertical`        — the licensed trade the registry actually publishes

Everything upstream worked. Production logs from the hunt that exposed this:

    [WA_LNI] principals resolved for 25/25 businesses · 6 are sole operators
    [WA_LNI] insurance resolved for 25/25 businesses · 1 carry above $1M
    [WA_LNI] ranked 25 candidates — returning 5, 5 sole operators

Five sole operators, ranked on cover, handed to a projection that dropped both
signals it had just ranked on. Every stored lead therefore had
`principal_count = 0` (crew_status "unknown", so the Retell script asks a
question the registry already answered, and the sheet's SoleOwner column reads
Unknown for everyone), `insurance_amt` absent (affordability scores the neutral
10 for everyone), and `vertical` falling back to the SEARCH QUERY — the exact
query-string-as-data confusion #162 was supposed to have ended.

The result was a flat score of 61 across every registry lead: the signature of
a scorer receiving nothing, which is the same failure `score_lead_icp` was
created to fix when every lead scored 50.

## Why it survived a test

`test_source_vertical_survives_the_hunt.py` asserts on `_apply_hunt_default`, a
LOCAL RE-IMPLEMENTATION of the one line worker.py runs. It passes, and always
would have, because the field was already gone two layers upstream.

A mock easier to satisfy than production is a decoy, not a test. These tests
therefore drive the real `find_leads_v3` and assert on what it actually emits.
"""
import asyncio

import pytest

from app.skills import lead_gen_v3 as v3

REGISTRY_LEAD = {
    "business": "LEWCO CONTRACTING",
    "owner_name": "Patrick Lewis",
    "owner_title": "Licence Principal",
    "owner_source": "wa_lni",
    "owner_confidence": 90,
    "phone": "+12536778727",
    "phone_source": "wa_lni",
    "phone_verified": True,
    "state": "WA",
    "vertical": "General",          # specialtycode1desc — the REAL trade
    "principal_count": 1,           # sole operator
    "insurance_amt": 2_000_000.0,   # $2M cover
    "url": "",
    "website": "",
    "email": "",
    "notes": "WA L&I licence LEWCOC*123AB · Corporation · effective 2001-01-01",
}


@pytest.fixture
def only_the_registry(monkeypatch):
    """Registry returns one rich lead; every web tier is silenced."""
    async def _registry(count):
        return [dict(REGISTRY_LEAD)]

    monkeypatch.setattr(v3, "licence_registry_for", lambda state: _registry)

    async def _none(*a, **k):
        return []

    for fn in ("_source_serpapi_maps", "_source_google_maps", "_source_duckduckgo"):
        if hasattr(v3, fn):
            monkeypatch.setattr(v3, fn, _none)
    return _registry


def _hunt(count=5, state="WA"):
    return asyncio.run(v3.find_leads_v3(count=count, query="custom home builder",
                                        state=state))


def test_the_sole_owner_signal_reaches_the_caller(only_the_registry):
    """principal_count drives crew_status, the sheet, and which pain the call opens on."""
    lead = _hunt()["leads"][0]
    assert lead.get("principal_count") == 1, (
        "the hunt ranked on this and then dropped it — crew_status reads "
        "'unknown' and Retell asks a question the registry already answered"
    )


def test_the_affordability_signal_reaches_the_caller(only_the_registry):
    """insurance_amt is worth up to 20 points — the largest scoring component."""
    lead = _hunt()["leads"][0]
    assert lead.get("insurance_amt") == 2_000_000.0, (
        "without cover every lead scores the neutral 10 for affordability"
    )


def test_the_licensed_trade_reaches_the_caller(only_the_registry):
    """The registry publishes the real trade; the query is not a fact about the business."""
    lead = _hunt()["leads"][0]
    assert lead.get("vertical") == "General", (
        "an empty vertical makes worker.py fall back to the search query, which "
        "is the query-string-as-data confusion #162 was meant to end"
    )


def test_the_lead_scores_on_the_signals_it_was_ranked_on(only_the_registry):
    """End to end: a $2M sole operator must not score like an unknown."""
    from app.skills.lead_validator import score_lead_icp

    lead = _hunt()["leads"][0]
    scored = score_lead_icp(lead)["breakdown"]
    assert scored["affordability"] == 20, "a $2M cover is the top affordability band"
    assert scored["urgency"] == 3, "a sole operator scores the solo urgency band"


def test_provenance_still_survives(only_the_registry):
    """The fields that already worked must keep working."""
    lead = _hunt()["leads"][0]
    assert lead["business"] == "LEWCO CONTRACTING"
    assert lead["owner_name"] == "Patrick Lewis"
    assert lead["phone"] == "+12536778727"
    assert lead["owner_source"] == "wa_lni"
    assert lead["state"] == "WA"
    assert lead["email"] == "", "licence data carries no email and must never guess one"
