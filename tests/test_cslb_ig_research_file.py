"""The CSLB -> Instagram-research join (scripts/cslb_ig_research_file.py).

## Why this file matters more than a normal script test

The output of this script is handed to a human who then sends a personal
Instagram DM addressing someone by their first name. Every failure mode here is
a message to a real contractor that is wrong in a way they will notice:

  · a reversed name  -> "Hi Davis" when he is Dana Davis
  · a stale title    -> DMing someone recorded as Deceased
  · a bad ICP match  -> pitching Meta ads to an auto body shop
  · a wrong owner    -> naming a different company's principal

So the assertions below are about correctness of *identity*, not shape.
"""
import csv
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from cslb_ig_research_file import (  # noqa: E402
    build, parse_cslb_name, title_rank, classes_of, pick,
)


# ── names: CSLB is fixed-width LAST/FIRST/MIDDLE ────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("DAVIS                    DANA         MICHAEL", ("Dana", "Davis", "Dana Davis")),
    ("MC CURDY                 KENNETH      JAMES",   ("Kenneth", "Mc Curdy", "Kenneth Mc Curdy")),
    ("OBRIEN                   PATRICK",              ("Patrick", "Obrien", "Patrick Obrien")),
    ("SINGLENAME",                                    ("", "Singlename", "Singlename")),
    ("   ",                                           ("", "", "")),
    ("",                                              ("", "", "")),
])
def test_parse_cslb_name(raw, expected):
    assert parse_cslb_name(raw) == expected


def test_the_surname_is_never_used_as_the_given_name():
    """The specific trap: owner_finder._person_from_principal reads a
    comma-less string as FIRST..LAST and would return 'Davis Michael' here.

    A DM opening 'Hi Davis' to a man called Dana is the exact failure this
    parser exists to prevent, so it gets its own named test.
    """
    first, last, _ = parse_cslb_name("DAVIS                    DANA         MICHAEL")
    assert first == "Dana"
    assert last == "Davis"


# ── titles ──────────────────────────────────────────────────────────────────

def test_deceased_is_excluded_outright():
    assert title_rank("Deceased") == 99


def test_sole_owner_outranks_everything():
    assert title_rank("Sole Owner") < title_rank("Officer")
    assert title_rank("Sole Owner") < title_rank("Responsible Managing Employee")


def test_an_employee_ranks_below_an_owner():
    assert title_rank("Responsible Managing Employee") > title_rank("Sole Owner")


def test_pipe_separated_titles_take_the_best():
    assert title_rank("Officer| Sole Owner") == title_rank("Sole Owner")


# ── helpers ─────────────────────────────────────────────────────────────────

def test_classes_of_splits_on_every_separator():
    assert classes_of("B-2|B") == {"B-2", "B"}
    assert classes_of("B-2, C-10") == {"B-2", "C-10"}
    assert classes_of("") == set()


def test_pick_finds_columns_whatever_the_header_is_called():
    """The Master file is a government export whose headers have changed before."""
    for header in ["LIC-NO", "LicenseNo", "License Number", "licence_no"]:
        assert pick([header], r"LIC[-_ ]?NO", r"licen[cs]e\s*[-_#]?\s*(no|num|number)?") == header


# ── the join, end to end ────────────────────────────────────────────────────

PERSONNEL = [
    # lic, Name-TP, Name (fixed-width), EMP-Titl-CDE
    ("1001", "Principal", "ALVAREZ            MARIA        LUZ",   "Sole Owner"),
    ("1001", "Principal", "ALVAREZ            JOSE",               "Officer"),
    ("1002", "Principal", "CHEN               WEI",                "Chief Executive Officer/President"),
    ("1003", "Principal", "GRAVES             HENRY",              "Deceased"),
    ("1004", "Principal", "OKONKWO            ADAEZE      N",      "Sole Owner"),
    ("1005", "Principal", "SMITH              JOHN",               "Sole Owner"),
]

