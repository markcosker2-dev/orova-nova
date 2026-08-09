"""The Leads sheet must carry niche, state and sole-owner status.

Added 2026-08-09 at the owner's request ("can you fix up the google sheet so
that it has the niche website and email if possible as are they sole owners?").

Two of these are not cosmetic:

* **State** — the storage gate dedups licence-registry leads on
  business + state, but the sheet never carried state, so a restored lead came
  back with `state=''` and failed to match the same business found by a hunt
  (`state='WA'`). ACCRETE CONSTRUCTION LLC was stored twice exactly that way.
* **SoleOwner** — `business_context.json` lists "No payroll (solo operator) -
  no urgency" as a kill signal, and ADR-0012 qualifies on whether ONE extra
  closed deal covers the retainer. This column is what makes that judgement
  possible before dialling.

`Website` had a column all along and was still being dropped on every restore.
"""
import asyncio
from unittest.mock import patch

import pytest

from app.skills import sheets_sync as ss


def test_column_letter_maths():
    assert ss._col_letter(1) == "A"
    assert ss._col_letter(12) == "L"
    assert ss._col_letter(16) == "P"
    assert ss._col_letter(26) == "Z"
    assert ss._col_letter(27) == "AA"


def test_the_write_range_is_not_pinned_to_twelve_columns():
    """':L' was hardcoded. Any new column would land outside the range and
    be silently dropped — the failure mode this whole session kept hitting."""
    seen = {}

    class _WS:
        def update(self, *a, **k):
            seen["range"] = k.get("range_name") or (a[0] if a else "")
            return {}

    row = [""] * len(ss.WORKSHEET_HEADERS["Leads"])
    asyncio.run(ss._update_with_backoff(_WS(), 5, row))
    expected_col = ss._col_letter(len(row))
    assert seen["range"] == f"A5:{expected_col}5", seen["range"]
    assert not seen["range"].endswith("L5") or expected_col == "L"


def test_unknown_principal_count_is_never_a_guess():
    """0 means "never looked up", and 58.9% of WA contractors are genuinely
    single-principal — so defaulting either way would be wrong at scale.

    The Principals cell stays blank (a count we do not have), but SoleOwner now
    spells out "Unknown" rather than leaving a blank to interpret: it is the
    column the owner reads to predict what the call will do, and blank reads as
    missing data instead of "the script will ask".
    """
    assert ss._principals_cell({}) == ""
    assert ss._principals_cell({"principal_count": 0}) == ""
    assert ss._sole_owner_cell({}) == "Unknown"
    assert ss._sole_owner_cell({"principal_count": 0}) == "Unknown"


def test_sole_owner_is_derived_from_principals():
    assert ss._sole_owner_cell({"principal_count": 1}) == "Yes"
    assert ss._sole_owner_cell({"principal_count": 3}) == "No"
    assert ss._principals_cell({"principal_count": 6}) == "6"


def test_a_junk_principal_value_never_raises():
    """Sheets returns strings, ints and blanks interchangeably."""
    for bad in ("", "n/a", None, [], {}):
        assert ss._principals_cell({"principal_count": bad}) == ""
        assert ss._sole_owner_cell({"principal_count": bad}) == "Unknown"


def test_the_row_carries_niche_state_and_sole_owner():
    """End-to-end through the real sync, against the real header order."""
    written = {}

    class _WS:
        def col_values(self, n):
            return ["Business"]          # header only -> next row is 2

        def update(self, *a, **k):
            written["row"] = (k.get("values") or a[1])[0]
            return {}

    async def _fake_ws(tab, workbook_name=None):
        return _WS()

    lead = {"business": "PEAK BUILDERS INC", "owner": "Jeffrey Rudd",
            "phone": "+12062323554", "state": "wa", "vertical": "General",
            "principal_count": 6, "website": "https://peakbuilders.example"}
    with patch.object(ss, "_get_worksheet", _fake_ws):
        res = asyncio.run(ss.sync_lead_to_sheets(lead))
    assert res["ok"] is True

    headers = ss.WORKSHEET_HEADERS["Leads"]
    row = written["row"]
    assert len(row) == len(headers), "row width must match the header row"
    cell = dict(zip(headers, row))
    assert cell["Niche"] == "General"
    assert cell["State"] == "WA", "state must be normalised on write"
    assert cell["Principals"] == "6"
    assert cell["SoleOwner"] == "No"
    assert cell["Website"] == "https://peakbuilders.example"


def test_restore_round_trips_state_website_and_principals():
    """A backup that loses fields is only half a backup."""
    records = [{
        "ID": 1, "Business": "ACCRETE CONSTRUCTION LLC", "Owner": "Michael Cholerton",
        "Email": "", "Phone": "+12532863900", "Website": "https://accrete.example",
        "URL": "", "Status": "New", "Score": 45, "Source": "wa_lni_licences",
        "Date": "2026-08-09", "Notes": "", "Niche": "General", "State": "wa",
        "Principals": 5, "SoleOwner": "No",
    }]

    class _WS:
        def get_all_records(self):
            return records

    async def _fake_ws(tab, workbook_name=None):
        return _WS()

    with patch.object(ss, "_get_worksheet", _fake_ws):
        leads = asyncio.run(ss.restore_leads_from_sheets())

    assert len(leads) == 1
    l = leads[0]
    assert l["state"] == "WA", "state must round-trip — its absence duplicated ACCRETE"
    assert l["website"] == "https://accrete.example", "website was silently dropped before"
    assert l["vertical"] == "General"
    assert l["principal_count"] == 5
