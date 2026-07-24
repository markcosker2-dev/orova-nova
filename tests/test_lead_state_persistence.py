"""Regression tests: lead["state"] must survive to storage.

The bug this locks down: lead_gen_v3._enrich computed result["state"] with a
comment saying it was persisted "so the decision-maker waterfall + reenrich
lane can fire the Secretary-of-State registry later" — but clean_output never
copied it, the leads table had no such column, and save_lead never wrote one.
So every stored lead reached owner_finder._registry_lookup with state="", which
routes to the OpenCorporates branch (GBP 2,250/yr, no key configured).

Net effect before the fix: the CA/WA/OR Secretary-of-State lookups could never
fire on a stored lead no matter which API keys were configured. Each test below
guards one link in that chain.
"""
import asyncio
import sqlite3
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.core._db_base import CANONICAL_SCHEMA_SQL


# ─── Link 3+4: the column exists and save_lead writes it ─────────

@pytest.fixture
def temp_leads_db(monkeypatch):
    """A real SQLite DB built from the canonical schema, wired into
    DatabaseManager.connection so save_lead exercises its real INSERT."""
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


def _lead(**overrides):
    base = {
        "business": "Sierra Ridge Builders",
        "owner": "Maria Santos",
        "email": "maria@sierraridgebuilders.com",
        "phone": "+14045551234",
        "url": "https://sierraridgebuilders.com",
        "website": "https://sierraridgebuilders.com",
        "vertical": "home remodeling",
    }
    base.update(overrides)
    return base


def test_leads_table_has_a_state_column():
    # The canonical schema is the single source of truth; _migrate_columns
    # diffs live DBs against it, so presence here is what makes the column
    # appear on restored Drive snapshots too.
    ref = sqlite3.connect(":memory:")
    ref.executescript(CANONICAL_SCHEMA_SQL)
    cols = {r[1] for r in ref.execute("PRAGMA table_info(leads)").fetchall()}
    ref.close()
    assert "state" in cols


def test_state_survives_a_save_lead_roundtrip(temp_leads_db):
    from app.core.database import DatabaseManager

    lead_id = DatabaseManager.save_lead(_lead(state="CA"))
    assert lead_id > 0, "lead was rejected by the storage gate"

    row = temp_leads_db.execute(
        "SELECT state FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    assert row["state"] == "CA"


def test_state_is_normalized_on_write(temp_leads_db):
    # Ungated ingest (CSV import, Sheets restore) supplies " ca " freely, and
    # _registry_lookup routes on an exact uppercase match — so the stored fact
    # has to be canonical rather than relying on every reader to re-normalize.
    from app.core.database import DatabaseManager

    lead_id = DatabaseManager.save_lead(_lead(state="  ca  "))
    row = temp_leads_db.execute(
        "SELECT state FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    assert row["state"] == "CA"


def test_missing_state_stores_empty_string_not_null(temp_leads_db):
    from app.core.database import DatabaseManager

    lead_id = DatabaseManager.save_lead(_lead())
    row = temp_leads_db.execute(
        "SELECT state FROM leads WHERE id = ?", (lead_id,)
    ).fetchone()
    assert row["state"] == ""


# ─── Link 2: clean_output must carry state out of the hunt ───────

def test_find_leads_v3_output_carries_state():
    """The exact regression: state was computed in _enrich and then dropped by
    clean_output, so it never reached save_lead at all."""
    from app.skills import lead_gen_v3

    discovered = [{
        "business": "Sierra Ridge Builders",
        "url": "https://sierraridgebuilders.com",
        "address": "123 Main St, San Jose, CA 95030",
        "phone": "+14045551234",
    }]

    async def _fake_enrich(url, business_name="", state="", score=0.0):
        return {"owner_name": "Maria Santos", "owner_title": "Owner",
                "email": "maria@sierraridgebuilders.com", "phone": "+14045551234",
                "owner_source": "website", "email_source": "website",
                "email_status": "found", "phone_source": "website",
                "phone_verified": False, "ad_signals": ""}

    with patch.object(lead_gen_v3, "_source_serpapi_maps",
                      new=AsyncMock(return_value=discovered)), \
         patch.object(lead_gen_v3, "enrich_lead_4step", new=_fake_enrich):
        out = asyncio.run(lead_gen_v3.find_leads_v3(count=1, query="kitchen remodelers San Jose"))

    assert out["leads"], "no leads returned"
    assert out["leads"][0]["state"] == "CA"


# ─── Link 5: with state present, routing reaches the CA registry ──

def test_registry_lookup_routes_ca_to_the_ca_registry():
    """The payoff. With state='CA' the lookup must reach _ca_registry_lookup —
    the CALICO-backed source — and must NOT fall through to OpenCorporates."""
    from app.skills import owner_finder

    ca_hit = {"owner": "Maria Santos", "title": "CEO",
              "source": "ca_registry", "confidence": 0.9}
    ca = AsyncMock(return_value=ca_hit)
    oc = AsyncMock(return_value=dict(owner_finder._EMPTY))

    with patch.object(owner_finder, "_ca_registry_lookup", new=ca), \
         patch.object(owner_finder, "_opencorporates_lookup", new=oc):
        result = asyncio.run(owner_finder._registry_lookup("Sierra Ridge Builders", "CA"))

    ca.assert_awaited_once()
    oc.assert_not_awaited()
    assert result["source"] == "ca_registry"


def test_registry_lookup_is_case_insensitive_on_state():
    from app.skills import owner_finder

    ca = AsyncMock(return_value={"owner": "Maria Santos", "title": "",
                                 "source": "ca_registry", "confidence": 0.9})
    with patch.object(owner_finder, "_ca_registry_lookup", new=ca):
        asyncio.run(owner_finder._registry_lookup("Sierra Ridge Builders", "ca"))
    ca.assert_awaited_once()


def test_empty_state_still_falls_through_to_opencorporates():
    """Documents the pre-fix behaviour that made the bug invisible: an empty
    state is not an error, it just silently routes to the dead branch. This is
    why the missing column produced no logs and no exception."""
    from app.skills import owner_finder

    oc = AsyncMock(return_value=dict(owner_finder._EMPTY))
    ca = AsyncMock(return_value=dict(owner_finder._EMPTY))

    with patch.object(owner_finder, "_opencorporates_lookup", new=oc), \
         patch.object(owner_finder, "_ca_registry_lookup", new=ca):
        asyncio.run(owner_finder._registry_lookup("Sierra Ridge Builders", ""))

    oc.assert_awaited_once()
    ca.assert_not_awaited()
