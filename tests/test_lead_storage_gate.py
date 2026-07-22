"""Lead storage gate + hygiene sweep (Phase 0 data integrity, 2026-07-20).

Live production (verified via /api/leads) held exactly two leads, both junk:
1. The repo's own make_blueprint/sample_webhook_payload.json fixture, stored
   verbatim: "Acme Remodeling Co" / "Jane Doe" / jane.doe@acme.com /
   +1-555-123-4567 / score 85 taken straight from the payload.
2. A row with NO business name whose phone (14047334400) rendered in the
   Mission Control "Business" column.

Both entered through the ungated Sheets restore path. The gate now lives in
save_lead (single insert choke point); the boot sweep quarantines what the
Drive/Sheets restores bring back.
"""
import sqlite3
import asyncio

import pytest

from app.skills.lead_validator import (
    validate_lead_for_storage,
    clean_phone_for_storage,
    clean_email_for_storage,
    clean_url_for_storage,
    is_placeholder_phone,
    contact_confidence,
    outreach_ready,
    _looks_like_phone,
)

# The two rows that were live in production on 2026-07-20.
PROD_FIXTURE_ACME = {
    "business": "Acme Remodeling Co", "owner": "Jane Doe",
    "email": "jane.doe@acme.com", "phone": "+1-555-123-4567",
    "url": "https://acme.example.com/contact", "status": "new", "score": 85,
}
PROD_FIXTURE_NO_NAME = {
    "business": "", "owner": "Member Circles",
    "email": "access@high.org", "phone": "14047334400", "status": "New", "score": 50,
}


# ── the gate rejects both live junk rows ─────────────────────────────────────

def test_gate_rejects_the_acme_fixture():
    result = validate_lead_for_storage(PROD_FIXTURE_ACME)
    assert result["ok"] is False
    assert "fixture" in result["reasons"][0]


def test_gate_rejects_business_less_row():
    result = validate_lead_for_storage(PROD_FIXTURE_NO_NAME)
    assert result["ok"] is False
    assert "no business name" in result["reasons"][0]


def test_gate_rejects_phone_as_business_name():
    result = validate_lead_for_storage({"business": "14047334400"})
    assert result["ok"] is False
    assert "phone number" in result["reasons"][0]


def test_gate_rejects_email_as_business_name():
    result = validate_lead_for_storage({"business": "info@dealer.com"})
    assert result["ok"] is False


# ── real leads pass, with unverifiable fields emptied, never faked ───────────

def test_gate_passes_real_lead_and_recomputes_score():
    lead = {
        "business": "Prestige Exotic Rentals", "owner": "Maria Santos",
        "email": "maria@prestigeexotics.com", "phone": "+1 404 733 4400",
        "website": "https://prestigeexotics.com", "vertical": "luxury car rental",
        "score": 999,  # fabricated payload score must not survive
    }
    result = validate_lead_for_storage(lead)
    assert result["ok"] is True
    cleaned = result["lead"]
    assert cleaned["phone"] == "+14047334400"  # normalized E.164
    # owner(25) + direct email(25) + phone(10) + website(10) + luxury(20) + vertical(10)
    assert cleaned["score"] == 100
    assert cleaned["score"] != 999


def test_gate_empties_placeholder_contact_fields_but_keeps_lead():
    lead = {
        "business": "Summit Custom Homes", "owner": "Greg Fields",
        "email": "test@test.com", "phone": "(212) 555-0123",
        "url": "https://example.com/summit",
    }
    result = validate_lead_for_storage(lead)
    assert result["ok"] is True
    assert result["lead"]["email"] == ""
    assert result["lead"]["phone"] == ""
    assert result["lead"]["url"] == ""
    assert len(result["reasons"]) == 3  # every drop is recorded


def test_gate_drops_fixture_owner_name_only():
    result = validate_lead_for_storage({"business": "Riverside Motors", "owner": "John Doe"})
    assert result["ok"] is True
    assert result["lead"]["owner"] == ""


# ── field cleaners ───────────────────────────────────────────────────────────

def test_phone_cleaner_rejects_known_fakes():
    assert clean_phone_for_storage("+1-555-123-4567") == ""   # 555 area code
    assert clean_phone_for_storage("(212) 555-0123") == ""    # fictional exchange
    assert clean_phone_for_storage("0000000000") == ""
    assert clean_phone_for_storage("1234567890") == ""
    assert clean_phone_for_storage("not a phone") == ""
    assert clean_phone_for_storage("") == ""


