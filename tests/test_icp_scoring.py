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
    lead = _lead(business="Exotic Motors of Newport", owner="Todd Rowsell",
                 email="todd@exoticmotors.com", phone="+19495551234",
                 website="https://exoticmotors.com", vertical="exotic car dealer")
    r = score_lead_icp(lead)
    assert r["score"] >= 70, r
    assert "HOT" in r["recommendation"]


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
    plain = score_lead_icp(_lead(business="Bob's Shop"))["score"]
    vertical = score_lead_icp(_lead(business="Bob's Detail Shop"))["score"]
    luxury = score_lead_icp(_lead(business="Bob's Luxury Detail Shop"))["score"]
    assert vertical > plain
    assert luxury > vertical


def test_breakdown_is_documented_and_sums():
    r = score_lead_icp(_lead(business="Exotic Car Rental", owner="Ana de Silva",
                             email="ana@ecr.com", phone="+15551234567",
                             website="https://ecr.com"))
    assert r["score"] == sum(r["breakdown"].values())
