"""A re-discovery must heal the row it matched, whichever key matched it.

`save_lead` deduplicates on three keys in order: email, then website domain,
then business+state. Only the LAST one backfilled. The first two returned -1
and healed nothing, so a lead matched by email or domain was frozen at whatever
it held the first time it was seen.

That is not a rare path. The hunt GUESSES an email for some registry leads, and
a guessed address is enough to make the email branch win. Observed live
2026-08-14 — five leads re-discovered, three healed, and the two that did not
are exactly the two whose notes read `| Email guess`:

    SCHULTE CONSTRUCTION LLC   email=''                              healed
    R G N CONSTRUCTION LLC     email=''                              healed
    LEWCO CONTRACTING          (registry sent none)                  healed
    FATBOY CONSTRUCTION INC    email='michael@fatboyconstruction.com' FROZEN
    J L REMODELING INC         email='jeffery@jlremodeling.com'       FROZEN

Both were scored 78 in flight — the registry knew their principal count and
their cover — and both remain stored at 81 with no signals at all, because the
branch that matched them had no repair in it.

The rule is unchanged and applies on every branch: fill a gap, never overwrite
a known value with an unknown one.
"""
import sqlite3
from contextlib import contextmanager

import pytest

from app.core._db_base import CANONICAL_SCHEMA_SQL
from app.core.database import DatabaseManager


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CANONICAL_SCHEMA_SQL)

    @contextmanager
    def _fake_connection(cls=None):
        yield conn

    monkeypatch.setattr(DatabaseManager, "connection", _fake_connection)
    yield conn
    conn.close()


BASE = {
    "business": "FATBOY CONSTRUCTION INC",
    "state": "WA",
    "owner": "Michael Boyle",
    "owner_name": "Michael Boyle",
    "phone": "+12065550101",
    "owner_source": "wa_lni",
    "source": "wa_lni",
    "vertical": "General",
    "url": "",
    "website": "",
}


def _row(conn, lead_id):
    return dict(conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


def test_a_lead_matched_by_email_still_heals(db):
    """The live case: a guessed address routed the lead to the branch with no repair."""
    thin = dict(BASE, email="michael@fatboyconstruction.com",
                principal_count=0, insurance_amt=0)
    lead_id = DatabaseManager.save_lead(thin)
    assert lead_id > 0

    rich = dict(BASE, email="michael@fatboyconstruction.com",
                principal_count=1, insurance_amt=2_000_000)
    assert DatabaseManager.save_lead(rich) == -1, "still a duplicate"

    healed = _row(db, lead_id)
    assert healed["principal_count"] == 1, "sole-owner status must heal here too"
    assert healed["insurance_amt"] == 2_000_000, "cover must heal here too"


def test_a_lead_matched_by_domain_still_heals(db):
    thin = dict(BASE, business="J L REMODELING INC", email="",
                url="https://jlremodeling.com", website="https://jlremodeling.com",
                principal_count=0, insurance_amt=0)
    lead_id = DatabaseManager.save_lead(thin)
    assert lead_id > 0

    rich = dict(thin, principal_count=1, insurance_amt=2_000_000)
    assert DatabaseManager.save_lead(rich) == -1

    healed = _row(db, lead_id)
    assert healed["principal_count"] == 1
    assert healed["insurance_amt"] == 2_000_000


def test_the_score_is_refreshed_on_the_email_branch_too(db):
    thin = dict(BASE, email="michael@fatboyconstruction.com",
                principal_count=0, insurance_amt=0)
    lead_id = DatabaseManager.save_lead(thin)
    before = _row(db, lead_id)["score"]

    DatabaseManager.save_lead(dict(BASE, email="michael@fatboyconstruction.com",
                                   principal_count=1, insurance_amt=2_000_000))
    assert _row(db, lead_id)["score"] > before, (
        "the score is what the sheet ranks by and what the call budget sorts on"
    )


def test_no_branch_downgrades_a_known_value(db):
    """Fail-open leaves 0. That must never erase a figure we already hold."""
    rich = dict(BASE, email="michael@fatboyconstruction.com",
                principal_count=1, insurance_amt=2_000_000)
    lead_id = DatabaseManager.save_lead(rich)

    DatabaseManager.save_lead(dict(BASE, email="michael@fatboyconstruction.com",
                                   principal_count=0, insurance_amt=0))

    healed = _row(db, lead_id)
    assert healed["principal_count"] == 1
    assert healed["insurance_amt"] == 2_000_000


def test_a_registry_trade_still_wins_on_the_email_branch(db):
    """The stored vertical is usually the search query; the registry beats it."""
    thin = dict(BASE, email="michael@fatboyconstruction.com", vertical="custom home builder",
                owner_source="", source="serp")
    lead_id = DatabaseManager.save_lead(thin)
    assert _row(db, lead_id)["vertical"] == "custom home builder"

    DatabaseManager.save_lead(dict(BASE, email="michael@fatboyconstruction.com",
                                   vertical="General", owner_source="wa_lni",
                                   source="wa_lni", principal_count=1))
    assert _row(db, lead_id)["vertical"] == "General"