def test_phone_cleaner_normalizes_real_numbers():
    assert clean_phone_for_storage("404-733-4400") == "+14047334400"
    assert clean_phone_for_storage("+44 20 7946 0958", "GB") == "+442079460958"


def test_email_cleaner_rejects_placeholders():
    for junk in ("example@example.com", "test@test.com", "info@example.com",
                 "support@example.com", "jane.doe@acme.com", "demo@sample.com"):
        assert clean_email_for_storage(junk) == "", junk
    assert clean_email_for_storage("owner@realdealer.com") == "owner@realdealer.com"
    # generic-but-real inboxes survive (scored lower, not rejected)
    assert clean_email_for_storage("info@realdealer.com") == "info@realdealer.com"


def test_url_cleaner_rejects_documentation_hosts():
    assert clean_url_for_storage("https://acme.example.com/contact") == ""
    assert clean_url_for_storage("https://example.org") == ""
    assert clean_url_for_storage("https://prestigeexotics.com") == "https://prestigeexotics.com"


def test_placeholder_phone_and_phone_like_heuristics():
    assert is_placeholder_phone("+1-555-123-4567")
    assert not is_placeholder_phone("+14047334400")
    assert _looks_like_phone("14047334400")
    assert _looks_like_phone("+1 (404) 733-4400")
    assert not _looks_like_phone("Kunkel & Daughters 4x4")
    assert not _looks_like_phone("")


# ── contact confidence: derived from verification signals, never stored ──────

def test_confidence_empty_fields_are_zero():
    assert contact_confidence({}) == {"email": 0, "phone": 0, "owner": 0}


def test_confidence_tracks_email_verification_status():
    base = {"email": "maria@prestigeexotics.com"}
    assert contact_confidence({**base, "email_status": "verified"})["email"] == 90
    assert contact_confidence({**base, "email_status": "found"})["email"] == 65
    assert contact_confidence({**base, "email_status": "guessed"})["email"] == 35
    assert contact_confidence(base)["email"] == 50  # unknown provenance
    # generic inbox penalty
    assert contact_confidence({"email": "info@dealer.com", "email_status": "found"})["email"] == 50


def test_confidence_phone_requires_e164():
    assert contact_confidence({"phone": "+14047334400"})["phone"] == 70
    assert contact_confidence({"phone": "404-733-4400"})["phone"] == 30  # unnormalized


def test_confidence_owner_grows_with_corroboration():
    assert contact_confidence({"owner": "Maria"})["owner"] == 0  # single word
    assert contact_confidence({"owner": "Maria Santos"})["owner"] == 60
    assert contact_confidence({"owner": "Maria Santos", "owner_title": "Owner"})["owner"] == 70
    assert contact_confidence({"owner": "Maria Santos", "owner_title": "Owner",
                               "linkedin_url": "https://linkedin.com/in/msantos"})["owner"] == 75


# ── outreach_ready — the owner bar: decision-maker name + direct email + phone ─

_READY_FULL = {"owner": "Eric Curran", "email": "eric@wcexotics.com",
               "email_status": "verified", "phone": "+14047334400"}


def test_outreach_ready_full_lead_clears_the_bar():
    r = outreach_ready(_READY_FULL)
    assert r["ready"] and r["emailable"] and r["callable"]
    assert r["has_name"] and r["has_direct_email"] and r["has_phone"]
    assert r["blockers"] == []


def test_outreach_ready_generic_email_is_callable_not_emailable():
    # info@ never counts as a direct email — but name + business phone is still callable.
    r = outreach_ready({**_READY_FULL, "email": "info@wcexotics.com", "email_status": "found"})
    assert r["ready"] and r["callable"] and not r["emailable"]
    assert not r["has_direct_email"]
    assert any("generic" in b for b in r["blockers"])


def test_outreach_ready_name_plus_business_phone_no_email():
    # The owner's explicit fallback: no email found → business number + the name.
    r = outreach_ready({"owner": "Eric Curran", "phone": "+14047334400"})
    assert r["ready"] and r["callable"] and not r["emailable"]
    assert "no email" in r["blockers"]


def test_outreach_ready_requires_the_decision_maker_name():
    # Perfect email + phone but no name is NOT ready — can't bypass the gatekeeper.
    r = outreach_ready({"email": "john@dealer.com", "email_status": "verified",
                        "phone": "+14047334400"})
    assert not r["ready"] and not r["has_name"]
    assert "no verified decision-maker name" in r["blockers"]


