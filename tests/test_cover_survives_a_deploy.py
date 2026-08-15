"""General liability cover must round-trip through the Leads sheet.

Render's free tier has an EPHEMERAL DISK. Every deploy destroys the SQLite
database and boot restores from the Leads tab — `♻️ Restored 14/14 leads from
Google Sheets`. So a field with no sheet column cannot survive a deploy, and
the loss is invisible because the ROW COUNT reconciles perfectly.

`principal_count` survives: the `Principals` column exists (#161).
`insurance_amt` had no column, so it was destroyed on every deploy.

Observed 2026-08-14: a hunt healed LEWCO to 83 with $2M of cover, the next
deploy restored it from the sheet at 76 with none, and 25 leads carrying
verified cover were reduced to zeros. That happened five times in one day while
every row count reconciled and nothing logged an error.

This is the field-level version of the durability bug #160 fixed for rows.
Rows were safe; fields were not.

`Insurance` is a READ-OUT of the registry, like `Principals` — the database is
the canonical owner (CLAUDE.md SSoT) and the sheet is its projection. It is
restored on boot because the restore IS the database at that moment, which is
exactly why it has to carry every field the scorer needs.
"""
import pytest

from app.skills import sheets_sync as ss


def test_insurance_is_a_leads_column():
    assert "Insurance" in ss.WORKSHEET_HEADERS["Leads"], (
        "a field with no sheet column cannot survive a deploy"
    )


@pytest.mark.parametrize("amt,expected", [
    (2_000_000, "2000000"),
    (1_000_000, "1000000"),
    (2_000_000.0, "2000000"),
    ("1000000.0000", "1000000"),   # Socrata returns the amount as a string
    (0, ""),                        # 0 = never looked up, NOT "carries nothing"
    (None, ""),
    ("", ""),
    ("junk", ""),
])
def test_the_cell_renders_cover_without_inventing_it(amt, expected):
    """Blank means unknown. A 0 rendered as "0" would read as "no cover"."""
    assert ss._insurance_cell({"insurance_amt": amt}) == expected


def test_the_row_width_still_matches_the_header():
    written = {}

    class _WS:
        def col_values(self, n):
            return ["Business"]

        def update(self, *a, **k):
            written["row"] = (k.get("values") or a[1])[0]
            return {}

    async def _fake_ws(tab, workbook_name=None):
        return _WS()

    import asyncio
    from unittest.mock import patch
    with patch.object(ss, "_get_worksheet", _fake_ws):
        asyncio.run(ss.sync_lead_to_sheets({
            "business": "NORTHVALE CONTRACTING LLC",
            "principal_count": 1,
            "insurance_amt": 2_000_000,
        }))

    headers = ss.WORKSHEET_HEADERS["Leads"]
    row = written["row"]
    assert len(row) == len(headers), "a row narrower than the header drops columns"
    cell = dict(zip(headers, row))
    assert cell["Insurance"] == "2000000"
    assert cell["Principals"] == "1"


def test_cover_is_restored_from_the_sheet():
    """The half that actually defends against the ephemeral disk."""
    lead = ss._lead_from_sheet_row({
        "Business": "NORTHVALE CONTRACTING LLC",
        "Phone": "+12065551234",
        "State": "WA",
        "Niche": "General",
        "Principals": "1",
        "Insurance": "2000000",
    })
    assert lead["insurance_amt"] == 2_000_000.0, (
        "without this the affordability signal dies on every deploy"
    )
    assert lead["principal_count"] == 1


def test_a_blank_insurance_cell_restores_as_unknown_not_zero_cover():
    lead = ss._lead_from_sheet_row({
        "Business": "NORTHVALE CONTRACTING LLC", "Insurance": "",
    })
    assert lead["insurance_amt"] == 0.0


def test_a_dollar_formatted_cell_still_restores():
    """Sheets may render the number with separators once a human touches it."""
    lead = ss._lead_from_sheet_row({
        "Business": "NORTHVALE CONTRACTING LLC", "Insurance": "$2,000,000",
    })
    assert lead["insurance_amt"] == 2_000_000.0
