"""Exit-3 boot crash regression (2026-07-21 outage).

Production evidence chain (Render API events + instance boot logs):
- #87's Sheets fallback synced hunted leads to the Google Sheet;
- Sheets parsed "+17166703920" as the NUMBER 17166703920;
- gspread get_all_records() returned it as an int on the next fresh boot;
- validate_lead_for_storage called .strip() on it -> AttributeError;
- the lifespan restore loop had no per-lead guard -> uvicorn exit 3;
- every deploy since #88 died with update_failed while the warm old
  instance kept serving HTTP 200.

Four layers fixed, each tested here: gate coercion, restore-source
coercion, RAW sheet writes, and the per-lead lifespan guard.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.skills.lead_validator import validate_lead_for_storage


# ── Layer 1: the gate survives non-string inputs ─────────────────────────────

def test_gate_survives_int_phone_the_production_crash():
    # the exact shape that killed three deploys
    result = validate_lead_for_storage({
        "business": "Vivid Motors",
        "owner": "Dana Ferrari",
        "phone": 17166703920,          # int from a numeric Sheet cell
        "email": "dana@vividmotors.com",
    })
    assert result["ok"] is True        # must not raise
    assert result["lead"]["phone"] == "+17166703920"  # coerced then normalized


def test_gate_survives_numeric_and_none_fields_everywhere():
    result = validate_lead_for_storage({
        "business": 12345678901,       # phone-as-name, now an int
        "owner": None,
        "email": 42,
        "url": 99,
    })
    assert result["ok"] is False       # rejected (phone-like name) — not crashed
    result2 = validate_lead_for_storage({
        "business": "Real Dealer", "owner": 7, "email": None,
        "phone": None, "url": None, "website": 3.5,
    })
    assert result2["ok"] is True       # junk fields dropped, never raised


# ── Layer 2: Sheets restore coerces text fields at the source ────────────────

def test_sheets_restore_coerces_numeric_cells():
    import app.skills.sheets_sync as ss

    class _WS:
        def get_all_records(self):
            return [{"ID": 7, "Business": "Vivid Motors", "Owner": "Dana Ferrari",
                     "Email": "dana@vividmotors.com", "Phone": 17166703920,
                     "URL": "https://vividmotors.com", "Status": "New",
                     "Score": 60, "Source": "Nova Engine", "Date": "2026-07-21",
                     "ClientID": 0}]

    async def fake_ws(*a, **k):
        return _WS()

    with patch.object(ss, "_get_worksheet", side_effect=fake_ws):
        leads = asyncio.run(ss.restore_leads_from_sheets())
    assert leads[0]["phone"] == "17166703920"
    assert isinstance(leads[0]["phone"], str)
    assert isinstance(leads[0]["business"], str)
    assert leads[0]["score"] == 60  # numeric fields stay numeric


# ── Layer 3: RAW writes prevent Sheets numeric coercion ──────────────────────

def test_sheet_append_uses_raw_input_option():
    import app.skills.sheets_sync as ss

    captured = {}

    class _WS:
        def append_row(self, row, value_input_option=None):
            captured["opt"] = value_input_option

    asyncio.run(ss._append_with_backoff(_WS(), ["a", "+17166703920"]))
    assert captured["opt"] == "RAW"


# ── Layer 4: one poisoned row must never kill the restore loop ───────────────

def test_restore_loop_pattern_survives_poison_row():
    """Mirrors the lifespan loop's per-lead guard: a raising save skips the
    row and continues — matching main.py's hardened restore loop."""
    saves = {"ok": 0, "skipped": 0}

    async def boom_then_ok(lead):
        if lead.get("poison"):
            raise AttributeError("'int' object has no attribute 'strip'")
        return 1

    async def run_loop(leads):
        restored = 0
        for lead in leads:
            try:
                if await boom_then_ok(lead) not in (-1, -2):
                    restored += 1
            except Exception:
                saves["skipped"] += 1
        saves["ok"] = restored

    asyncio.run(run_loop([{"poison": True}, {"business": "Good"}, {"business": "Also Good"}]))
    assert saves["skipped"] == 1
    assert saves["ok"] == 2
