"""Owner report, 2026-08-02: "why is nova in telegram always sending me
automotive leads?" and "i need Nova to stop spamming me with the thing only
once and done".

Three defects sat behind those two sentences. Each gets a test here.

1. The hunt rotation actively SEARCHED for automotive — 2 of 14 entries, picked
   uniformly, so ~14% of every hunt.
2. The ADR-0012 opportunistic exemption read the marker out of `vertical`, and
   worker.py sets `vertical = niche` (the raw query string). So the query
   'exotic car dealer california' exempted EVERY row it returned, including
   plain dealers and repair shops. A live probe put 5 of 8 automotive rows
   through the gate.
3. Cosmetic auto services (detailing / ceramic / PPF / tint) appeared in no
   off-ICP list at all.

The false-positive discipline of tests/test_icp_name_gate.py is repeated here:
a wrongly-blocked remodeler is a lost prospect, so every new pattern is checked
against real in-ICP naming.
"""
import pytest

from app.skills.lead_validator import (
    off_icp_vertical_reason,
    off_icp_business_name_reason,
)
from app.worker import DEFAULT_HUNT_NICHES


def _gate(business: str, vertical: str = "") -> str:
    """Both legs, in the order the pipeline applies them."""
    lead = {"business": business, "vertical": vertical}
    return off_icp_vertical_reason(lead) or off_icp_business_name_reason(lead)


# ── 1. The rotation must not hunt automotive ────────────────────────────────

_AUTO_QUERY_MARKERS = ("car", "auto", "vehicle", "ceramic coating", "detailing")


def test_hunt_rotation_contains_no_automotive_niche():
    offenders = [n for n in DEFAULT_HUNT_NICHES
                 if any(m in n.lower() for m in _AUTO_QUERY_MARKERS)]
    assert offenders == [], (
        f"automotive niches back in the hunt rotation: {offenders}. ADR-0012 "
        f"ranks exotic auto opportunistic-only; a rotation slot spends "
        f"discovery budget on it every seventh run."
    )


def test_hunt_rotation_is_still_populated_and_on_icp():
    """Subtraction must not empty the rotation — that would silently stop the
    hunt rather than redirect it."""
    assert len(DEFAULT_HUNT_NICHES) >= 8
    assert any("home" in n or "remodel" in n for n in DEFAULT_HUNT_NICHES)
    # Med spas left the rotation on 2026-08-09 (ADR-0015 — "our ICP was never
    # med spas"), so the guard inverts: this file's whole point is that
    # subtraction must REDIRECT the hunt, never empty it. The length floor
    # above is what protects that; the vertical assertions below say which
    # verticals are legitimately gone.
    assert not any("med spa" in n or "medical spa" in n or "cosmetic surgery" in n
                   for n in DEFAULT_HUNT_NICHES)


# ── 2. The exemption must read the business, not the query ──────────────────

# This is the exact production shape: vertical IS the search string.
_EXOTIC_QUERY = "exotic car dealer california"


@pytest.mark.parametrize("business", [
    "Prestige Auto Sales",
    "Bob's Auto Repair",
    "Metro Ford Dealership",
])
def test_off_icp_names_blocked_even_under_the_exotic_exemption(business):
    """The vertical leg exempts anything whose vertical carries an exotic/
    luxury/classic marker — and worker.py sets vertical = the query string, so
    'exotic car dealer california' exempts every row it returns. The NAME leg
    is what still has to catch a repair shop or a franchised dealer."""
    assert _gate(business, _EXOTIC_QUERY), (
        f"{business!r} walked BOTH legs of the ICP gate"
    )


def test_generic_name_from_an_exotic_query_stays_exempt_by_design():
    """Documented residual, not an oversight: a lead found by an exotic-dealer
    search probably IS one, and ADR-0012 keeps that segment opportunistic
    rather than excluded. The control is upstream — automotive is no longer in
    the hunt rotation at all (see test_hunt_rotation_contains_no_automotive_niche)."""
    assert _gate("Sunset Motors", _EXOTIC_QUERY) == ""


@pytest.mark.parametrize("business", [
    "West Coast Exotic Cars",
    "Beverly Hills Luxury Motorcars",
    "Classic Car Gallery",
])
def test_genuinely_exotic_businesses_stay_opportunistic(business):
    """ADR-0012 keeps exotic/luxury/classic as opportunistic, NOT excluded —
    the carve-out still applies when the BUSINESS is the evidence."""
    assert _gate(business, _EXOTIC_QUERY) == ""


# ── 3. Cosmetic auto services are off-ICP ───────────────────────────────────

_DETAILING_QUERY = "ceramic coating auto detailing california"


@pytest.mark.parametrize("business", [
    "Elite Ceramic Coating",
    "Precision Auto Detailing",
    "ClearShield Paint Protection Film",
    "Apex Window Tinting",
    "Northwest PPF",
    "Sound Vinyl Wraps",
])
def test_cosmetic_auto_services_are_blocked(business):
    """A tint job grosses a few hundred dollars; ADR-0012's qualifying test
    asks whether ONE extra deal covers a ~$6.5-7.5K/mo retainer."""
    assert _gate(business, _DETAILING_QUERY), f"{business!r} passed the ICP gate"


