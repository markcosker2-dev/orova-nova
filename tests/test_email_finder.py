"""Tests for the owner-direct email finder + verifier (app/skills/email_finder.py).

Covers: env-gating (unset keys skip cleanly), quota rationing (cap exhausted
-> no HTTP call), Tomba->Prospeo fallback order (never both on one lead when
Tomba hits), Verifalia verdict parsing incl. the 202-poll path, fail-OPEN
behavior on verifier errors, select_best_guess's upgrade/keep/drop logic, and
the light_enrich wiring (Step 4.7 finder + Step 5 verified guess).

All httpx calls are mocked — fully offline. Follows tests/test_owner_finder.py's
style: plain asyncio.run + unittest.mock, patched at the module path the code
under test actually imports from.
"""
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock

from app.skills import email_finder


# ── helpers (same shapes as test_owner_finder.py) ──────────────────────────

def _resp(status_code=200, json_data=None, text=""):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    m.text = text
    return m


def _client(get_return=None, post_return=None, get_side_effect=None, post_side_effect=None):
    client = MagicMock()
    client.get = AsyncMock(return_value=get_return or _resp(), side_effect=get_side_effect)
    client.post = AsyncMock(return_value=post_return or _resp(), side_effect=post_side_effect)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _no_ration_db():
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)
    db.set_state = AsyncMock()
    return db


def _patch_db(db=None):
    """The ration helper lives in owner_finder — patch its DB handle there."""
    return patch("app.skills.owner_finder._get_db", AsyncMock(return_value=db or _no_ration_db()))


def _clear_finder_env(monkeypatch):
    for var in ("TOMBA_API_KEY", "TOMBA_SECRET", "PROSPEO_API_KEY",
                "VERIFALIA_USERNAME", "VERIFALIA_PASSWORD"):
        monkeypatch.delenv(var, raising=False)


# ── Tomba: env-gating, parsing, rationing ──────────────────────────────────

def test_tomba_skipped_when_keys_unset(monkeypatch):
    _clear_finder_env(monkeypatch)
    with patch("app.skills.email_finder.httpx.AsyncClient") as client_cls:
        result = asyncio.run(email_finder._tomba_finder("Jane Smith", "acme.com"))
    assert result == {"email": "", "source": "", "status": ""}
    client_cls.assert_not_called()


def test_tomba_parses_verified_hit(monkeypatch):
    monkeypatch.setenv("TOMBA_API_KEY", "ta_test")
    monkeypatch.setenv("TOMBA_SECRET", "ts_test")
    tomba_json = {"data": {"email": "Jane@Acme.com", "score": 97,
                           "verification": {"status": "valid"}}}
    client = _client(get_return=_resp(200, tomba_json))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._tomba_finder("Jane Smith", "acme.com"))
    assert result == {"email": "jane@acme.com", "source": "tomba", "status": "verified"}


def test_tomba_low_score_hit_is_found_not_verified(monkeypatch):
    monkeypatch.setenv("TOMBA_API_KEY", "ta_test")
    monkeypatch.setenv("TOMBA_SECRET", "ts_test")
    tomba_json = {"data": {"email": "jane@acme.com", "score": 40, "verification": {"status": ""}}}
    client = _client(get_return=_resp(200, tomba_json))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._tomba_finder("Jane Smith", "acme.com"))
    assert result["status"] == "found"


def test_tomba_blocked_when_monthly_cap_exhausted(monkeypatch):
    monkeypatch.setenv("TOMBA_API_KEY", "ta_test")
    monkeypatch.setenv("TOMBA_SECRET", "ts_test")
    now = time.localtime()
    db = MagicMock()
    db.get_state = AsyncMock(return_value={"bucket": f"{now.tm_year}-{now.tm_mon}",
                                           "count": email_finder.TOMBA_MONTHLY_CAP})
    db.set_state = AsyncMock()
    with patch("app.skills.email_finder.httpx.AsyncClient") as client_cls, _patch_db(db):
        result = asyncio.run(email_finder._tomba_finder("Jane Smith", "acme.com"))
    assert result["email"] == ""
    client_cls.assert_not_called()  # ration must block the HTTP call entirely


