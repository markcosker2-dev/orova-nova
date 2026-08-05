"""Tests for the owner-name-FIRST resolver (app/skills/owner_finder.py).

Covers: fallback order (registry hit short-circuits; falls through on miss/
error), rationing (counter exhausted -> source skipped), cache hit (2nd call
doesn't re-request), all-sources-fail -> empty dict / no crash, LLM-dead
safety (no AI import anywhere in this module), and that find_leads_v3 wires
resolve_owner into its enrichment step.

All httpx calls are mocked — fully offline. Follows the style of
tests/test_reply_booking.py / tests/test_approval_gate.py: plain
asyncio.run + unittest.mock, patched at the module path the code under
test actually imports from.
"""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from app.skills import owner_finder


# ── helpers ──────────────────────────────────────────────────────────────────

def _resp(status_code=200, json_data=None, text=""):
    """A minimal stand-in for an httpx.Response."""
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.text = text
    return m


def _client_returning(get_return=None, get_side_effect=None):
    """Build a mock httpx.AsyncClient whose .get() is an AsyncMock, usable as
    an async context manager (the code does `async with httpx.AsyncClient(...) as client`)."""
    client = MagicMock()
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(return_value=get_return or _resp())
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _no_cache_no_ration():
    """Patch DatabaseManager so cache always misses and rationing always allows
    (bucket count starts at 0 each call) — used for tests that aren't
    specifically exercising cache/ration behavior."""
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)
    db.set_state = AsyncMock()
    return db


# ── fallback order: WA registry hit short-circuits everything else ─────────

def test_wa_hit_short_circuits_other_stages(monkeypatch):
    # WA now resolves against the L&I contractor licence registry on
    # data.wa.gov (Socrata list-of-rows), not the anti-bot-gated SoS API.
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    monkeypatch.delenv("OPENCORPORATES_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    wa_json = [{"businessname": "ACME ROOFING LLC",
                "primaryprincipalname": "SMITH, JANE MARIE",
                "contractorlicensestatus": "ACTIVE"}]
    client = _client_returning(get_return=_resp(200, wa_json))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=_no_cache_no_ration())), \
         patch("app.skills.owner_finder._website_scrape_fallback", AsyncMock()) as scrape_mock, \
         patch("app.skills.owner_finder._serpapi_fallback", AsyncMock()) as serp_mock:
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA"))

    assert result["owner"] == "Jane Smith"
    assert result["source"] == "wa_lni"
    assert result["confidence"] > 0
    scrape_mock.assert_not_called()
    serp_mock.assert_not_called()


def test_wa_miss_falls_through_to_website_scrape(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    monkeypatch.delenv("OPENCORPORATES_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    empty_wa = {"Rows": []}
    client = _client_returning(get_return=_resp(200, empty_wa))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=_no_cache_no_ration())), \
         patch("app.skills.owner_finder._website_scrape_fallback",
               AsyncMock(return_value={"owner": "Bob Jones", "title": "", "source": "website_scrape", "confidence": 0.5})) as scrape_mock:
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA", domain="acme.com"))

    assert result["owner"] == "Bob Jones"
    assert result["source"] == "website_scrape"
    scrape_mock.assert_called_once()


def test_registry_error_falls_through_without_raising(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)

    client = _client_returning(get_side_effect=RuntimeError("network exploded"))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=_no_cache_no_ration())), \
         patch("app.skills.owner_finder._website_scrape_fallback",
               AsyncMock(return_value={"owner": "Carla Diaz", "title": "", "source": "website_scrape", "confidence": 0.5})):
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA"))

    assert result["owner"] == "Carla Diaz"  # fell through, no exception propagated


# ── CA gating: default OFF, only runs when CA_SOS_API_KEY is set ──────────

