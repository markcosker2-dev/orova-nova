"""Licence-registry leads must have a dedup key.

## The bug this locks down (production, 2026-08-09)

`save_lead` deduplicated on email, then on website domain. Licence-registry
rows — WA L&I, OR CCB, CA CSLB, which have been the PRIMARY lead source since
ADR-0014 — carry none of the three:

    business: "HAWK CONSTRUCTION"   email: ""   url: ""   website: ""

So they had no dedup key at all, and every hunt re-inserted the same
contractors. `/api/leads` that morning: **24 rows, 13 distinct businesses**,
with FOREVER QUALITY CONSTRUCT LLC stored four separate times.

The damage was not just a bloated table. The Leads sheet upserts by business
name, so it correctly held ~13 rows while the database showed 24 — and every
comparison between them read as a catastrophic backup failure. Weeks of
"durability is broken, leads keep vanishing" was substantially this bug
reflected in a mirror.

The fallback key is deliberately narrow: business + state, and ONLY when email
and domain are both absent. Two real firms can share a name, and when either
has a domain or an email the stronger checks already told them apart. Merging
on name there would delete real leads — a much worse outcome than a duplicate.
"""
import sqlite3
from contextlib import contextmanager

import pytest

from app.core._db_base import CANONICAL_SCHEMA_SQL


@pytest.fixture
def temp_leads_db(monkeypatch):
    """Real SQLite from the canonical schema, so save_lead runs its real SQL."""
    from app.core.database import DatabaseManager

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CANONICAL_SCHEMA_SQL)

    @contextmanager
    def _fake_connection(cls=None):
        yield conn

    monkeypatch.setattr(DatabaseManager, "connection", _fake_connection)
    yield conn
    conn.close()


def _registry_lead(business="HAWK CONSTRUCTION", state="WA", **over):
    """A lead shaped exactly like WA L&I / OR CCB output: no email, no domain."""
    lead = {
        "business": business,
        "owner": "Kulwinder Gakhal",
        "owner_title": "Licence Principal",
        "owner_source": "wa_lni",
        "phone": "+12065782277",
        "phone_source": "wa_lni",
        "phone_verified": 1,
        "owner_confidence": 90,
        "state": state,
        "email": "",
        "url": "",
        "website": "",
        "notes": "WA L&I licence HAWKCC*747ND",
    }
    lead.update(over)
    return lead


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]


def test_the_same_registry_contractor_is_not_stored_twice(temp_leads_db):
    """The exact production shape: re-running a hunt must not re-insert."""
    from app.core.database import DatabaseManager

    first = DatabaseManager.save_lead(_registry_lead())
    second = DatabaseManager.save_lead(_registry_lead())

    assert first > 0, "the first save must succeed"
    assert second == -1, "the second save must be recognised as a duplicate"
    assert _count(temp_leads_db) == 1


def test_four_hunts_still_leave_one_row(temp_leads_db):
    """FOREVER QUALITY CONSTRUCT LLC was stored 4x in production."""
    from app.core.database import DatabaseManager

    for _ in range(4):
        DatabaseManager.save_lead(_registry_lead(business="FOREVER QUALITY CONSTRUCT LLC"))
    assert _count(temp_leads_db) == 1


def test_dedup_is_case_and_whitespace_insensitive(temp_leads_db):
    """Registry feeds are not consistent about casing or padding."""
    from app.core.database import DatabaseManager

    DatabaseManager.save_lead(_registry_lead(business="TA BUILDERS LLC"))
    DatabaseManager.save_lead(_registry_lead(business="  ta builders llc  "))
    assert _count(temp_leads_db) == 1


def test_the_same_name_in_a_different_state_is_a_different_business(temp_leads_db):
    """"Golan Construction" in WA and in OR are not the same firm."""
    from app.core.database import DatabaseManager

    DatabaseManager.save_lead(_registry_lead(business="GOLAN CONSTRUCTION LLC", state="WA"))
    DatabaseManager.save_lead(_registry_lead(business="GOLAN CONSTRUCTION LLC", state="OR"))
    assert _count(temp_leads_db) == 2, "state must keep same-named firms apart"


def test_distinct_businesses_are_all_still_stored(temp_leads_db):
    """The fix must not become a blunt instrument that swallows real leads."""
    from app.core.database import DatabaseManager

    for name in ("HAWK CONSTRUCTION", "TA BUILDERS LLC", "GOLAN CONSTRUCTION LLC",
                 "GOLDENKEY REMODELING LLC", "FOREVER QUALITY CONSTRUCT LLC"):
        DatabaseManager.save_lead(_registry_lead(business=name))
    assert _count(temp_leads_db) == 5, "the 5 real WA contractors must all survive"


def test_same_name_but_a_real_domain_is_never_merged_away(temp_leads_db):
    """The narrow gate that stops this fix from destroying data.

    Two firms can share a name. When one has a website the domain check already
    distinguishes them, so the name fallback must stand down — losing a real
    lead is far worse than keeping a duplicate.
    """
    from app.core.database import DatabaseManager

    a = DatabaseManager.save_lead(_registry_lead(business="SUMMIT REMODELING"))
    b = DatabaseManager.save_lead(
        _registry_lead(business="SUMMIT REMODELING", website="https://summit-remodel-wa.com"))

    assert a > 0 and b > 0, "a lead carrying a domain must not be merged by name"
    assert _count(temp_leads_db) == 2


def test_a_lead_with_no_business_name_is_unaffected(temp_leads_db):
    """No name means the gate rejects it anyway — the fallback must not crash."""
    from app.core.database import DatabaseManager

    assert DatabaseManager.save_lead(_registry_lead(business="")) == -2