def test_tomba_network_error_returns_empty_no_crash(monkeypatch):
    monkeypatch.setenv("TOMBA_API_KEY", "ta_test")
    monkeypatch.setenv("TOMBA_SECRET", "ts_test")
    client = _client(get_side_effect=RuntimeError("tomba is down"))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._tomba_finder("Jane Smith", "acme.com"))
    assert result == {"email": "", "source": "", "status": ""}


# ── Prospeo: parsing + both response shapes ─────────────────────────────────

def test_prospeo_skipped_when_key_unset(monkeypatch):
    _clear_finder_env(monkeypatch)
    with patch("app.skills.email_finder.httpx.AsyncClient") as client_cls:
        result = asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    assert result["email"] == ""
    client_cls.assert_not_called()


# Shape mirrors the live /enrich-person response verified 2026-07-10.
def _prospeo_body(email="jane@acme.com", status="VERIFIED", revealed=True):
    return {"error": False, "person": {"full_name": "Jane Smith",
            "email": {"status": status, "revealed": revealed, "email": email,
                      "verification_method": "SMTP"}}}


def test_prospeo_parses_verified_reveal(monkeypatch):
    monkeypatch.setenv("PROSPEO_API_KEY", "pk_test")
    client = _client(post_return=_resp(200, _prospeo_body()))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    assert result == {"email": "jane@acme.com", "source": "prospeo", "status": "verified"}


def test_prospeo_unverified_reveal_is_found_not_verified(monkeypatch):
    monkeypatch.setenv("PROSPEO_API_KEY", "pk_test")
    client = _client(post_return=_resp(200, _prospeo_body(status="UNKNOWN")))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    assert result["status"] == "found"


def test_prospeo_masked_unrevealed_email_is_rejected(monkeypatch):
    monkeypatch.setenv("PROSPEO_API_KEY", "pk_test")
    body = _prospeo_body(email="j***@acme.com", revealed=False)
    client = _client(post_return=_resp(200, body))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    assert result["email"] == ""  # masked address is not usable for outreach


def test_prospeo_sends_new_enrich_person_shape(monkeypatch):
    """Guard against regressing to the DEPRECATED /email-finder endpoint."""
    monkeypatch.setenv("PROSPEO_API_KEY", "pk_test")
    client = _client(post_return=_resp(200, _prospeo_body()))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    url = client.post.await_args.args[0]
    payload = client.post.await_args.kwargs["json"]
    assert url.endswith("/enrich-person")
    assert payload == {"data": {"full_name": "Jane Smith", "company_website": "acme.com"}}


def test_prospeo_error_flag_returns_empty(monkeypatch):
    monkeypatch.setenv("PROSPEO_API_KEY", "pk_test")
    client = _client(post_return=_resp(200, {"error": True}))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._prospeo_finder("Jane Smith", "acme.com"))
    assert result["email"] == ""


# ── find_owner_email: Tomba-first order, Prospeo as fallback only ──────────

def test_tomba_hit_short_circuits_prospeo(monkeypatch):
    _clear_finder_env(monkeypatch)
    hit = {"email": "jane@acme.com", "source": "tomba", "status": "verified"}
    with patch("app.skills.email_finder._tomba_finder", AsyncMock(return_value=hit)), \
         patch("app.skills.email_finder._prospeo_finder", AsyncMock()) as prospeo_mock:
        result = asyncio.run(email_finder.find_owner_email("Jane Smith", "acme.com"))
    assert result["source"] == "tomba"
    prospeo_mock.assert_not_called()  # never spend both quotas on one lead


def test_tomba_miss_falls_back_to_prospeo(monkeypatch):
    _clear_finder_env(monkeypatch)
    hit = {"email": "jane@acme.com", "source": "prospeo", "status": "found"}
    with patch("app.skills.email_finder._tomba_finder",
               AsyncMock(return_value=dict(email_finder._EMPTY))), \
         patch("app.skills.email_finder._prospeo_finder", AsyncMock(return_value=hit)):
        result = asyncio.run(email_finder.find_owner_email("Jane Smith", "acme.com"))
    assert result["source"] == "prospeo"


