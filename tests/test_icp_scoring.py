"""Deterministic ICP scoring (SDR refocus, 2026-07-14).

The old score_lead() weighed company_size / B2B industry / email-opens — data
the hunt pipeline never has — so EVERY live lead scored exactly 50 (observed in
prod twice on 2026-07-13). These tests pin the replacement: the score must
discriminate on the fields enrichment actually collects.
"""
from app.skills.lead_validator import score_lead_icp


def _lead(**kw):
    base = {"business": "", "owner": "", "email": "", "phone": "", "website": "", "vertical": ""}
    base.update(kw)
    return base


def test_perfect_icp_lead_is_hot():
    """Exemplar moved to the real lead vertical 2026-08-09.

    This used to describe "Exotic Motors of Newport" as the perfect ICP lead.
    After ADR-0012/0015 that is not a prospect at all, and once the search
    query stopped feeding the scorer it landed on exactly 70 — passing only
    because full contact data happens to equal the HOT threshold, which made
    the test a coincidence rather than a check. A genuine ICP lead should
    clear the bar on ICP fit as well as contact data.
    """
    lead = _lead(business="Summit Custom Home Builders", owner="Todd Rowsell",
                 email="todd@summitcustomhomes.com", phone="+19495551234",
                 website="https://summitcustomhomes.com",
                 vertical="luxury home remodeling california")
    r = score_lead_icp(lead)
    assert r["score"] >= 70, r
    assert "HOT" in r["recommendation"]
    assert r["breakdown"]["luxury_signal"] == 20, "'custom home' is a can-afford signal"
    assert r["breakdown"]["vertical_match"] == 10, "'builders' is the lead vertical"


def test_empty_lead_is_skip():
    r = score_lead_icp(_lead(business="Some Shop"))
    assert r["score"] < 25
    assert "SKIP" in r["recommendation"]


def test_scores_discriminate_not_flat():
    """The regression that mattered: different inputs MUST give different scores."""
    scores = {
        score_lead_icp(_lead(business="A"))["score"],
        score_lead_icp(_lead(business="Luxury Auto Detail", email="info@lad.com"))["score"],
        score_lead_icp(_lead(business="Exotic Rentals LA", owner="Jane Smith",
                             email="jane@exoticrentals.com", phone="+13105550000",
                             website="https://exoticrentals.com"))["score"],
    }
    assert len(scores) == 3, f"scores must differ, got {scores}"
    assert 50 not in scores or len(scores) == 3  # no flat-50 collapse


def test_direct_email_beats_generic():
    direct = score_lead_icp(_lead(business="X Wraps", email="mike@xwraps.com"))["score"]
    generic = score_lead_icp(_lead(business="X Wraps", email="info@xwraps.com"))["score"]
    assert direct > generic


def test_luxury_and_vertical_signals_add():
    """Exemplars moved off automotive 2026-08-09 (ADR-0012/0015).

    This used to key on "Bob's Detail Shop" — "detail" was an ICP vertical
    keyword back when the lead vertical was luxury automotive. The assertion
    being made (a vertical keyword adds points; luxury adds more on top) is
    unchanged; only the vocabulary it demonstrates it with has moved to the
    vertical we actually sell to.
    """
    plain = score_lead_icp(_lead(business="Bob's Shop"))["score"]
    vertical = score_lead_icp(_lead(business="Bob's Remodel Shop"))["score"]
    luxury = score_lead_icp(_lead(business="Bob's Luxury Remodel Shop"))["score"]
    assert vertical > plain
    assert luxury > vertical


def test_the_search_query_cannot_inflate_the_score():
    """The 2026-08-09 defect: the score measured the QUERY, not the business.

    worker.py sets lead["vertical"] to the search query string, and the scorer
    used to include it in the haystack. So every lead a query returned earned
    +20 luxury and +10 vertical whether or not it was a prospect. In production
    that put nytimes.com and amazon.com at 65 WARM — level with every real WA
    contractor — and customink.com at 100 HOT, top of the whole pipeline.

    Two leads, same query, one obviously off-ICP: only the real one may score
    on ICP fit.
    """
    query = "luxury home remodeling washington"
    junk = score_lead_icp(_lead(business="nytimes.com", vertical=query))
    real = score_lead_icp(_lead(business="GOLAN CONSTRUCTION LLC", vertical=query))

    assert junk["breakdown"]["luxury_signal"] == 0, "the query leaked in as a luxury signal"
    assert junk["breakdown"]["vertical_match"] == 0, "the query leaked in as a vertical match"
    assert real["breakdown"]["vertical_match"] == 10, "a real contractor must match on its own name"
    assert real["score"] > junk["score"], "an off-ICP domain must not outscore a contractor"


def test_licence_registry_names_match_on_their_own():
    """"construction" and "contractor" were missing from the keyword list.

    Licence registries (WA L&I / OR CCB / CSLB) are the primary source per
    ADR-0014 and name rows exactly this way. Before 2026-08-09 these scored
    vertical_match only via the query string, so with the query removed they
    would have scored 0 on ICP fit — the cleanup and the haystack fix only
    work together.
    """
    for name in ("HAWK CONSTRUCTION", "GOLAN CONSTRUCTION LLC",
                 "FOREVER QUALITY CONSTRUCT LLC", "TA BUILDERS LLC",
                 "GOLDENKEY REMODELING LLC"):
        r = score_lead_icp(_lead(business=name))
        assert r["breakdown"]["vertical_match"] == 10, f"{name} scored 0 on ICP fit"


def test_off_icp_verticals_no_longer_score():
    """ADR-0012 demoted automotive; ADR-0015 removed med spas."""
    for name in ("Elite Auto Detailing", "Precision Window Tint",
                 "Radiance Med Spa", "Bayview Collision Center"):
        r = score_lead_icp(_lead(business=name))
        assert r["breakdown"]["vertical_match"] == 0, f"{name} still scores as on-ICP"


def test_breakdown_is_documented_and_sums():
    r = score_lead_icp(_lead(business="Exotic Car Rental", owner="Ana de Silva",
                             email="ana@ecr.com", phone="+15551234567",
                             website="https://ecr.com"))
    assert r["score"] == sum(r["breakdown"].values())
