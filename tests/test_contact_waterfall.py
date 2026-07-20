"""Persistent decision-maker waterfall (ADR-0009, 2026-07-20).

The concrete failure this fixes: production stored
blake@westcoastexoticcars.com with owner="" — a human reads "Blake"
instantly. The waterfall must (a) infer the name from the email, (b) keep
going across sources, (c) cross-reference, (d) never fabricate, and record
a per-field evidence ledger.
"""
import asyncio
from datetime import date

from unittest.mock import AsyncMock, patch

from app.skills.contact_waterfall import (
    infer_name_from_email,
    detect_title,
    merge_candidates,
    resolve_decision_maker,
    apply_decision_maker,
    reenrich_stored_leads,
    DecisionMakerResult,
    Evidence,
    CONFIDENCE_STOP,
)

TODAY = date.today().isoformat()


# ── email local-part inference ───────────────────────────────────────────────

def test_infer_first_name_from_email():
    ev = infer_name_from_email("blake@westcoastexoticcars.com")
    assert ev is not None
    assert ev.value == "Blake"
    assert ev.source == "email_localpart" and ev.method == "inference"
    assert 30 <= ev.confidence < 50


def test_infer_full_name_from_dotted_email():
    ev = infer_name_from_email("john.smith@dealer.com")
    assert ev.value == "John Smith"
    assert ev.confidence == 50


def test_infer_rejects_generic_inboxes():
    for junk in ("info@x.com", "sales@x.com", "contact@x.com", "noreply@x.com",
                 "parts@dealer.com", "leasing@dealer.com"):
        assert infer_name_from_email(junk) is None, junk


def test_infer_rejects_business_word_and_unparseable_locals():
    assert infer_name_from_email("exotics@webuyexotics.com") is None  # business word
    assert infer_name_from_email("jsmith@x.com") is None              # ambiguous initial+last
    assert infer_name_from_email("b@x.com") is None                   # too short
    assert infer_name_from_email("not-an-email") is None


# ── title / role detection with decision-maker priority ──────────────────────

def test_detect_title_priority():
    assert detect_title("Jane is the Owner and Founder")[1] == "Owner"   # owner wins
    assert detect_title("our General Manager")[1] == "General Manager"
    assert detect_title("Chief Marketing Officer")[1] == "Marketing Director"
    assert detect_title("just some body text")[1] == ""


# ── cross-referencing ────────────────────────────────────────────────────────

def test_two_sources_agreeing_boost_confidence():
    evs = [
        Evidence("Blake Johnson", 55, "website_about", "page_scrape", TODAY),
        Evidence("Blake Johnson", 40, "search_snippet", "search", TODAY),
    ]
    r = merge_candidates(evs)
    assert r.name == "Blake Johnson"
    assert r.confidence == 70  # max(55,40) + 15 agreement bonus


def test_email_localpart_matching_a_source_verifies_email():
    evs = [
        Evidence("Blake", 35, "email_localpart", "inference", TODAY),
        Evidence("Blake Johnson", 70, "website_team", "page_scrape", TODAY, title="Owner"),
    ]
    r = merge_candidates(evs)
    # different normalized names -> NOT auto-verified; full name wins on conf
    assert r.name == "Blake Johnson"


def test_email_verification_when_names_match():
    evs = [
        Evidence("Blake Johnson", 50, "email_localpart", "inference", TODAY),
        Evidence("Blake Johnson", 70, "website_team", "page_scrape", TODAY, title="Owner"),
    ]
    r = merge_candidates(evs)
    assert r.email_verified_personal is True
    assert r.title == "Owner"
    assert r.confidence >= 85  # 70 +15 agreement +10 email-verify, capped 97


def test_merge_empty_is_fabrication_safe():
    r = merge_candidates([])
    assert r.name == "" and r.confidence == 0 and r.ledger() == []


def test_higher_confidence_candidate_wins():
    evs = [
        Evidence("Alex Reed", 85, "ca_sos", "registry_api", TODAY, title="Owner"),
        Evidence("Sam Poe", 40, "search_snippet", "search", TODAY),
    ]
    assert merge_candidates(evs).name == "Alex Reed"


# ── orchestration: persistent, ordered, stop-early ───────────────────────────

def _stub(*evs_lists):
    """Build patchable async sources returning canned evidence lists."""
    async def make(evs):
        return list(evs)
    return [(lambda e=evs: (lambda lead: make(e)))() for evs in evs_lists]


def test_waterfall_infers_blake_from_email_alone():
    # The exact production lead: only a personal email, no other data.
    lead = {"business": "West Coast Exotic Cars",
            "email": "blake@westcoastexoticcars.com",
            "website": "http://westcoastexoticcars.com/"}

    async def only_email(l):
        from app.skills.contact_waterfall import _source_email_inference
        return await _source_email_inference(l)

    async def nothing(l):
        return []

    r = asyncio.run(resolve_decision_maker(lead, sources=[only_email, nothing]))
    assert r.name == "Blake"
    assert r.source == "email_localpart"
    assert r.confidence >= 30
    assert any(e["source"] == "email_localpart" for e in r.ledger())


def test_waterfall_continues_past_failing_sources():
    lead = {"business": "Dealer", "email": "", "website": "http://x.com"}

    async def dead1(l):
        raise RuntimeError("source down")

    async def dead2(l):
        return []

    async def hit(l):
        return [Evidence("Dana Ferrari", 60, "website_about", "page_scrape", TODAY)]

    r = asyncio.run(resolve_decision_maker(lead, sources=[dead1, dead2, hit]))
    assert r.name == "Dana Ferrari"  # did NOT give up after dead1 raised


