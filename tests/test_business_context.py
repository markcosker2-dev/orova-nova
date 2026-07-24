"""Regression tests for the owner-approved business-context edits
(profitability-plan §6, approved 2026-07-10) and their §5.2 operational
counterpart in the hunt rotation.

business_context.json is the machine-readable twin of the vault's
business-model note — these tests pin the approved ICP narrowing, funnel
benchmarks, margin correction, P1-first outreach framing, and the net-new
calling-policy compliance section, plus JSON validity itself (the file is
loaded by the email pipeline, proofreader, and drip templates).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_context() -> dict:
    return json.loads((ROOT / "app" / "core" / "business_context.json").read_text(encoding="utf-8"))


def test_business_context_is_valid_json_with_core_sections():
    ctx = _load_context()
    for section in ("company", "services", "commercial_terms", "sales_funnel",
                    "icp", "email_rules", "outreach", "compliance"):
        assert section in ctx, f"missing section: {section}"


def test_icp_narrowed_to_owner_reachable_verticals():
    icp = _load_context()["icp"]
    primary = " | ".join(icp["primary_verticals"])
    secondary = " | ".join(icp["secondary_verticals"])
    assert "Luxury real estate agents" in primary
    assert "aviation" not in primary.lower()      # moved out of primary
    assert "yacht" not in primary.lower()
    assert "opportunistic only" in secondary       # kept, explicitly deprioritized


def test_funnel_benchmarks_present_with_derivation_pointer():
    benchmarks = _load_context()["sales_funnel"]["funnel_benchmarks_2026"]
    assert "5-8%" in benchmarks["cold_email_reply_rate_target"]
    assert "20-30%" in benchmarks["meeting_to_close_rate_target"]
    assert "profitability-plan" in benchmarks["note"]


def test_margin_target_corrected_with_conservative_floor_retained():
    margin = _load_context()["commercial_terms"]["margin_target"]
    assert "90%+" in margin
    assert "75-80%" in margin  # worst-case floor kept for external conversations


def test_outreach_leads_with_package_1():
    value = _load_context()["outreach"]["initial_email_framework"]["value"]
    assert "Package 1" in value


def test_calling_policy_pins_business_line_only():
    policy = _load_context()["compliance"]["calling_policy"]
    assert "published line" in policy["rule"]
    assert "personal cell" in policy["rule"].lower() or "personal-cell" in policy["rule"].lower()
    assert "dnc.py" in policy["known_gap"]


def test_pricing_unchanged_by_this_edit():
    """§6 touched margin WORDING only — package prices must be untouched."""
    services = _load_context()["services"]
    assert services[0]["price_monthly_usd"] == 4000
    assert services[1]["price_monthly_usd"] == 5000


def test_hunt_rotation_excludes_aviation_and_yachting():
    from app.worker import DEFAULT_HUNT_NICHES
    joined = " | ".join(DEFAULT_HUNT_NICHES)
    assert "jet" not in joined
    assert "yacht" not in joined


def test_hunt_rotation_leads_with_homes_and_demotes_auto():
    """ADR-0012: the rotation is weighted by ENTRY COUNT — worker.py picks with
    random.choice(), uniformly — so composition IS the strategy. Custom homes /
    remodeling leads (one $100K+ job pays 4-7 months of retainer); exotic auto
    drops to opportunistic (a $200K buyer rarely starts on a Meta lead form)."""
    from app.worker import DEFAULT_HUNT_NICHES
    joined = " | ".join(DEFAULT_HUNT_NICHES).lower()
    # every core vertical stays reachable
    for expected in ("custom home builder", "med spa", "luxury real estate agent",
                     "exotic car dealer"):
        assert expected in joined, f"missing rotation niche: {expected}"

    def _count(keys):
        return len([n for n in DEFAULT_HUNT_NICHES if any(k in n.lower() for k in keys)])

    homes = _count(("home", "remodel", "kitchen", "bathroom"))
    auto = _count(("car ", "car'", "auto", "detailing", "car dealer"))
    assert homes >= len(DEFAULT_HUNT_NICHES) / 2, (
        f"homes/remodel must LEAD the rotation, got {homes}/{len(DEFAULT_HUNT_NICHES)}")
    assert auto < homes, f"exotic auto must be opportunistic, got auto={auto} vs homes={homes}"
