"""Tests for the National DNC Registry scrub gate (app/core/dnc.is_dnc_registered).

An ADDITIVE TCPA gate on top of the existing opt-out suppression list. Unlike
is_suppressed (fail-closed), the national-registry check FAILS OPEN — it must
never block the live call lane when unconfigured, because there is no registry
data source on the $0 tier yet. Fully offline: httpx + DatabaseManager mocked.
"""
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock

from app.core import dnc


def _resp(status=200, json_data=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data or {}
    return m


def _client(get_return=None, get_side_effect=None):
    c = MagicMock()
    c.get = AsyncMock(return_value=get_return or _resp(), side_effect=get_side_effect)
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    return c


def _clear_env(monkeypatch):
    monkeypatch.delenv("DNC_SCRUB_API_KEY", raising=False)
    monkeypatch.delenv("DNC_SCRUB_URL", raising=False)


def _no_cache_db():
    db = MagicMock()
    db.get_state = AsyncMock(return_value=None)
    db.set_state = AsyncMock()
    return db


def test_unconfigured_fails_open_without_http(monkeypatch):
    _clear_env(monkeypatch)
    with patch("app.core.dnc.httpx.AsyncClient") as client_cls:
        result = asyncio.run(dnc.is_dnc_registered("+17165551234"))
    assert result is False               # fail-open: not blocked
    client_cls.assert_not_called()       # no lookup attempted


def test_registered_number_is_blocked(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    client = _client(get_return=_resp(200, {"on_registry": True}))
    with patch("app.core.dnc.httpx.AsyncClient", return_value=client), \
         patch("app.core.dnc.DatabaseManager", _no_cache_db()):
        assert asyncio.run(dnc.is_dnc_registered("+17165551234")) is True


def test_clean_number_is_allowed(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    client = _client(get_return=_resp(200, {"on_registry": False}))
    with patch("app.core.dnc.httpx.AsyncClient", return_value=client), \
         patch("app.core.dnc.DatabaseManager", _no_cache_db()):
        assert asyncio.run(dnc.is_dnc_registered("+17165551234")) is False


def test_provider_error_fails_open(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    client = _client(get_side_effect=RuntimeError("provider down"))
    with patch("app.core.dnc.httpx.AsyncClient", return_value=client), \
         patch("app.core.dnc.DatabaseManager", _no_cache_db()):
        assert asyncio.run(dnc.is_dnc_registered("+17165551234")) is False  # never raises, not blocked


def test_non_200_fails_open(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    client = _client(get_return=_resp(503, {}))
    with patch("app.core.dnc.httpx.AsyncClient", return_value=client), \
         patch("app.core.dnc.DatabaseManager", _no_cache_db()):
        assert asyncio.run(dnc.is_dnc_registered("+17165551234")) is False


def test_fresh_cache_hit_skips_provider(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    db = MagicMock()
    db.get_state = AsyncMock(return_value={"registered": True, "ts": time.time() - 3600})  # 1h old
    db.set_state = AsyncMock()
    with patch("app.core.dnc.httpx.AsyncClient") as client_cls, \
         patch("app.core.dnc.DatabaseManager", db):
        result = asyncio.run(dnc.is_dnc_registered("+17165551234"))
    assert result is True
    client_cls.assert_not_called()       # served from cache, no lookup


def test_expired_cache_triggers_fresh_lookup(monkeypatch):
    monkeypatch.setenv("DNC_SCRUB_API_KEY", "k"); monkeypatch.setenv("DNC_SCRUB_URL", "https://dnc.test/lookup")
    db = MagicMock()
    stale = time.time() - (dnc.DNC_CACHE_TTL_DAYS + 1) * 86400
    db.get_state = AsyncMock(return_value={"registered": True, "ts": stale})
    db.set_state = AsyncMock()
    client = _client(get_return=_resp(200, {"on_registry": False}))
    with patch("app.core.dnc.httpx.AsyncClient", return_value=client), \
         patch("app.core.dnc.DatabaseManager", db):
        result = asyncio.run(dnc.is_dnc_registered("+17165551234"))
    assert result is False               # fresh lookup overrode the stale cache
    client.get.assert_awaited_once()


def test_dialer_blocks_on_registry_hit(monkeypatch):
    """trigger_retell_call must skip when is_dnc_registered is True (Retell env present)."""
    from app.skills import outbound_dialer
    monkeypatch.setenv("RETELL_API_KEY", "k"); monkeypatch.setenv("RETELL_FROM_NUMBER", "+1"); monkeypatch.setenv("RETELL_AGENT_ID", "a")
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)), \
         patch("app.core.dnc.is_dnc_registered", AsyncMock(return_value=True)):
        result = asyncio.run(outbound_dialer.trigger_retell_call("+17165551234", {}))
    assert result["skipped"] is True
    assert "National DNC Registry" in result["error"]
