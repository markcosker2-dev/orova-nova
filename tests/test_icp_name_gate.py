"""ADR-0012 ICP gate — the business-name leg (2026-07-29).

Why this file exists: on 2026-07-29 production held exactly one lead,
"Keith's Auto Repair", with an EMPTY vertical and status 'Contacted'. The boot
hygiene sweep ran the vertical-only ICP gate over it and logged
"[HYGIENE] sweep clean: 1 leads OK" — a general auto repair shop, which
ADR-0012 disqualifies on sight, passed because nothing read the name.

The owner rule for any new detector is: run it against ~10 real in-ICP examples
and check the hit rate per signal; anything firing near 100% or 0% is noise.
A name matcher is worthless if it also blocks real remodelers, so the
false-positive suite below is the point of this file, not an afterthought.
"""
import pytest

from app.skills.lead_validator import (
    off_icp_business_name_reason,
    off_icp_trade_reason,
    off_icp_vertical_reason,
    validate_lead_for_storage,
)

# ── In-ICP names that MUST survive the gate ──────────────────────────────────
# ADR-0012's ranked ICP: custom home builders / high-end remodelers (lead),
# med spas, luxury RE. Several are deliberate near-misses on the patterns:
#   "Mechanical" vs \bmechanic\b · "Retirement" vs \btire\b
#   "Autumn"/"Automatic" vs \bauto\b · "Carriage"/"Carlton" vs \bcar\b
IN_ICP_NAMES = [
    "Whitestone Custom Homes",
    "Alderwood Design Build",
    "Summit Ridge Remodeling",
    "Harbor & Oak Kitchen and Bath",
    "Cascade Heritage Builders",
    "Evergreen Custom Home Builders",
    "Pinnacle Luxury Renovations",
    "Northgate Mechanical Contractors",      # \bmechanic\b must NOT match
    "Retirement Living Builders LLC",        # \btire\b must NOT match
    "Autumn Ridge Custom Homes",             # \bauto\b must NOT match
    "Automatic Gate & Fence Co",             # \bauto\b must NOT match
    "Carriage House Renovations",            # \bcar\b must NOT match
    "Carlton Bay Remodeling",                # \bcar\b must NOT match
    "Radiance Med Spa",                      # \bradiator\b must NOT match
    "Glow Aesthetics & Wellness",
    "Bellevue Luxury Properties Group",
    "Stonebridge General Contracting",
    "Lakeview Roofing & Exteriors",
    "Brookfield Interior Design Studio",
    "Copperleaf Fine Homebuilding",
]

# ── Off-ICP names that MUST be blocked (ADR-0012 "disqualify on sight") ──────
OFF_ICP_NAMES = [
    "Keith's Auto Repair",                   # the live 2026-07-29 production row
    "Mike's Auto Body",
    "Sunset Automotive Repair",
    "Discount Tire Center",
    "Precision Transmissions",
    "Bay Area Collision Center",
    "Joe's Car Wash",
    "Larry's Muffler Shop",
    "Quick Lube Express",
    "Bob's Towing",
    "Valley Smog Check Station",
    "Hillside Auto Parts",
    "Metro Ford Dealership",
    "Certified Auto Service",
    "Al's Brake & Alignment",
    "Downtown Mechanic Shop",
    "Speedy Oil Change",
]

# ADR-0012 keeps exotic/luxury/classic auto as "opportunistic only", NOT
# excluded. West Coast Exotic Cars is a real, deliberately-retained lead.
OPPORTUNISTIC_NAMES = [
    "West Coast Exotic Cars",
    "Beverly Hills Luxury Motorcars",
    "Classic Car Restorations of Marin",
]


@pytest.mark.parametrize("name", IN_ICP_NAMES)
def test_in_icp_names_are_not_blocked(name):
    """0% false positives. A wrongly-blocked remodeler is a lost prospect."""
    assert off_icp_business_name_reason({"business": name}) == "", (
        f"FALSE POSITIVE: in-ICP business {name!r} was disqualified")


@pytest.mark.parametrize("name", OFF_ICP_NAMES)
def test_off_icp_names_are_blocked(name):
    reason = off_icp_business_name_reason({"business": name})
    assert reason, f"MISS: off-ICP business {name!r} passed the gate"
    assert "ADR-0012" in reason


@pytest.mark.parametrize("name", OPPORTUNISTIC_NAMES)
def test_exotic_and_luxury_auto_stay_opportunistic(name):
    """ADR-0012 exempts exotic/luxury/classic — same carve-out as the vertical leg."""
    assert off_icp_business_name_reason({"business": name}) == ""


def test_signal_is_not_noise():
    """The owner rule: a signal firing near 100% or 0% across real inputs is noise.

    Measured over the full corpus, the name matcher must separate the two
    populations cleanly rather than firing on everything or nothing.
    """
    in_icp_hits = sum(
        bool(off_icp_business_name_reason({"business": n})) for n in IN_ICP_NAMES)
    off_icp_hits = sum(
        bool(off_icp_business_name_reason({"business": n})) for n in OFF_ICP_NAMES)
    assert in_icp_hits == 0, f"{in_icp_hits}/{len(IN_ICP_NAMES)} in-ICP names blocked"
    assert off_icp_hits == len(OFF_ICP_NAMES)


def test_empty_name_is_not_disqualifying():
    """Absence of a name is not evidence of being off-ICP; other rules judge it."""
    assert off_icp_business_name_reason({}) == ""
    assert off_icp_business_name_reason({"business": ""}) == ""
    assert off_icp_business_name_reason({"business": "   "}) == ""


# ── The regression this whole change exists for ─────────────────────────────

def test_production_row_that_slipped_through_is_now_blocked():
    """Keith's Auto Repair, exactly as stored in production on 2026-07-29:
    vertical EMPTY, so the vertical-only gate returned '' and the sweep passed it."""
    lead = {"business": "Keith's Auto Repair", "vertical": ""}

    assert off_icp_vertical_reason(lead) == ""      # the old gate: blind
    assert off_icp_trade_reason(lead)               # the combined gate: catches it


def test_storage_gate_quarantines_the_production_row():
    """End-to-end: the boot hygiene sweep calls validate_lead_for_storage, so
    this is what will actually happen to the row on the next deploy."""
    result = validate_lead_for_storage({
        "business": "Keith's Auto Repair",
        "owner": "Keith Mayou While Others",
        "email": "automan67@aol.com",
        "phone": "+15595550101",
        "vertical": "",
        "status": "Contacted",
    })
    assert result["ok"] is False
    assert any("ADR-0012" in r for r in result["reasons"])


def test_vertical_leg_still_wins_when_both_would_fire():
    """Vertical is checked first, so a labelled row reports the vertical reason."""
    reason = off_icp_trade_reason(
        {"business": "Keith's Auto Repair", "vertical": "Automotive"})
    assert "vertical" in reason


def test_in_icp_lead_with_off_icp_vertical_label_is_still_blocked():
    """The name leg must not accidentally rescue a row the vertical leg rejects."""
    assert off_icp_trade_reason(
        {"business": "Whitestone Custom Homes", "vertical": "auto repair"})