def test_ca_registry_skipped_when_key_unset(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    result = asyncio.run(owner_finder._ca_registry_lookup("Acme Roofing"))
    assert result["owner"] == ""
    assert result["source"] == ""


def test_ca_registry_used_when_key_set(monkeypatch):
    monkeypatch.setenv("CA_SOS_API_KEY", "test-key-123")
    ca_json = {"entities": [{"officers": [{"name": "Maria Lopez", "title": "CEO"}]}]}
    client = _client_returning(get_return=_resp(200, ca_json))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        result = asyncio.run(owner_finder._ca_registry_lookup("Acme Roofing"))

    assert result["owner"] == "Maria Lopez"
    assert result["source"] == "ca_sos"


def test_ca_registry_errors_default_to_empty_not_raise(monkeypatch):
    monkeypatch.setenv("CA_SOS_API_KEY", "test-key-123")
    client = _client_returning(get_side_effect=RuntimeError("CALICO is down"))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        result = asyncio.run(owner_finder._ca_registry_lookup("Acme Roofing"))
    assert result == {"owner": "", "title": "", "source": "", "confidence": 0.0}


# ── rationing: OpenCorporates daily cap ────────────────────────────────────

def test_opencorporates_skipped_when_daily_cap_exhausted(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_KEY", "oc-test-key")

    # Ration state already at cap for today's bucket.
    import time
    now = time.localtime()
    bucket = f"{now.tm_year}-{now.tm_yday}"
    db = MagicMock()
    db.get_state = AsyncMock(return_value={"bucket": bucket, "count": owner_finder.OPENCORPORATES_DAILY_CAP})
    db.set_state = AsyncMock()

    client = _client_returning(get_return=_resp(200, {"results": {"companies": []}}))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client) as client_cls, \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)):
        result = asyncio.run(owner_finder._opencorporates_lookup("Acme Roofing"))

    assert result["owner"] == ""
    client_cls.assert_not_called()  # ration check must block the HTTP call entirely


def test_opencorporates_allowed_under_cap(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_KEY", "oc-test-key")
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)  # no bucket yet -> starts at 0
    db.set_state = AsyncMock()

    oc_json = {"results": {"companies": [{"company": {"officers": [
        {"officer": {"name": "Tom Reed", "position": "Manager"}}
    ]}}]}}
    client = _client_returning(get_return=_resp(200, oc_json))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)):
        result = asyncio.run(owner_finder._opencorporates_lookup("Acme Roofing"))

    assert result["owner"] == "Tom Reed"
    assert result["source"] == "opencorporates"
    db.set_state.assert_awaited()  # usage count incremented


def test_opencorporates_skipped_when_no_key(monkeypatch):
    monkeypatch.delenv("OPENCORPORATES_API_KEY", raising=False)
    result = asyncio.run(owner_finder._opencorporates_lookup("Acme Roofing"))
    assert result["owner"] == ""


# ── SerpAPI: score-gated + monthly cap ──────────────────────────────────────

def test_serpapi_skipped_below_score_threshold(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "serp-test-key")
    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls:
        result = asyncio.run(owner_finder._serpapi_fallback("Acme Roofing", score=10.0))
    assert result["owner"] == ""
    client_cls.assert_not_called()


def test_serpapi_skipped_when_monthly_cap_exhausted(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "serp-test-key")
    import time
    now = time.localtime()
    bucket = f"{now.tm_year}-{now.tm_mon}"
    db = MagicMock()
    db.get_state = AsyncMock(return_value={"bucket": bucket, "count": owner_finder.SERPAPI_MONTHLY_CAP})
    db.set_state = AsyncMock()

    with patch("app.skills.owner_finder.httpx.AsyncClient") as client_cls, \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)):
        result = asyncio.run(owner_finder._serpapi_fallback("Acme Roofing", score=90.0))

    assert result["owner"] == ""
    client_cls.assert_not_called()


def test_serpapi_used_for_high_score_lead_under_cap(monkeypatch):
    monkeypatch.setenv("SERPAPI_KEY", "serp-test-key")
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)
    db.set_state = AsyncMock()

    serp_json = {"organic_results": [
        {"title": "Acme Roofing", "snippet": "Founded by Nina Patel, owner of Acme Roofing."}
    ]}
    client = _client_returning(get_return=_resp(200, serp_json))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)):
        result = asyncio.run(owner_finder._serpapi_fallback("Acme Roofing", score=95.0))

    assert result["owner"] == "Nina Patel"
    assert result["source"] == "serpapi"


