"""Hunt endpoint niche override + url-credit in ICP scoring (2026-07-20).

The Render TARGET_NICHE env has been stale-generic since 2026-07-15 and only
Mark can edit it — hunts kept returning off-ICP businesses. The endpoint now
accepts explicit niche/location so on-ICP hunts don't depend on env access.

score_lead_icp credited `website` but not `url`, so hunted leads carrying
their site in `url` silently lost 10 points; Yelp directory URLs must still
earn nothing (a Yelp page is not the business's own web presence).
"""
from unittest.mock import AsyncMock, patch

from app.skills.lead_validator import score_lead_icp
from tests.test_dashboard_api import _make_test_client

AUTH = {"X-API-Key": "test-dashboard-key"}


# ── scoring: url earns web-presence credit, Yelp URLs don't ──────────────────

def _base():
    return {"business": "Vivid Motors", "owner": "", "email": "", "phone": ""}


def test_score_credits_site_in_url_column():
    with_url = score_lead_icp({**_base(), "url": "https://vividmotors.com"})["breakdown"]
    assert with_url["website"] == 5


def test_score_yelp_url_earns_nothing():
    yelp = score_lead_icp({**_base(), "url": "https://www.yelp.com/biz/vivid-motors"})["breakdown"]
    assert yelp["website"] == 0


def test_score_website_column_still_wins_over_url():
    both = score_lead_icp({**_base(), "website": "https://vividmotors.com",
                           "url": "https://www.yelp.com/biz/vivid-motors"})["breakdown"]
    assert both["website"] == 5


def test_score_yelp_check_is_host_anchored():
    # 'notyelp.com' is NOT Yelp — must earn the credit (CodeQL: substring
    # matching at arbitrary positions is not sanitization)
    assert score_lead_icp({**_base(), "url": "https://notyelp.com"})["breakdown"]["website"] == 5
    # yelp.com in the PATH of a real site is not a directory link either
    assert score_lead_icp({**_base(), "url": "https://vivid.com/about-yelp.com"})["breakdown"]["website"] == 5
    # any true yelp subdomain IS Yelp
    assert score_lead_icp({**_base(), "url": "https://m.yelp.com/biz/x"})["breakdown"]["website"] == 0


# ── hunt endpoint: explicit niche/location pass through to the worker ────────

def test_hunt_endpoint_passes_niche_and_location():
    with _make_test_client() as client, \
         patch("app.worker.run_lead_hunt_slow_lane", new_callable=AsyncMock) as mock_hunt:
        resp = client.post("/api/actions/hunt-leads",
                           json={"niche": "exotic car dealer", "location": "Los Angeles CA"},
                           headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["niche"] == "exotic car dealer"
    assert body["location"] == "Los Angeles CA"
    mock_hunt.assert_called_once_with(client_id=0, niche="exotic car dealer",
                                      location="Los Angeles CA", state=None)


def test_hunt_endpoint_defaults_to_rotation():
    with _make_test_client() as client, \
         patch("app.worker.run_lead_hunt_slow_lane", new_callable=AsyncMock) as mock_hunt:
        resp = client.post("/api/actions/hunt-leads", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["niche"] == "(TARGET_NICHE rotation)"
    mock_hunt.assert_called_once_with(client_id=0, niche=None, location=None,
                                      state=None)


# ── hunt endpoint: jurisdiction is a separate, explicit parameter ───────────
# `location` is a SEARCH term; `state` is a legal jurisdiction that selects the
# licence registry. Conflating them is what let discovery decide which registry
# to query by substring-matching a search string.

def test_hunt_endpoint_passes_explicit_state():
    with _make_test_client() as client, \
         patch("app.worker.run_lead_hunt_slow_lane", new_callable=AsyncMock) as mock_hunt:
        resp = client.post("/api/actions/hunt-leads",
                           json={"niche": "remodelers", "state": "or"},
                           headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["state"] == "OR"
    mock_hunt.assert_called_once_with(client_id=0, niche="remodelers",
                                      location=None, state="OR")


def test_hunt_endpoint_state_absent_reports_the_fallback():
    with _make_test_client() as client, \
         patch("app.worker.run_lead_hunt_slow_lane", new_callable=AsyncMock):
        resp = client.post("/api/actions/hunt-leads", headers=AUTH)
    assert resp.json()["state"] == "(TARGET_STATE env / inferred)"
