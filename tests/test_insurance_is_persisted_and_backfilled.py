"""The affordability signal must survive the hunt that fetched it.

`_attach_wa_insurance` fills `insurance_amt` from the WA L&I insurance dataset
and `_affordability_points` scores on it — worth up to 20 of the ICP score, the
single largest component. But it was never a COLUMN: it lived on the in-flight
dict during the hunt and evaporated at INSERT.

Three consequences, all live before this fix:

1. The signal cannot be shown, sorted on, or audited. Every stored lead reads
   `insurance_amt = None` no matter what the registry said.
2. Re-scoring a STORED lead computes a different number than the one stored,
   because affordability falls back to the neutral 10. `main.py` does exactly
   that to render `icp_reason` in the dashboard, so a $2M lead can display a
   weaker recommendation than its own stored score justifies. CLAUDE.md names
   the server-side recompute as canonical, and a canonical recompute that
   cannot reproduce the stored value is not canonical.
3. `_backfill_registry_fields` could not heal it on re-discovery, so the ten
   production leads carrying `principal_count = 0` would have healed their
   urgency signal and still shown no cover.

The backfill also refreshes `score`. Healing the inputs and leaving the score
stale is half a repair: the score is what the Leads sheet ranks by and what
`get_uncontacted_callable_leads` orders the call budget by
(`ORDER BY COALESCE(score,0) DESC`).
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
    "owner": "Patrick Lewis",
    "phone": "+12536778727",
    "vertical": "General Contractor",
    "owner_source": "wa_lni",
    "source": "wa_lni",
    "principal_count": 1,
    "email": "",
    "website": "",
    "url": "",
}


def _row(conn, lead_id):
    return dict(conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())


def test_insurance_is_stored_on_insert(db):
    """The registry told us; the row must remember."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD, insurance_amt=2_000_000))
    assert _row(db, lead_id)["insurance_amt"] == 2_000_000


def test_a_re_discovery_fills_cover_we_did_not_have(db):
    """The exact shape of the ten production leads: stored thin, re-found rich."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD, principal_count=0))
    assert not _row(db, lead_id)["insurance_amt"]

    DatabaseManager.save_lead(dict(REGISTRY_LEAD, principal_count=1,
                                   insurance_amt=2_000_000))

    healed = _row(db, lead_id)
    assert healed["insurance_amt"] == 2_000_000, "cover must heal on re-discovery"
    assert healed["principal_count"] == 1, "urgency must heal in the same pass"


def test_a_known_cover_is_never_clobbered_by_an_unknown_one(db):
    """Fail-open leaves insurance at 0. That must never erase a real figure."""
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD, insurance_amt=2_000_000))
    DatabaseManager.save_lead(dict(REGISTRY_LEAD, insurance_amt=0))
    assert _row(db, lead_id)["insurance_amt"] == 2_000_000


def test_the_score_is_refreshed_when_the_signals_heal(db):
    """The score is what the sheet ranks by and what the call budget sorts on.

    Healing principal_count and cover while leaving a stale score means the
    repair never reaches the thing that decides who gets called.
    """
    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD, principal_count=0))
    before = _row(db, lead_id)["score"]

    DatabaseManager.save_lead(dict(REGISTRY_LEAD, principal_count=1,
                                   insurance_amt=2_000_000))
    after = _row(db, lead_id)["score"]

    assert after > before, (
        f"a $2M cover is worth 20 affordability points; score stayed {before}"
    )


def test_a_stored_lead_rescores_to_what_was_stored(db):
    """CLAUDE.md: score_lead_icp is the canonical server-side recompute.

    A recompute that cannot reproduce the stored value is not canonical — and
    main.py re-scores stored rows to render the dashboard recommendation.
    """
    from app.skills.lead_validator import score_lead_icp

    lead_id = DatabaseManager.save_lead(dict(REGISTRY_LEAD, insurance_amt=2_000_000))
    stored = _row(db, lead_id)
    assert score_lead_icp(stored)["score"] == stored["score"], (
        "the stored score must be reproducible from the stored row"
    )