def test_serpapi_does_not_overcapture_trailing_word(monkeypatch):
    """Regression (live-observed 2026-07-04): a snippet like '...Founder Kim
    Malek Built the...' must extract 'Kim Malek', not 'Kim Malek Built' — the
    role-prefixed patterns now cap at first+last."""
    monkeypatch.setenv("SERPAPI_KEY", "serp-test-key")
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)
    db.set_state = AsyncMock()

    serp_json = {"organic_results": [
        {"title": "How Salt & Straw Founder Kim Malek Built an Empire",
         "snippet": "Salt & Straw Founder Kim Malek Built the ice cream brand from scratch."}
    ]}
    client = _client_returning(get_return=_resp(200, serp_json))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)):
        result = asyncio.run(owner_finder._serpapi_fallback("Salt & Straw", score=95.0))

    assert result["owner"] == "Kim Malek"


# ── cache: second call doesn't re-request ──────────────────────────────────

def test_cache_hit_skips_second_lookup(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    import time
    cached_entry = {
        "_cached_at": time.time(),
        "result": {"owner": "Cached Owner", "title": "CEO", "source": "wa_sos", "confidence": 0.85},
    }
    db = MagicMock()
    db.get_state = AsyncMock(return_value=cached_entry)
    db.set_state = AsyncMock()

    with patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)), \
         patch("app.skills.owner_finder._registry_lookup", AsyncMock()) as registry_mock, \
         patch("app.skills.owner_finder._website_scrape_fallback", AsyncMock()) as scrape_mock, \
         patch("app.skills.owner_finder._serpapi_fallback", AsyncMock()) as serp_mock:
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA"))

    assert result["owner"] == "Cached Owner"
    registry_mock.assert_not_called()
    scrape_mock.assert_not_called()
    serp_mock.assert_not_called()
    db.set_state.assert_not_awaited()  # cache hit path never re-writes the cache


def test_cache_expired_ttl_triggers_fresh_lookup(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    import time
    stale_entry = {
        "_cached_at": time.time() - (owner_finder.CACHE_TTL_SECONDS + 3600),  # 1hr past TTL
        "result": {"owner": "Stale Owner", "title": "", "source": "wa_sos", "confidence": 0.85},
    }
    db = MagicMock()
    db.get_state = AsyncMock(return_value=stale_entry)
    db.set_state = AsyncMock()

    with patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db)), \
         patch("app.skills.owner_finder._registry_lookup",
               AsyncMock(return_value={"owner": "Fresh Owner", "title": "", "source": "wa_sos", "confidence": 0.85})) as registry_mock:
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA"))

    assert result["owner"] == "Fresh Owner"
    registry_mock.assert_called_once()


# ── all sources fail -> empty dict, no crash ────────────────────────────────

def test_all_sources_fail_returns_empty_dict_no_crash(monkeypatch):
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    monkeypatch.delenv("OPENCORPORATES_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)

    client = _client_returning(get_side_effect=RuntimeError("everything is down"))

    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
         patch("app.skills.owner_finder._get_db", AsyncMock(return_value=_no_cache_no_ration())), \
         patch("app.skills.owner_finder._website_scrape_fallback", AsyncMock(side_effect=RuntimeError("scrape blew up"))):
        result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="ZZ", domain="acme.com", score=99.0))

    assert result == {"owner": "", "title": "", "source": "", "confidence": 0.0}


def test_empty_business_name_returns_empty_immediately():
    result = asyncio.run(owner_finder.resolve_owner(""))
    assert result == {"owner": "", "title": "", "source": "", "confidence": 0.0}


# ── LLM-dead safety: this module never imports/depends on any AI client ────

def test_no_ai_client_import_anywhere_in_module():
    import inspect
    source = inspect.getsource(owner_finder)
    assert "ai_client" not in source
    assert "UnifiedAIClient" not in source


