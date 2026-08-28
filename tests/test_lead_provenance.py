"""Per-field provenance through the enrichment merge (2026-07-20).

Audit findings this locks in:
- resolve_owner returned {source, confidence} but enrich_lead_4step threw
  both away; find_leads_v3's output filter dropped them again; save_lead had
  no columns. Mission Control could never tell a CA-SoS legal filing from an
  AI-scraped guess.
- BUG: enrich_lead_4step's _guess_email fallback returned the guess bare;
  light_enrich later stamped unlabeled emails 'found' — pattern guesses
  masqueraded as scraped facts (confidence 65 instead of 35).
- Phones were first-hit-wins with no corroboration; two independent sources
  agreeing (site + Google Business) is real verification and now recorded.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.skills.lead_gen_v3 import enrich_lead_4step
from app.skills.lead_validator import contact_confidence


def _run_4step(registry=None, website=None, bbb=None, google=None):
    async def go():
        with patch("app.skills.owner_finder.resolve_owner", new_callable=AsyncMock) as m_reg, \
             patch("app.skills.lead_gen_v3._scrape_website", new_callable=AsyncMock) as m_site, \
             patch("app.skills.lead_gen_v3._bbb_lookup", new_callable=AsyncMock) as m_bbb, \
             patch("app.skills.lead_gen_v3._google_business_lookup", new_callable=AsyncMock) as m_goog:
            m_reg.return_value = registry or {"owner": "", "title": "", "source": "", "confidence": 0.0}
            m_site.return_value = website or {}
            m_bbb.return_value = bbb or {}
            m_goog.return_value = google or {}
            return await enrich_lead_4step("https://vividmotors.com", "Vivid Motors", state="CA")
    return asyncio.run(go())


def test_registry_owner_carries_source():
    out = _run_4step(registry={"owner": "Dana Ferrari", "title": "CEO",
                               "source": "ca_sos", "confidence": 0.9})
    assert out["owner_name"] == "Dana Ferrari"
    assert out["owner_source"] == "ca_sos"


def test_field_sources_recorded_in_priority_order():
    out = _run_4step(
        website={"email": "dana@vividmotors.com", "phone": "(716) 670-3920"},
        google={"phone": "716-670-3920", "owner_name": "Dana Ferrari"},
    )
    assert out["email_source"] == "website"
    assert out["email_status"] == "found"
    assert out["phone_source"] == "website"
    assert out["owner_source"] == "google_business"


def test_phone_corroborated_by_two_sources_is_verified():
    out = _run_4step(
        website={"phone": "(716) 670-3920"},
        google={"phone": "+1716 670 3920"},
    )
    assert out["phone"] == "+17166703920"
    assert out["phone_verified"] is True


def test_single_source_phone_is_not_verified():
    out = _run_4step(website={"phone": "(716) 670-3920"})
    assert out["phone_verified"] is False


def test_guessed_email_is_labeled_guessed_never_found():
    # The live bug: guess came back bare -> later stamped 'found'.
    with patch("app.skills.lead_gen_v3._guess_email", return_value="dana@vividmotors.com"):
        out = _run_4step(registry={"owner": "Dana Ferrari", "title": "",
                                   "source": "ca_sos", "confidence": 0.9})
    assert out["email"] == "dana@vividmotors.com"
    assert out["email_status"] == "guessed"
    assert out["email_source"] == "pattern_guess"


# ── confidence consumes the new provenance ───────────────────────────────────

def test_confidence_phone_verified_reaches_90():
    assert contact_confidence({"phone": "+17166703920", "phone_verified": 1})["phone"] == 90
    assert contact_confidence({"phone": "+17166703920"})["phone"] == 70


def test_confidence_registry_owner_outranks_scraped():
    reg = contact_confidence({"owner": "Dana Ferrari", "owner_source": "ca_sos"})
    scraped = contact_confidence({"owner": "Dana Ferrari", "owner_source": "website"})
    assert reg["owner"] == 85
    assert scraped["owner"] == 60


def test_confidence_owner_caps_at_95():
    out = contact_confidence({"owner": "Dana Ferrari", "owner_source": "ca_sos",
                              "owner_title": "CEO", "linkedin_url": "https://linkedin.com/in/df"})
    assert out["owner"] == 95


# ── person-name plausibility: the live fakes must die ────────────────────────

def test_live_fake_owner_names_rejected():
    from app.skills.lead_validator import is_plausible_person_name
    # stored as real owners in production, 2026-07-20 hunt
    for fake in ("THANKS TO", "We Proudly", "Good People", "Member Circles",
                 "Auto Repair", "Free Quote"):
        assert not is_plausible_person_name(fake), fake


def test_real_names_still_pass():
    from app.skills.lead_validator import is_plausible_person_name
    for real in ("Todd Rowsell", "Darren O'Gara", "Maria Santos",
                 "Sarah van Dyke", "Jean-Pierre Dubois", "SMITH JOHN"):
        assert is_plausible_person_name(real), real


def test_gate_drops_implausible_owner_and_derived_guessed_email():
    from app.skills.lead_validator import validate_lead_for_storage
    # the exact live row: fake owner + email fabricated FROM the fake owner
    result = validate_lead_for_storage({
        "business": "Calabasas Luxury Motorcars",
        "owner": "THANKS TO",
        "email": "thanks@calabasasluxurymotorcars.com",
        "phone": "+17166703920",
    })
    assert result["ok"] is True
    assert result["lead"]["owner"] == ""
    assert result["lead"]["email"] == ""  # fabrication squared — gone
    assert result["lead"]["phone"] == "+17166703920"  # real data untouched


def test_gate_keeps_unrelated_email_when_owner_dropped():
    from app.skills.lead_validator import validate_lead_for_storage
    # live row: fake owner but a REAL generic inbox — inbox survives
    result = validate_lead_for_storage({
        "business": "The Luxury Collection Los Gatos",
        "owner": "Good People",
        "email": "info@astonmartinlosgatos.com",
    })
    assert result["lead"]["owner"] == ""
    assert result["lead"]["email"] == "info@astonmartinlosgatos.com"


# ── canonical schema carries the provenance columns ──────────────────────────

def test_canonical_schema_has_provenance_columns():
    from app.core._db_base import CANONICAL_SCHEMA_SQL
    for col in ("owner_source", "email_source", "phone_source", "phone_verified"):
        assert col in CANONICAL_SCHEMA_SQL
