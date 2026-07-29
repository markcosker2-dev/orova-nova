"""Cold email must not go out off-ICP or without a postal address.

Live incident 2026-07-25/26. The outreach lane worked through 51 stored rows all
tagged vertical "Automotive" and sent **48 cold emails** — to google.com, an
Argentine government museum (museo@adolfoalsina.gov.ar), autotrader.com, two
trade publications, and placeholder addresses like name@hotmail.com. Zero
replies, 550 rejections from Microsoft, and sender reputation spent on a segment
ADR-0012 had already ruled out.

Two independent failures made it possible:

1. ADR-0012 says "disqualify on sight: general auto repair, franchised new-car
   dealers" — but that decision lived only in a document. A strategy decision
   that is not encoded is not a control.
2. The CAN-SPAM footer warned-and-sent when BUSINESS_POSTAL_ADDRESS was unset,
   so all 48 shipped without the physical address 15 U.S.C. §7704 requires.
   Every other risky path in this system fails closed; this one failed open.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.skills.lead_validator import (off_icp_vertical_reason,
                                       validate_lead_for_storage)

ADDR = "OROVA, 1 Example St, Manila, PH"


def _lead(**over):
    base = {"business": "Sierra Ridge Builders", "owner": "Maria Santos",
            "email": "maria@sierraridgebuilders.com",
            "website": "https://sierraridgebuilders.com",
            "url": "https://sierraridgebuilders.com",
            "phone": "+14045551234", "vertical": "home remodeling"}
    base.update(over)
    return base


# ─── The exact rows that were emailed ────────────────────────────

@pytest.mark.parametrize("vertical", [
    "Automotive",          # all 51 legacy rows carried this
    "automotive",
    "auto repair",
    "Auto Service",
    "car repair",
    "dealership",
])
def test_the_disqualified_verticals_are_rejected(vertical):
    assert off_icp_vertical_reason({"vertical": vertical}) != ""


def test_storage_gate_quarantines_the_legacy_automotive_rows():
    """These rows are already in production. The boot hygiene sweep re-runs this
    gate, so encoding the rule here is what clears them."""
    out = validate_lead_for_storage(_lead(vertical="Automotive"))
    assert out["ok"] is False
    assert "ADR-0012" in out["reasons"][0]


# ─── ADR-0012 keeps exotic/luxury as opportunistic ───────────────

@pytest.mark.parametrize("vertical", [
    "exotic car dealer",
    "exotic car dealer california",
    "luxury car rental",
    "classic car restoration",
])
def test_exotic_and_luxury_auto_are_not_disqualified(vertical):
    """ADR-0012 demotes these to 'opportunistic only' — NOT excluded. Over-
    blocking here would silently delete a segment the owner chose to keep."""
    assert off_icp_vertical_reason({"vertical": vertical}) == ""


def test_the_target_icp_is_never_blocked():
    for v in ("home remodeling", "custom home builder", "kitchen remodeling",
              "med spa", "luxury real estate"):
        assert off_icp_vertical_reason({"vertical": v}) == "", v


def test_empty_vertical_is_not_disqualified():
    # Absence of a label is not evidence of being off-ICP.
    assert off_icp_vertical_reason({"vertical": ""}) == ""
    assert off_icp_vertical_reason({}) == ""


# ─── Pre-send gates ──────────────────────────────────────────────

def _send(**env):
    from app.skills import agentmail_skill
    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=False)):
        return asyncio.run(agentmail_skill.send_outreach(
            to="owner@sierraridgebuilders.com", subject="Hi", body="Body",
            skip_proofread=True, **env))


def test_send_is_blocked_without_a_postal_address(monkeypatch):
    monkeypatch.delenv("BUSINESS_POSTAL_ADDRESS", raising=False)
    res = _send()
    assert res.get("skipped") is True
    assert "CAN-SPAM" in (res.get("error") or "")


def test_whitespace_postal_address_does_not_count(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", "   ")
    assert _send().get("skipped") is True


def test_a_real_postal_address_unblocks_the_gate(monkeypatch):
    """Guards against the gate blocking everything forever — one env var must
    genuinely release it."""
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", ADDR)
    res = _send()
    assert "CAN-SPAM" not in (res.get("error") or "")


def test_send_is_blocked_for_an_off_icp_lead(monkeypatch):
    """The check that would have stopped all 48 sends."""
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", ADDR)
    from app.skills import agentmail_skill

    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=False)), \
         patch.object(agentmail_skill, "DatabaseManager") as db:
        db.query = AsyncMock(return_value={"vertical": "Automotive"})
        res = asyncio.run(agentmail_skill.send_outreach(
            to="dustin@stateautomotiveutah.com", subject="Hi", body="B",
            skip_proofread=True, lead_id=42))
    assert res.get("skipped") is True
    assert "Off-ICP" in (res.get("error") or "")


def test_icp_lookup_failure_blocks_rather_than_sends(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", ADDR)
    from app.skills import agentmail_skill

    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=False)), \
         patch.object(agentmail_skill, "DatabaseManager") as db:
        db.query = AsyncMock(side_effect=RuntimeError("db down"))
        res = asyncio.run(agentmail_skill.send_outreach(
            to="x@y.com", subject="Hi", body="B", skip_proofread=True, lead_id=42))
    assert res.get("skipped") is True


def test_on_icp_lead_passes_both_gates(monkeypatch):
    monkeypatch.setenv("BUSINESS_POSTAL_ADDRESS", ADDR)
    from app.skills import agentmail_skill

    with patch("app.core.dnc.is_email_suppressed", new=AsyncMock(return_value=False)), \
         patch.object(agentmail_skill, "DatabaseManager") as db:
        db.query = AsyncMock(return_value={"vertical": "home remodeling"})
        res = asyncio.run(agentmail_skill.send_outreach(
            to="owner@sierraridgebuilders.com", subject="Hi", body="B",
            skip_proofread=True, lead_id=7))
    err = res.get("error") or ""
    assert "Off-ICP" not in err and "CAN-SPAM" not in err