def test_resolve_owner_works_with_no_ai_available(monkeypatch):
    # Simulate the documented dead-LLM state: even if ai_client.UnifiedAIClient
    # raises when constructed, resolve_owner must still work since it never
    # touches it.
    monkeypatch.delenv("CA_SOS_API_KEY", raising=False)
    with patch("app.core.ai_client.UnifiedAIClient", side_effect=RuntimeError("no key")):
        wa_json = [{"businessname": "ACME ROOFING",
                    "primaryprincipalname": "REILLY, PAT",
                    "contractorlicensestatus": "ACTIVE"}]
        client = _client_returning(get_return=_resp(200, wa_json))
        with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client), \
             patch("app.skills.owner_finder._get_db", AsyncMock(return_value=_no_cache_no_ration())):
            result = asyncio.run(owner_finder.resolve_owner("Acme Roofing", state="WA"))
    assert result["owner"] == "Pat Reilly"


# ── OR CCB licence registry ──────────────────────────────────────────────
#
# Replaced the Oregon SECRETARY OF STATE HTML scrape, which was wrong twice
# over (both verified live 2026-08-06):
#   · it returned an owner for 0 of 10 real Oregon contractors, and the host
#     does not answer at all — a full connect timeout.
#   · even working, a "Registered Agent" is frequently a law firm or an agent
#     service, not the decision maker.
# CCB publishes the Responsible Managing Individual, the direct analogue of
# WA L&I's licence principal. Live hit rate on the same corpus: 13/14.

_OR_ROWS = [   # verbatim shapes from data.oregon.gov/resource/g77e-6bhs.json
    {"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": "TANYA VALERIA PONOMAREV",
     "state": "OR"},
]


def test_or_ccb_returns_the_responsible_managing_individual():
    client = _client_returning(get_return=_resp(200, json_data=_OR_ROWS))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        result = asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))
    assert result["owner"] == "Tanya Ponomarev"
    assert result["source"] == "or_ccb"
    assert result["title"] == "Responsible Managing Individual"
    assert result["confidence"] == 0.9


def test_or_ccb_requires_an_exact_normalized_name_match():
    """A near-miss must return nothing, not the wrong company's RMI."""
    client = _client_returning(get_return=_resp(200, json_data=_OR_ROWS))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        result = asyncio.run(owner_finder._or_registry_lookup("Vitan Construction & Design"))
    assert result["owner"] == ""


def test_or_ccb_refuses_single_token_names():
    """'Acme' exact-matched a real licence literally named ACME once — a
    correct string match to the wrong company."""
    client = _client_returning(get_return=_resp(200, json_data=_OR_ROWS))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        assert asyncio.run(owner_finder._or_registry_lookup("Vitan"))["owner"] == ""


def test_or_ccb_rejects_placeholder_rmi_values():
    """116 rows carry a sentinel instead of a person. 'RD - NO RMI RQRD'
    parses to 'Rd Rqrd', which passes _is_plausible_name and would put a
    nonexistent person into a call script."""
    for sentinel in ("RD - NO RMI RQRD", "RMI NOT RQ'D", "NO RMI ON FILE",
                     "NO RMI REQUIRED - DEVELOPER"):
        rows = [{"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": sentinel,
                 "state": "OR"}]
        client = _client_returning(get_return=_resp(200, json_data=rows))
        with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
            result = asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))
        assert result["owner"] == "", f"{sentinel!r} became an owner name"


def test_or_ccb_refuses_to_guess_between_conflicting_individuals():
    rows = [
        {"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": "TANYA VALERIA PONOMAREV", "state": "OR"},
        {"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": "SOMEONE ELSE ENTIRELY", "state": "OR"},
    ]
    client = _client_returning(get_return=_resp(200, json_data=rows))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        assert asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))["owner"] == ""


def test_or_ccb_prefers_an_in_state_licence():
    """The dataset is 'contractors who can legally work in Oregon' — 14.5% of
    rows are based elsewhere."""
    rows = [
        {"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": "OUT OF STATE PERSON", "state": "WA"},
        {"full_name": "VITAN CONSTRUCTION LLC", "rmi_name": "TANYA VALERIA PONOMAREV", "state": "OR"},
    ]
    client = _client_returning(get_return=_resp(200, json_data=rows))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        result = asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))
    assert result["owner"] == "Tanya Ponomarev"