def test_detailing_query_alone_blocks_even_an_unnamed_row():
    """Licence-registry rows arrive with no vertical; hunt rows arrive with the
    query as the vertical. The query leg must stand on its own."""
    assert _gate("", _DETAILING_QUERY)


# ── The false-positive bar: real in-ICP names must still pass ───────────────

IN_ICP_CONTROLS = [
    # the 10 researched Seattle targets, plus deliberate near-misses on the
    # new patterns: "Detail Oriented" vs "detailing", "Wraparound" vs "wraps".
    "Wise Choice Construction",
    "Level Up Construction & Remodeling",
    "Eagle Remodel & Construction",
    "NW Quality Construction",
    "Cruz Construction & Renovation",
    "Dream Home Construction",
    "Cobalt Construction",
    "Cherry Design + Build",
    "Your Home Builders",
    "JD McDowell Construction",
    "Detail Oriented Custom Homes",
    "Wraparound Porch Builders",
    "Retirement Living Builders",
    "Autumn Ridge Custom Homes",
    "Mechanical Contractors of Seattle",
    "Pinnacle Luxury Renovations",
    "Radiance Med Spa",
    "Bellevue Luxury Properties Group",
]


@pytest.mark.parametrize("business", IN_ICP_CONTROLS)
def test_zero_false_positives_on_real_in_icp_names(business):
    assert _gate(business, "custom home builder california") == "", (
        f"{business!r} was wrongly quarantined — a blocked remodeler is a lost "
        f"prospect, which costs more than an automotive lead getting through."
    )


# ── 4. The hunt report must not re-announce the same businesses ─────────────
# "i need Nova to stop spamming me with the thing only once and done".

import asyncio                                              # noqa: E402
from unittest.mock import AsyncMock, patch                  # noqa: E402


def _hunt_patches(found_leads, state):
    """Mirrors tests/test_post_hunt_snapshot.py, plus a fake state store so the
    debounce is exercised rather than stubbed out."""
    async def _get_state(key, default=None):
        return state.get(key, default)

    async def _set_state(key, value):
        state[key] = value

    return [
        patch("app.worker.find_leads", new_callable=AsyncMock,
              return_value={"leads": found_leads, "text": "t"}),
        patch("app.worker.enrich_lead_lite", new_callable=AsyncMock,
              side_effect=lambda l: l),
        patch("app.worker.DatabaseManager.asave_lead", new_callable=AsyncMock,
              return_value=7),
        patch("app.worker.DatabaseManager.aget_metrics", new_callable=AsyncMock,
              return_value={"cost": 0}),
        patch("app.worker.DatabaseManager.aupdate_metrics", new_callable=AsyncMock),
        patch("app.worker.DatabaseManager.get_state", side_effect=_get_state),
        patch("app.worker.DatabaseManager.set_state", side_effect=_set_state),
        patch("app.skills.vault_skill.backup_database", new_callable=AsyncMock,
              return_value={"ok": True, "filename": "b.db"}),
    ]


def _run_hunt_capturing_reports(found_leads, state, runs=1):
    from app.worker import run_lead_hunt_slow_lane
    sent = []

    async def _capture(msg):
        sent.append(msg)

    p = _hunt_patches(found_leads, state)
    with p[0], p[1], p[2], p[3], p[4], p[5], p[6], p[7], \
         patch("app.worker.send_telegram_report", side_effect=_capture):
        for _ in range(runs):
            asyncio.run(run_lead_hunt_slow_lane(
                client_id=0, niche="custom home builder", location="California"))
    return sent


_BATCH = [{"business": "Cherry Design + Build", "url": "https://c.com",
           "owner_name": "Ann Lee", "email": "", "phone": "", "score": 0}]


def test_identical_hunt_batch_reports_once_not_every_run():
    state = {}
    sent = _run_hunt_capturing_reports(_BATCH, state, runs=3)
    assert len(sent) == 1, (
        f"the same batch paged Telegram {len(sent)}x — this is the reported spam"
    )


def test_a_genuinely_new_batch_still_pages_immediately():
    """The debounce must not swallow real news."""
    state = {}
    first = _run_hunt_capturing_reports(_BATCH, state, runs=1)
    other = [{"business": "Dream Home Construction", "url": "https://d.com",
              "owner_name": "Bo Ruiz", "email": "", "phone": "", "score": 0}]
    second = _run_hunt_capturing_reports(other, state, runs=1)
    assert len(first) == 1 and len(second) == 1


def test_debounce_fails_open_when_the_state_store_errors():
    """A state-store failure must send, never silently swallow an alert."""
    from app.worker import run_lead_hunt_slow_lane
    sent = []

    async def _capture(msg):
        sent.append(msg)

    p = _hunt_patches(_BATCH, {})
    with p[0], p[1], p[2], p[3], p[4], p[7], \
         patch("app.worker.DatabaseManager.get_state",
               side_effect=RuntimeError("db gone")), \
         patch("app.worker.DatabaseManager.set_state",
               side_effect=RuntimeError("db gone")), \
         patch("app.worker.send_telegram_report", side_effect=_capture):
        asyncio.run(run_lead_hunt_slow_lane(
            client_id=0, niche="custom home builder", location="California"))
    assert len(sent) == 1