def test_outreach_ready_emailable_without_phone():
    r = outreach_ready({"owner": "Eric Curran", "email": "eric@wcexotics.com",
                        "email_status": "found"})
    assert r["ready"] and r["emailable"] and not r["callable"]
    assert "no phone" in r["blockers"]


def test_outreach_ready_empty_lead_blocks_everything():
    r = outreach_ready({})
    assert not r["ready"] and not r["emailable"] and not r["callable"]
    assert len(r["blockers"]) == 3


# ── save_lead integration: rejection happens before any DB write ─────────────

def test_save_lead_rejects_junk_without_touching_db(monkeypatch):
    from app.core.database import DatabaseManager

    def _boom(cls):
        raise AssertionError("DB must not be touched for a rejected lead")
    monkeypatch.setattr(DatabaseManager, "connection", classmethod(_boom))
    assert DatabaseManager.save_lead(dict(PROD_FIXTURE_ACME)) == -2
    assert DatabaseManager.save_lead(dict(PROD_FIXTURE_NO_NAME)) == -2


# ── hygiene sweep quarantines restored junk ──────────────────────────────────

LEADS_SCHEMA = """
    CREATE TABLE leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business TEXT, owner TEXT, url TEXT, website TEXT, email TEXT,
        phone TEXT, vertical TEXT, status TEXT DEFAULT 'New', notes TEXT,
        icebreaker TEXT, score REAL DEFAULT 0, client_id INTEGER DEFAULT 0,
        email_status TEXT, owner_title TEXT, linkedin_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP
    );
"""


class _FakeDB:
    """Async DatabaseManager.query shim over a plain sqlite3 connection."""
    def __init__(self, conn):
        self.conn = conn

    async def query(self, sql, params=(), fetchall=False):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur.fetchall() if fetchall else cur


@pytest.fixture
def hygiene_db(tmp_path, monkeypatch):
    conn = sqlite3.connect(str(tmp_path / "hygiene.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(LEADS_SCHEMA)
    ins = ("INSERT INTO leads (business, owner, email, phone, url, vertical, status, score) "
           "VALUES (?,?,?,?,?,?,?,?)")
    # 1: the Acme fixture, 2: the no-name row — the two live prod rows
    conn.execute(ins, ("Acme Remodeling Co", "Jane Doe", "jane.doe@acme.com",
                       "+1-555-123-4567", "https://acme.example.com/contact", "", "new", 85))
    conn.execute(ins, ("", "Member Circles", "access@high.org", "14047334400", "", "", "New", 50))
    # 3: a real lead with one junk field (555 phone) — cleaned, not quarantined
    conn.execute(ins, ("Prestige Exotic Rentals", "Maria Santos", "maria@prestigeexotics.com",
                       "555-123-4567", "https://prestigeexotics.com", "luxury car rental", "New", 50))
    # 4: a fully clean, already-contacted lead — untouched (score preserved)
    conn.execute(ins, ("Legacy Motors", "Ann Kim", "ann@legacymotors.com",
                       "+14047334400", "https://legacymotors.com", "dealer", "Email Sent", 60))
    conn.commit()

    import app.core.lead_hygiene as hygiene
    monkeypatch.setattr(hygiene, "DatabaseManager", _FakeDB(conn))
    yield conn
    conn.close()


def test_sweep_quarantines_prod_junk_and_cleans_partial_rows(hygiene_db):
    from app.core.lead_hygiene import quarantine_invalid_leads
    summary = asyncio.run(quarantine_invalid_leads())
    assert summary["quarantined"] == 2

    rows = {r["id"]: r for r in hygiene_db.execute("SELECT * FROM leads").fetchall()}
    assert rows[1]["status"] == "Invalid" and "[HYGIENE]" in rows[1]["notes"]
    assert rows[2]["status"] == "Invalid"
    # Row 3: junk phone emptied (NOT replaced with anything), score recomputed
    assert rows[3]["status"] == "New"
    assert rows[3]["phone"] == ""
    # owner(25) + direct email(25) + website-via-url(10) + luxury(20) +
    # vertical(10); the junk phone earns nothing
    assert rows[3]["score"] == 90
    # Row 4: contacted + already clean — completely untouched
    assert rows[4]["score"] == 60 and rows[4]["status"] == "Email Sent"


def test_sweep_is_idempotent(hygiene_db):
    from app.core.lead_hygiene import quarantine_invalid_leads
    asyncio.run(quarantine_invalid_leads())
    second = asyncio.run(quarantine_invalid_leads())
    assert second["quarantined"] == 0 and second["cleaned"] == 0 and second["rescored"] == 0