def test_or_ccb_skips_cleanly_on_non_200():
    client = _client_returning(get_return=_resp(503, json_data=[]))
    with patch("app.skills.owner_finder.httpx.AsyncClient", return_value=client):
        assert asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))["owner"] == ""


def test_or_ccb_kill_switch(monkeypatch):
    monkeypatch.setenv("OR_CCB_ENABLED", "0")
    assert asyncio.run(owner_finder._or_registry_lookup("Vitan Construction"))["owner"] == ""


# ── unknown/other state routes to OpenCorporates ────────────────────────────

def test_unknown_state_routes_to_opencorporates(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_KEY", "oc-test-key")
    with patch("app.skills.owner_finder._opencorporates_lookup",
               AsyncMock(return_value={"owner": "Sam Kim", "title": "Director", "source": "opencorporates", "confidence": 0.75})) as oc_mock, \
         patch("app.skills.owner_finder._wa_registry_lookup", AsyncMock()) as wa_mock, \
         patch("app.skills.owner_finder._ca_registry_lookup", AsyncMock()) as ca_mock, \
         patch("app.skills.owner_finder._or_registry_lookup", AsyncMock()) as or_mock:
        result = asyncio.run(owner_finder._registry_lookup("Acme Roofing", "TX"))

    assert result["owner"] == "Sam Kim"
    oc_mock.assert_called_once()
    wa_mock.assert_not_called()
    ca_mock.assert_not_called()
    or_mock.assert_not_called()


# ── find_leads_v3 wiring: resolve_owner is actually invoked ────────────────

def test_find_leads_invokes_resolve_owner():
    """The enrichment step in lead_gen_v3.enrich_lead_4step must call
    owner_finder.resolve_owner before falling back to the website-scrape
    owner_name strategy, per the task's wiring requirement."""
    from app.skills import lead_gen_v3

    resolve_mock = AsyncMock(return_value={"owner": "Registry Owner", "title": "CEO", "source": "wa_sos", "confidence": 0.85})

    async def _fake_strategy(*args, **kwargs):
        return {"owner_name": "", "email": "", "phone": ""}

    with patch("app.skills.owner_finder.resolve_owner", resolve_mock), \
         patch.object(lead_gen_v3, "_scrape_website", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_whois_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_state_registry_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_ddg_owner_verification", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_bbb_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_google_business_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})):
        result = asyncio.run(lead_gen_v3.enrich_lead_4step("https://acme.com", "Acme Roofing", state="WA"))

    resolve_mock.assert_awaited_once()
    call_kwargs = resolve_mock.await_args.kwargs
    assert call_kwargs.get("state") == "WA"
    assert result["owner_name"] == "Registry Owner"


def test_find_leads_registry_miss_falls_back_to_website_scrape_strategy():
    """When resolve_owner comes up empty, the existing 6-strategy chain
    (specifically the website scrape strategy) still supplies the name —
    confirms the fallback wiring, not just the short-circuit path."""
    from app.skills import lead_gen_v3

    resolve_mock = AsyncMock(return_value={"owner": "", "title": "", "source": "", "confidence": 0.0})

    with patch("app.skills.owner_finder.resolve_owner", resolve_mock), \
         patch.object(lead_gen_v3, "_scrape_website",
                      AsyncMock(return_value={"owner_name": "Scraped Name", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_whois_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_state_registry_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_ddg_owner_verification", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_bbb_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})), \
         patch.object(lead_gen_v3, "_google_business_lookup", AsyncMock(return_value={"owner_name": "", "email": "", "phone": ""})):
        result = asyncio.run(lead_gen_v3.enrich_lead_4step("https://acme.com", "Acme Roofing", state="WA"))

    resolve_mock.assert_awaited_once()
    assert result["owner_name"] == "Scraped Name"
