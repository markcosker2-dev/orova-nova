"""An owner-entered email must not make the next hunt duplicate the lead.

This is a SEAM test. Two commits that are each correct alone break each other
here, which is why six passing tests on either side missed it:

* `fix(dedup)` made a re-discovery backfill an existing row instead of
  discarding it — but only on the business+state branch, whose SELECT also
  required the STORED row to have no email and no website.
* `feat(sheets)` let the owner type an email into the Leads tab and pulled it
  into the database.

The moment the second one runs, the first one stops matching:

1. WA L&I publishes no email and no website, so the INCOMING lead has neither
   and the email/domain dedup branches never fire.
2. The business+state branch fires, but its SELECT no longer matches, because
   the stored row now holds the owner's address.
3. save_lead falls through to INSERT.
4. `idx_leads_email_client` is PARTIAL (`WHERE trim(email) != ''`), so it does
   not constrain the new row either — its email is ''.

The result is two rows for one business, and it compounds: the duplicate has
no email, so it becomes the match target next round while the emailed original
drifts. The Leads sheet upserts by business name, so the tab keeps showing one
row while the table grows — which is precisely the "24 rows holding 13 distinct
businesses" inflation described in the comment above the code that caused it.

The fix drops the stored-side predicates. The incoming-side guard
(`not email and not domain`) is what stops two different firms merging; the
stored-side clause added nothing and caused this.
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


REGISTRY_LEAD = {
    "business": "LEWCO CONTRACTING",
    "state": "WA",
    "owner_name": "Patrick Lewis",
    "phone": "+12536778727",
    "vertical": "General Contractor",
    "owner_source": "wa_lni",
    "source": "wa_lni",
    "principal_count": 1,
    "email": "",
    "website": "",
    "url": "",
}


def _rows(conn, business="lewco contracting"):
    return conn.execute(
        "SELECT COUNT(*) FROM leads WHERE lower(trim(business)) = ?", (business,)
    ).fetchone()[0]


def test_a_hunt_after_an_owner_typed_email_does_not_duplicate(db):
    """The exact production sequence: hunt, owner types an email, hunt again."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD))
    assert lead_id > 0

    # The owner fills the Email cell in; pull_manual_edits_from_sheets writes it.
    with DatabaseManager.connection() as conn:
        conn.execute(
            "UPDATE leads SET email = ?, email_source = 'owner_manual' WHERE id = ?",
            ("patrick@lewcocontracting.com", lead_id))
        conn.commit()

    # The next hunt re-finds the same business — registries still carry no email.
    again = DatabaseManager.save_lead(dict(REGISTRY_LEAD))

    with DatabaseManager.connection() as conn:
        assert _rows(conn) == 1, (
            "an owner-entered email must not make the business invisible to "
            "dedup — the hunt duplicated the lead"
        )
    assert again == -1, "the re-discovery should dedup, not insert"


def test_the_owners_address_survives_the_re_discovery(db):
    """Dedup must not let a registry row blank out the address he typed."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD))
    with DatabaseManager.connection() as conn:
        conn.execute("UPDATE leads SET email = ? WHERE id = ?",
                     ("patrick@lewcocontracting.com", lead_id))
        conn.commit()

    DatabaseManager.save_lead(dict(REGISTRY_LEAD))

    with DatabaseManager.connection() as conn:
        email = conn.execute(
            "SELECT email FROM leads WHERE id = ?", (lead_id,)).fetchone()[0]
    assert email == "patrick@lewcocontracting.com", (
        "the hand-typed address is the scarcest data in the pipeline"
    )


def test_a_website_only_row_is_also_still_deduped(db):
    """Same seam, other stored-side predicate: a website must not hide the row."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD))
    with DatabaseManager.connection() as conn:
        conn.execute("UPDATE leads SET website = ? WHERE id = ?",
                     ("https://lewcocontracting.com", lead_id))
        conn.commit()

    DatabaseManager.save_lead(dict(REGISTRY_LEAD))

    with DatabaseManager.connection() as conn:
        assert _rows(conn) == 1, "an enriched website must not hide the business"


def test_backfill_still_reaches_a_row_that_now_has_an_email(db):
    """The repair must keep working after the row has been enriched.

    principal_count drives sole-owner status and therefore which pain the call
    opens on. A row that gained an email must still be able to heal.
    """
    thin = dict(REGISTRY_LEAD, principal_count=0)
    lead_id = DatabaseManager.save_lead(thin)
    with DatabaseManager.connection() as conn:
        conn.execute("UPDATE leads SET email = ? WHERE id = ?",
                     ("patrick@lewcocontracting.com", lead_id))
        conn.commit()

    DatabaseManager.save_lead(dict(REGISTRY_LEAD, principal_count=1))

    with DatabaseManager.connection() as conn:
        count = conn.execute(
            "SELECT principal_count FROM leads WHERE id = ?", (lead_id,)).fetchone()[0]
    assert count == 1, "the backfill must still reach an enriched row"


@pytest.mark.parametrize("state_a,state_b", [("WA", "OR")])
def test_the_same_name_in_two_states_stays_two_leads(db, state_a, state_b):
    """Widening the match must not start merging genuinely different firms."""
    DatabaseManager.save_lead(dict(REGISTRY_LEAD, state=state_a))
    DatabaseManager.save_lead(dict(REGISTRY_LEAD, state=state_b))
    with DatabaseManager.connection() as conn:
        assert _rows(conn) == 2, "state is part of the identity"