def test_find_owner_email_empty_inputs_return_empty():
    assert asyncio.run(email_finder.find_owner_email("", "acme.com"))["email"] == ""
    assert asyncio.run(email_finder.find_owner_email("Jane Smith", ""))["email"] == ""


# ── Verifalia: env-gating, verdict parsing, 202 poll, fail-open ────────────

def test_verifalia_returns_none_when_creds_unset(monkeypatch):
    _clear_finder_env(monkeypatch)
    with patch("app.skills.email_finder.httpx.AsyncClient") as client_cls:
        result = asyncio.run(email_finder._verifalia_classify(["a@b.com"]))
    assert result is None
    client_cls.assert_not_called()


def test_verifalia_parses_classifications(monkeypatch):
    monkeypatch.setenv("VERIFALIA_USERNAME", "user")
    monkeypatch.setenv("VERIFALIA_PASSWORD", "pass")
    verifalia_json = {"entries": {"data": [
        {"inputData": "jane@acme.com", "classification": "Deliverable"},
        {"inputData": "jane.smith@acme.com", "classification": "Undeliverable"},
    ]}}
    client = _client(post_return=_resp(200, verifalia_json))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._verifalia_classify(["jane@acme.com", "jane.smith@acme.com"]))
    assert result == {"jane@acme.com": "Deliverable", "jane.smith@acme.com": "Undeliverable"}


def test_verifalia_202_polls_once_then_parses(monkeypatch):
    monkeypatch.setenv("VERIFALIA_USERNAME", "user")
    monkeypatch.setenv("VERIFALIA_PASSWORD", "pass")
    accepted = _resp(202, {"overview": {"id": "job-123"}})
    completed = _resp(200, {"entries": {"data": [
        {"inputData": "jane@acme.com", "classification": "Risky"},
    ]}})
    client = _client(post_return=accepted, get_return=completed)
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._verifalia_classify(["jane@acme.com"]))
    assert result == {"jane@acme.com": "Risky"}
    client.get.assert_awaited_once()  # exactly one poll, then give up


def test_verifalia_network_error_fails_open_to_none(monkeypatch):
    monkeypatch.setenv("VERIFALIA_USERNAME", "user")
    monkeypatch.setenv("VERIFALIA_PASSWORD", "pass")
    client = _client(post_side_effect=RuntimeError("verifalia is down"))
    with patch("app.skills.email_finder.httpx.AsyncClient", return_value=client), _patch_db():
        result = asyncio.run(email_finder._verifalia_classify(["jane@acme.com"]))
    assert result is None


def test_verifalia_ration_counts_per_email_not_per_call(monkeypatch):
    """3 candidates with only 2 credits left today must be blocked outright —
    the amount-aware ration prevents a partial overspend."""
    monkeypatch.setenv("VERIFALIA_USERNAME", "user")
    monkeypatch.setenv("VERIFALIA_PASSWORD", "pass")
    now = time.localtime()
    db = MagicMock()
    db.get_state = AsyncMock(return_value={"bucket": f"{now.tm_year}-{now.tm_yday}",
                                           "count": email_finder.VERIFALIA_DAILY_CAP - 2})
    db.set_state = AsyncMock()
    with patch("app.skills.email_finder.httpx.AsyncClient") as client_cls, _patch_db(db):
        result = asyncio.run(email_finder._verifalia_classify(["a@b.com", "c@b.com", "d@b.com"]))
    assert result is None
    client_cls.assert_not_called()


# ── select_best_guess: upgrade / keep / drop ────────────────────────────────

_GUESSES = ["jane@acme.com", "jane.smith@acme.com", "jsmith@acme.com", "janesmith@acme.com"]


def test_no_verdict_keeps_first_guess_as_guessed():
    with patch("app.skills.email_finder._verifalia_classify", AsyncMock(return_value=None)):
        chosen, status = asyncio.run(email_finder.select_best_guess(_GUESSES))
    assert (chosen, status) == ("jane@acme.com", "guessed")