def test_waterfall_stops_early_on_strong_candidate():
    lead = {"business": "Dealer", "email": "", "website": "http://x.com"}
    calls = {"n": 0}

    async def strong(l):
        calls["n"] += 1
        return [Evidence("Alex Reed", 90, "ca_sos", "registry_api", TODAY, title="Owner")]

    async def should_not_run(l):
        calls["n"] += 100
        return []

    r = asyncio.run(resolve_decision_maker(lead, sources=[strong, should_not_run]))
    assert r.confidence >= CONFIDENCE_STOP
    assert calls["n"] == 1  # second source never called


# ── apply_decision_maker: upgrade-only, never downgrade ──────────────────────

def test_apply_upgrades_and_sets_evidence():
    lead = {"business": "X", "owner": "", "owner_confidence": 0,
            "email": "blake@x.com", "email_status": "found"}
    dm = DecisionMakerResult(name="Blake Johnson", title="Owner", confidence=85,
                             source="website_team",
                             evidence=[Evidence("Blake Johnson", 70, "website_team", "page_scrape", TODAY, title="Owner"),
                                       Evidence("Blake Johnson", 50, "email_localpart", "inference", TODAY)],
                             email_verified_personal=True)
    apply_decision_maker(lead, dm)
    assert lead["owner"] == "Blake Johnson"
    assert lead["owner_title"] == "Owner"
    assert lead["owner_confidence"] == 85
    assert '"source": "website_team"' in lead["evidence_json"]
    assert lead["email_status"] == "verified"  # dm match verified the email


def test_apply_does_not_downgrade_stronger_existing_owner():
    lead = {"business": "X", "owner": "Alex Reed", "owner_confidence": 90,
            "owner_source": "ca_sos"}
    dm = DecisionMakerResult(name="Blake", confidence=35, source="email_localpart")
    apply_decision_maker(lead, dm)
    assert lead["owner"] == "Alex Reed"  # registry hit preserved
    assert lead["owner_confidence"] == 90


def test_apply_ignores_unconfident_result():
    lead = {"business": "X", "owner": "", "owner_confidence": 0}
    dm = DecisionMakerResult(name="Maybe Someone", confidence=20, source="search_snippet")
    apply_decision_maker(lead, dm)
    assert lead["owner"] == ""  # below CONFIDENCE_MIN, not stored


# ── reenrich lane over stored leads ──────────────────────────────────────────

def test_reenrich_upgrades_low_confidence_lead():
    stored = [{"id": 1, "business": "West Coast Exotic Cars",
               "email": "blake@westcoastexoticcars.com",
               "website": "http://westcoastexoticcars.com/", "owner": "",
               "owner_confidence": 0, "score": 75}]
    updates = []

    async def fake_query(sql, params=(), fetchall=False):
        if fetchall:
            return stored
        updates.append((sql, params))
        return None

    dm = DecisionMakerResult(name="Blake", confidence=35, source="email_localpart",
                             evidence=[Evidence("Blake", 35, "email_localpart", "inference", TODAY)])
    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.skills.contact_waterfall.resolve_decision_maker",
               new_callable=AsyncMock, return_value=dm):
        summary = asyncio.run(reenrich_stored_leads(limit=10))
    assert summary["upgraded"] == 1
    assert summary["found_names"][0]["owner"] == "Blake"
    # a background state_store write may interleave, so match any update
    assert any("UPDATE leads SET owner" in u[0] for u in updates)


def test_reenrich_skips_when_no_improvement():
    stored = [{"id": 1, "business": "X", "owner": "Alex Reed",
               "owner_confidence": 90, "score": 50}]

    async def fake_query(sql, params=(), fetchall=False):
        return stored if fetchall else None

    dm = DecisionMakerResult(name="Blake", confidence=35, source="email_localpart")
    with patch("app.core.database.DatabaseManager.query", side_effect=fake_query), \
         patch("app.skills.contact_waterfall.resolve_decision_maker",
               new_callable=AsyncMock, return_value=dm):
        summary = asyncio.run(reenrich_stored_leads(limit=10))
    assert summary["upgraded"] == 0


# ── storage + schema wiring ──────────────────────────────────────────────────

def test_canonical_schema_has_waterfall_columns():
    from app.core._db_base import CANONICAL_SCHEMA_SQL
    for col in ("owner_confidence", "evidence_json"):
        assert col in CANONICAL_SCHEMA_SQL


def test_storage_gate_accepts_vetted_single_first_name():
    # "Blake" is a single token — the shape heuristic rejects it, but a
    # positive owner_confidence means the waterfall vetted it.
    from app.skills.lead_validator import validate_lead_for_storage
    result = validate_lead_for_storage({
        "business": "West Coast Exotic Cars", "owner": "Blake",
        "owner_confidence": 35, "owner_source": "email_localpart",
        "email": "blake@westcoastexoticcars.com"})
    assert result["ok"] is True
    assert result["lead"]["owner"] == "Blake"


def test_storage_gate_still_drops_unvetted_fragment():
    from app.skills.lead_validator import validate_lead_for_storage
    result = validate_lead_for_storage({"business": "X", "owner": "THANKS TO",
                                        "owner_confidence": 0})
    assert result["lead"]["owner"] == ""


def test_confidence_uses_waterfall_owner_confidence():
    from app.skills.lead_validator import contact_confidence
    # single-token "Blake" would be 0 by shape, but ledger confidence wins
    assert contact_confidence({"owner": "Blake", "owner_confidence": 35})["owner"] == 35
