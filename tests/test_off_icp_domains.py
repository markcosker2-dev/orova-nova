"""Off-ICP domain classes must be quarantined by the storage gate.

Live 2026-07-26: production held 47 leads that passed every existing check —
an Argentine GOVERNMENT MUSEUM (museo@adolfoalsina.gov.ar), an Argentine news
site, and a NAMED AUTOMOTIVE JOURNALIST at a trade publisher
(lvellequette@crain.com). The outreach gate kept them from being contacted, but
a journalist receiving OROVA cold outreach is a reputational risk, not a
data-quality nit.

The false-positive tests matter more than the true-positive ones: wrongly
quarantining a real contractor costs more than leaving a junk row, so the rule
is deliberately narrow.
"""
import pytest

from app.skills.lead_validator import (off_icp_domain_reason,
                                       validate_lead_for_storage)


def _lead(**over):
    base = {"business": "Sierra Ridge Builders", "owner": "Maria Santos",
            "email": "maria@sierraridgebuilders.com",
            "website": "https://sierraridgebuilders.com",
            "url": "https://sierraridgebuilders.com", "phone": "+14045551234"}
    base.update(over)
    return base


# ─── The exact production rows ───────────────────────────────────

@pytest.mark.parametrize("email,expect", [
    ("museo@adolfoalsina.gov.ar", "government/education"),
    ("lvellequette@crain.com", "publisher/trade-press"),
    ("contacto@infobae.com", "publisher/trade-press"),  # a .com, but a news outlet
    ("info@constructora.com.ar", "non-US domain"),      # the ccTLD branch
    ("content@automotiveworld.com", "publisher/trade-press"),
])
def test_real_production_junk_is_rejected(email, expect):
    reason = off_icp_domain_reason(_lead(email=email, website="", url=""))
    assert reason, f"{email} should have been disqualified"
    assert expect in reason


def test_gate_rejects_the_argentine_government_museum():
    out = validate_lead_for_storage(_lead(email="museo@adolfoalsina.gov.ar",
                                          website="", url=""))
    assert out["ok"] is False
    assert "government/education" in out["reasons"][0]


def test_gate_rejects_a_journalist_at_a_trade_publisher():
    out = validate_lead_for_storage(_lead(email="lvellequette@crain.com",
                                          website="", url=""))
    assert out["ok"] is False


# ─── Caught on the WEBSITE host too, not just email ──────────────

def test_disqualifying_domain_in_the_website_is_caught():
    out = off_icp_domain_reason(_lead(email="", website="https://www.acmecity.gov",
                                      url=""))
    assert "government/education" in out


def test_disqualifying_domain_in_the_url_is_caught():
    out = off_icp_domain_reason(_lead(email="", website="",
                                      url="http://museo.adolfoalsina.gov.ar/pages"))
    assert out != ""


# ─── FALSE POSITIVES — the tests that matter most ────────────────

@pytest.mark.parametrize("domain", [
    "sierraridgebuilders.com",
    "valleyhomebuilders.com",
    "supremeremodelinginc.com",
    "otbaybuilders.net",
    "buildwithus.co",        # Colombia ccTLD, widely used by US businesses
    "remodel.io",            # generic-modern, not a country signal
    "buildright.ai",
    "kitchens.me",
    "govinda-construction.com",   # contains "gov" but is not a .gov
    "education-builders.com",     # contains "edu" but is not a .edu
    "milbrook-homes.com",         # contains "mil" but is not a .mil
])
def test_real_contractor_domains_are_never_quarantined(domain):
    assert off_icp_domain_reason(_lead(email=f"owner@{domain}",
                                       website=f"https://{domain}",
                                       url=f"https://{domain}")) == ""


def test_a_clean_lead_still_passes_the_whole_gate():
    out = validate_lead_for_storage(_lead())
    assert out["ok"] is True


def test_lead_with_no_domains_at_all_is_not_disqualified_by_this_rule():
    # Absence of a domain is not evidence of being off-ICP; other gate rules
    # decide such rows.
    assert off_icp_domain_reason(_lead(email="", website="", url="")) == ""


def test_bare_hostname_without_a_dot_is_ignored():
    assert off_icp_domain_reason(_lead(email="", website="http://localhost",
                                       url="")) == ""


# ─── Hygiene sweep uses the same rule ────────────────────────────

def test_sweep_and_ingest_share_one_rule():
    """lead_hygiene re-runs validate_lead_for_storage over restored rows, so
    adding the rule to the gate is what makes the boot sweep clear these —
    there is deliberately no second copy of the logic to drift."""
    import inspect
    from app.core import lead_hygiene
    src = inspect.getsource(lead_hygiene)
    assert "validate_lead_for_storage" in src
    assert "off_icp_domain_reason" not in src, "rule must live only in the gate"