def test_deliverable_candidate_upgrades_to_verified():
    verdicts = {"jane@acme.com": "Undeliverable", "jane.smith@acme.com": "Deliverable"}
    with patch("app.skills.email_finder._verifalia_classify", AsyncMock(return_value=verdicts)):
        chosen, status = asyncio.run(email_finder.select_best_guess(_GUESSES))
    assert (chosen, status) == ("jane.smith@acme.com", "verified")


def test_all_undeliverable_drops_email_entirely():
    verdicts = {g: "Undeliverable" for g in _GUESSES[:3]}
    with patch("app.skills.email_finder._verifalia_classify", AsyncMock(return_value=verdicts)):
        chosen, status = asyncio.run(email_finder.select_best_guess(_GUESSES))
    assert (chosen, status) == (None, "")


def test_risky_without_deliverable_stays_guessed():
    verdicts = {"jane@acme.com": "Undeliverable",
                "jane.smith@acme.com": "Risky",
                "jsmith@acme.com": "Unknown"}
    with patch("app.skills.email_finder._verifalia_classify", AsyncMock(return_value=verdicts)):
        chosen, status = asyncio.run(email_finder.select_best_guess(_GUESSES))
    assert (chosen, status) == ("jane.smith@acme.com", "guessed")


def test_empty_guesses_return_none():
    assert asyncio.run(email_finder.select_best_guess([])) == (None, "")


# ── light_enrich wiring: Step 4.7 + Step 5 actually call this module ───────

def _bare_lead():
    return {"url": "https://acme.com", "business": "Acme Roofing", "owner": "Jane Smith"}


def _enrich_with_patches(lead, finder_result, guess_result):
    """Run enrich_lead_lite with all network/AI paths stubbed out so only the
    email-finder wiring is exercised."""
    from app.skills import light_enrich
    with patch.object(light_enrich, "_fetch_page", AsyncMock(return_value=None)), \
         patch.object(light_enrich, "_ddg_enrich_contact", AsyncMock(return_value=("", ""))), \
         patch.object(light_enrich, "_verify_mx", AsyncMock(return_value=True)), \
         patch.object(light_enrich, "log_skill_note", MagicMock()), \
         patch("app.skills.email_finder.find_owner_email", AsyncMock(return_value=finder_result)) as finder_mock, \
         patch("app.skills.email_finder.select_best_guess", AsyncMock(return_value=guess_result)) as guess_mock, \
         patch("app.skills.lead_enrichment.enrich_with_linkedin", AsyncMock(return_value={})):
        result = asyncio.run(light_enrich.enrich_lead_lite(lead))
    return result, finder_mock, guess_mock


def test_enrich_uses_finder_hit_and_skips_guessing(monkeypatch):
    _clear_finder_env(monkeypatch)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    finder_hit = {"email": "jane@acme.com", "source": "tomba", "status": "verified"}
    result, finder_mock, guess_mock = _enrich_with_patches(_bare_lead(), finder_hit, (None, ""))
    assert result["email"] == "jane@acme.com"
    assert result["email_status"] == "verified"
    finder_mock.assert_awaited_once()
    guess_mock.assert_not_called()  # finder hit means no guessing needed


def test_enrich_verified_guess_sets_verified_status(monkeypatch):
    _clear_finder_env(monkeypatch)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    result, _, guess_mock = _enrich_with_patches(
        _bare_lead(), dict(email_finder._EMPTY), ("jane@acme.com", "verified"))
    assert result["email"] == "jane@acme.com"
    assert result["email_status"] == "verified"
    guess_mock.assert_awaited_once()


def test_enrich_all_bounce_leaves_lead_without_email(monkeypatch):
    _clear_finder_env(monkeypatch)
    monkeypatch.delenv("HUNTER_API_KEY", raising=False)
    monkeypatch.delenv("APOLLO_API_KEY", raising=False)
    result, _, _ = _enrich_with_patches(_bare_lead(), dict(email_finder._EMPTY), (None, ""))
    assert not result.get("email")  # bounce-poison guard: no email beats a bad one
