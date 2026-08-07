"""CSV import must accept licence-registry exports as they actually arrive.

A real CSLB (California Contractors State License Board) export was downloaded
on 2026-08-04 — 236 B-2 Residential Remodeling contractors in Los Angeles
County. Its header row is CamelCase with punctuation:

    LicenseNumber, BusinessType, BusinessName, Address, City, State,
    ZIP Code, County, PhoneNumber, IssueDate, ExpirationDate,
    Classification(s), Status, SuretyCompany, ...

The importer normalised headers by swapping only spaces and dashes for
underscores, so "BusinessName" became "businessname" and never matched the
alias "business_name". The entire import aborted with:

    "No business/company column found in header: [...]"

"PhoneNumber" and "Classification(s)" failed identically — and phone is the
ONLY channel a licence-registry lead can be reached on, since these files
carry no email by statute (B&P Code §27).

These tests exercise the mapping directly rather than end-to-end, so they
prove the fix without needing a database. An earlier end-to-end version failed
on `database is locked` — the connection-pool bug fixed separately in PR #129 —
which would have made this change look dependent on unmerged work when the
mapping itself is entirely independent of it.
"""
import pytest

from app.main import CSV_HEADER_ALIASES, _norm_csv_header, map_csv_headers

# Verbatim header row from the downloaded file.
CSLB_HEADER = [
    "LicenseNumber", "BusinessType", "BusinessName", "Address", "City",
    "State", "ZIP Code", "County", "PhoneNumber", "IssueDate",
    "ExpirationDate", "Classification(s)", "Status", "SuretyCompany",
    "ContractorBondNumber",
]


# ── the regression ──────────────────────────────────────────────────────────

def test_real_cslb_header_row_maps_the_business_column():
    """Before the fix this was absent, and the import aborted outright."""
    m = map_csv_headers(CSLB_HEADER)
    assert m.get("business") == "BusinessName", (
        f"business column not mapped from a real CSLB header: {m}"
    )


def test_real_cslb_header_row_maps_the_phone_column():
    """Phone is the only reachable channel for these leads. Losing it
    silently would be worse than failing loudly."""
    m = map_csv_headers(CSLB_HEADER)
    assert m.get("phone") == "PhoneNumber", f"phone column not mapped: {m}"


def test_classification_maps_to_vertical():
    """Classification(s) IS the trade. California supplies it; Washington's
    registry has no category field at all, which is why a name-regex exists
    there to guess."""
    m = map_csv_headers(CSLB_HEADER)
    assert m.get("vertical") == "Classification(s)", f"vertical not mapped: {m}"


def test_state_is_mapped():
    """Drives owner_finder's registry routing; save_lead upper-cases on write."""
    m = map_csv_headers(CSLB_HEADER)
    assert m.get("state") == "State", f"state not mapped: {m}"


def test_registry_export_has_no_email_column_and_that_is_expected():
    """Not a defect — CSLB withholds email by statute. Pinned so nobody
    'fixes' it later by inventing an address."""
    m = map_csv_headers(CSLB_HEADER)
    assert "email" not in m


# ── the class of bug, not just this instance ────────────────────────────────

@pytest.mark.parametrize("header,label", [
    ("Business Name", "spaces"),
    ("business-name", "dashes"),
    ("business_name", "underscores"),
    ("BusinessName", "CamelCase"),
    ("BUSINESSNAME", "upper"),
    ("  Business_Name  ", "stray whitespace"),
    ("Business.Name", "dots"),
])
def test_every_header_shape_resolves_to_business(header, label):
    assert map_csv_headers([header]).get("business") == header, f"{label} failed"


@pytest.mark.parametrize("header", [
    "PhoneNumber", "Phone Number", "phone-number", "TELEPHONE", "Mobile",
])
def test_every_phone_shape_resolves(header):
    assert map_csv_headers([header]).get("phone") == header


def test_normaliser_strips_punctuation():
    assert _norm_csv_header("Classification(s)") == "classifications"
    assert _norm_csv_header("ZIP Code") == "zipcode"
    assert _norm_csv_header("  Phone-Number ") == "phonenumber"
    assert _norm_csv_header(None) == ""


# ── guards that must NOT be weakened ────────────────────────────────────────

def test_unrecognised_headers_map_to_nothing():
    """Normalising more aggressively must not start matching things it
    shouldn't — an over-eager mapper silently files data in the wrong column."""
    m = map_csv_headers(["LicenseNumber", "IssueDate", "SuretyCompany",
                         "ContractorBondNumber", "Status"])
    assert m == {}, f"unrelated registry columns were mapped: {m}"


def test_bond_and_licence_numbers_are_not_mistaken_for_a_phone():
    m = map_csv_headers(["ContractorBondNumber", "LicenseNumber"])
    assert "phone" not in m


def test_first_alias_wins_when_several_match():
    """Deterministic precedence — 'business' beats 'company' beats 'name'."""
    m = map_csv_headers(["Name", "Company", "Business"])
    assert m["business"] == "Business"


def test_every_alias_is_reachable_after_normalisation():
    """Guards against adding an alias that can never match because the
    normaliser reduces it to a key another alias already claims."""
    for field, names in CSV_HEADER_ALIASES.items():
        for n in names:
            got = map_csv_headers([n]).get(field)
            assert got == n, f"alias {n!r} for {field!r} is unreachable"