MASTER = [
    # on-ICP, B-2 + design-build name -> should rank FIRST
    dict(LicenseNo="1004", BusinessName="ADAEZE CUSTOM HOMES", MailingAddress="1 A St",
         City="PASADENA", County="LOS ANGELES", ZIPCode="91101", BusinessPhone="(626) 555-0101",
         Classifications="B-2", BusinessType="Sole Ownership", PrimaryStatus="ACTIVE"),
    # on-ICP, plain name -> survives, ranks lower
    dict(LicenseNo="1001", BusinessName="ALVAREZ CONSTRUCTION", MailingAddress="2 B St",
         City="PASADENA", County="LOS ANGELES", ZIPCode="91104", BusinessPhone="6265550102",
         Classifications="B", BusinessType="LLC", PrimaryStatus="ACTIVE"),
    # principal is Deceased -> must be dropped, never DMed
    dict(LicenseNo="1003", BusinessName="GRAVES FINE HOMES", MailingAddress="3 C St",
         City="PASADENA", County="LOS ANGELES", ZIPCode="91105", BusinessPhone="6265550103",
         Classifications="B-2", BusinessType="Sole Ownership", PrimaryStatus="ACTIVE"),
    # off-ICP by business name -> the shared ADR-0012 gate must drop it
    dict(LicenseNo="1002", BusinessName="WESTSIDE AUTO REPAIR & COLLISION", MailingAddress="4 D St",
         City="LOS ANGELES", County="LOS ANGELES", ZIPCode="90001", BusinessPhone="2135550104",
         Classifications="B", BusinessType="Corporation", PrimaryStatus="ACTIVE"),
    # no principal in the personnel file -> dropped
    dict(LicenseNo="9999", BusinessName="GHOST BUILDERS", MailingAddress="5 E St",
         City="PASADENA", County="LOS ANGELES", ZIPCode="91101", BusinessPhone="6265550105",
         Classifications="B-2", BusinessType="LLC", PrimaryStatus="ACTIVE"),
    # unusable phone -> dropped (a DM/call target with no number is not a lead)
    dict(LicenseNo="1005", BusinessName="SMITH CUSTOM BUILD", MailingAddress="6 F St",
         City="GLENDALE", County="LOS ANGELES", ZIPCode="91201", BusinessPhone="n/a",
         Classifications="B-2", BusinessType="Sole Ownership", PrimaryStatus="ACTIVE"),
]


@pytest.fixture
def files(tmp_path):
    p = tmp_path / "PersonnelData.csv"
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["LIC-NO", "Name-TP", "Name", "EMP-Titl-CDE"])
        w.writerows(PERSONNEL)
    m = tmp_path / "MasterData.csv"
    with io.open(m, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(MASTER[0]))
        w.writeheader()
        w.writerows(MASTER)
    return str(m), str(p), str(tmp_path / "out.csv")


def test_join_keeps_only_reachable_on_icp_rows(files):
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    names = [r["BusinessName"] for r in rows]
    assert "ADAEZE CUSTOM HOMES" in names
    assert "ALVAREZ CONSTRUCTION" in names
    assert "GRAVES FINE HOMES" not in names, "a Deceased principal reached the DM list"
    assert "WESTSIDE AUTO REPAIR & COLLISION" not in names, "off-ICP survived the shared gate"
    assert "GHOST BUILDERS" not in names, "a licence with no principal produced a row"
    assert "SMITH CUSTOM BUILD" not in names, "an unusable phone produced a row"
    assert len(rows) == 2


def test_owner_name_is_prefilled_and_correct(files):
    """The whole point: the research task must stop paying quota for this."""
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    by = {r["BusinessName"]: r for r in rows}
    assert by["ADAEZE CUSTOM HOMES"]["owner_name"] == "Adaeze Okonkwo"
    assert by["ADAEZE CUSTOM HOMES"]["owner_first"] == "Adaeze"
    assert by["ADAEZE CUSTOM HOMES"]["owner_source"] == "cslb_personnel"


def test_the_best_ranked_principal_wins_when_a_licence_has_several(files):
    """Licence 1001 has a Sole Owner AND an Officer. The owner must win."""
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    row = next(r for r in rows if r["BusinessName"] == "ALVAREZ CONSTRUCTION")
    assert row["owner_name"] == "Maria Alvarez"
    assert row["owner_title"] == "Sole Owner"


def test_b2_and_design_build_names_rank_first(files):
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    assert rows[0]["BusinessName"] == "ADAEZE CUSTOM HOMES"


def test_phone_is_normalised_to_e164(files):
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    assert all(r["PhoneNumber"].startswith("+1") and len(r["PhoneNumber"]) == 12 for r in rows)


def test_county_filter_excludes_other_counties(files):
    master, personnel, out = files
    assert build(master, personnel, "ORANGE", 50, out, per_city_cap=0) == []


def test_per_city_cap_spreads_the_list(files):
    """The task asks for spread explicitly — 30 DMs into one suburb reads as spam."""
    master, personnel, out = files
    rows = build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=1)
    cities = [r["City"] for r in rows]
    assert len(cities) == len(set(cities))


def test_output_file_is_written_with_the_expected_header(files):
    master, personnel, out = files
    build(master, personnel, "LOS ANGELES", 50, out, per_city_cap=0)
    with io.open(out, encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    for col in ("BusinessName", "City", "PhoneNumber", "owner_name", "instagram_handle"):
        assert col in header


def test_a_broken_master_header_fails_loudly(tmp_path, files):
    """An empty output that looks like 'no matches' would be the worst outcome.

    A government export that renames a column must stop the run, not silently
    produce a file Mark trusts.
    """
    _, personnel, out = files
    bad = tmp_path / "bad.csv"
    with io.open(bad, "w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(["col_a", "col_b", "col_c"])
    with pytest.raises(SystemExit) as e:
        build(str(bad), personnel, "", 10, out, per_city_cap=0)
    assert "master file: missing" in str(e.value)
