"""The sheet and the dialer must never disagree about sole-owner status.

The Leads sheet's SoleOwner column is how the owner predicts what a call will
do. The Retell script opens on a different pain depending on crew status —
payroll pressure for a firm with staff, his own calendar for a one-man
operation. If the sheet renders one answer while the dialer sends another, the
column is worse than absent: it is trusted.

Both therefore derive from ONE function, `lead_validator.crew_status`
(CLAUDE.md single-source-of-truth rule). These tests pin that they agree for
every input, including the junk shapes a Google Sheet round-trip produces —
gspread returns ints for numeric cells, blanks for empty ones, and strings for
anything it cannot parse.
"""
import pytest

from app.skills.lead_validator import (CREW_HAS_CREW, CREW_SOLO, CREW_UNKNOWN,
                                       crew_status)
from app.skills.outbound_dialer import _crew_status
from app.skills.sheets_sync import _sole_owner_cell

# raw principal_count -> (canonical status, sheet label)
CASES = [
    (1, CREW_SOLO, "Yes"),
    (2, CREW_HAS_CREW, "No"),
    (6, CREW_HAS_CREW, "No"),
    (0, CREW_UNKNOWN, "Unknown"),
    (None, CREW_UNKNOWN, "Unknown"),
    ("", CREW_UNKNOWN, "Unknown"),
    ("n/a", CREW_UNKNOWN, "Unknown"),
    ("3", CREW_HAS_CREW, "No"),      # Sheets hands back strings
    ("1", CREW_SOLO, "Yes"),
    (-2, CREW_UNKNOWN, "Unknown"),   # nonsense is never "has crew"
]


@pytest.mark.parametrize("raw,expected,label", CASES)
def test_dialer_and_sheet_agree(raw, expected, label):
    assert crew_status(raw) == expected
    assert _crew_status(raw) == expected, "dialer diverged from canonical"
    assert _sole_owner_cell({"principal_count": raw}) == label, "sheet diverged"


@pytest.mark.parametrize("raw,expected,label", CASES)
def test_the_sheet_label_always_maps_back_to_what_retell_gets(raw, expected, label):
    """Round-trip: the label the owner reads must imply the dialer's value."""
    back = {"Yes": CREW_SOLO, "No": CREW_HAS_CREW, "Unknown": CREW_UNKNOWN}[label]
    assert back == _crew_status(raw), (
        f"sheet shows {label!r} but Retell receives {_crew_status(raw)!r}")


def test_crew_status_accepts_a_lead_dict_or_a_count():
    assert crew_status({"principal_count": 1}) == CREW_SOLO
    assert crew_status(1) == CREW_SOLO
    assert crew_status({}) == CREW_UNKNOWN


def test_unknown_is_never_silently_a_lean():
    """58.9% of WA contractors are single-principal — any default is a coin
    flip that opens the call on the wrong pain."""
    assert crew_status(None) == CREW_UNKNOWN
    assert crew_status(None) not in (CREW_SOLO, CREW_HAS_CREW)


def test_the_sheet_never_shows_a_blank_for_unknown():
    """A blank cell reads as missing data; the useful fact is that we do not
    know and the script will ask on the call."""
    assert _sole_owner_cell({}) == "Unknown"
    assert _sole_owner_cell({"principal_count": 0}) == "Unknown"
