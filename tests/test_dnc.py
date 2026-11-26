"""Tests for the DNC/consent gate on the outbound calling lane."""
import asyncio
from unittest.mock import patch, AsyncMock

from app.core import dnc


import pytest


# ── canonicalisation ────────────────────────────────────────────────────────
# REPLACES the old test_normalize, which asserted the DEFECT as correct:
#     assert dnc._normalize("(323) 555-0102") == "3235550102"
#     assert dnc._normalize("+1323 555 0102") == "+13235550102"
# Those are the SAME number resolving to two different keys. The test passed,
# so the bypass below shipped and survived every run of the suite.

_E164 = "+13235550102"


@pytest.mark.parametrize("raw", [
    "+13235550102",
    "3235550102",
    "(323) 555-0102",
    "13235550102",
    "323-555-0102",
    "+1 (323) 555-0102",
    "  +1323 555 0102  ",
    "1 (323) 555-0102",
])
def test_every_real_world_format_canonicalises_to_one_key(raw):
    assert dnc._normalize(raw) == _E164, (
        f"{raw!r} produced a different suppression key — stored and queried "
        f"forms must agree or the DNC gate can be bypassed"
    )


@pytest.mark.parametrize("junk", ["", "   ", "abc", "n/a", "123", "ext 456", "+", "-"])
def test_unresolvable_input_yields_no_key(junk):
    """"" is what makes is_suppressed fail CLOSED — see the test below."""
    assert dnc._normalize(junk) == ""


def test_normalize_handles_none():
    assert dnc._normalize(None) == ""


def test_empty_number_is_suppressed():
    assert asyncio.run(dnc.is_suppressed("")) is True
    assert asyncio.run(dnc.is_suppressed(None)) is True


def test_clean_number_not_suppressed():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[])):
        assert asyncio.run(dnc.is_suppressed("+13235550102")) is False


def test_listed_number_is_suppressed_regardless_of_formatting():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=["3235550102"])):
        assert asyncio.run(dnc.is_suppressed("(323) 555-0102")) is True


# ── THE REGRESSION: store one format, query every other ─────────────────────
# The test above could not catch the bypass, because "3235550102" and
# "(323) 555-0102" already normalised identically under the old code. The real
# defect only appeared across the +1 boundary. Measured before the fix, with
# the E.164 form the Retell webhook actually writes (app/main.py:1124):
#     stored '+13235550102' -> is_suppressed('3235550102')     = False  BYPASS
#     stored '+13235550102' -> is_suppressed('(323) 555-0102') = False  BYPASS
#     stored '+13235550102' -> is_suppressed('13235550102')    = False  BYPASS
#     stored '+13235550102' -> is_suppressed('323-555-0102')   = False  BYPASS
# 4 of 6 formats were dialable despite being suppressed.

_QUERY_FORMS = ["+13235550102", "3235550102", "(323) 555-0102", "13235550102",
                "323-555-0102", "+1 (323) 555-0102", "1 (323) 555-0102"]


@pytest.mark.parametrize("stored", ["+13235550102", "3235550102", "(323) 555-0102"])
@pytest.mark.parametrize("queried", _QUERY_FORMS)
def test_suppression_matches_across_every_stored_and_queried_format(stored, queried):
    """Every (stored, queried) pair of the same number must match.

    Includes stored forms that are NOT E.164 — a Sheets/backup restore, a CSV
    import, a legacy row predating normalisation, or a future manual DNC-entry
    UI can all put a non-E.164 value on the list.
    """
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[stored])):
        assert asyncio.run(dnc.is_suppressed(queried)) is True, (
            f"DNC BYPASS: stored {stored!r} did not suppress {queried!r}"
        )


def test_a_different_number_is_still_dialable():
    """Canonicalisation must not over-match into blocking everyone."""
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=["+13235550102"])):
        assert asyncio.run(dnc.is_suppressed("+12065550111")) is False


@pytest.mark.parametrize("junk", ["abc", "n/a", "123", "ext 456"])
def test_unresolvable_number_fails_closed(junk):
    """Fail-closed is preserved AND extended. "123" previously produced a key
    that matched nothing and was therefore DIALABLE; it is now blocked."""
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[])):
        assert asyncio.run(dnc.is_suppressed(junk)) is True


def test_round_trip_add_then_check_across_formats():
    """End-to-end through the real writer and the real reader, no mocking of
    either — add_suppression stores, is_suppressed matches, in any format."""
    store = {}
    with patch.object(dnc.DatabaseManager, "get_state",
                      AsyncMock(side_effect=lambda k, d=None: store.get(k, d))), \
         patch.object(dnc.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: store.__setitem__(k, v))):
        assert asyncio.run(dnc.add_suppression("(323) 555-0102", reason="opt-out")) is True
        for q in _QUERY_FORMS:
            assert asyncio.run(dnc.is_suppressed(q)) is True, f"stored via add_suppression, {q!r} not matched"


def test_fails_closed_on_db_error():
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(side_effect=RuntimeError("db down"))):
        assert asyncio.run(dnc.is_suppressed("+13235550102")) is True


def test_add_suppression_persists_normalized():
    # Capture set_state PER KEY: the app's background log-flush concurrently
    # calls set_state('agent_logs', ...), which would clobber a single global
    # capture. Keying by state-key isolates the DNC write we're asserting on.
    saved = {}
    with patch.object(dnc.DatabaseManager, "get_state", AsyncMock(return_value=[])), \
         patch.object(dnc.DatabaseManager, "set_state",
                      AsyncMock(side_effect=lambda k, v: saved.__setitem__(k, v))):
        ok = asyncio.run(dnc.add_suppression("(323) 555-0102", reason="opt-out"))
    assert ok is True
    # Canonical E.164, not the old digits-only key. This is the write half of
    # the fix — store and query must agree, so BOTH sides canonicalise.
    assert saved[dnc._DNC_KEY] == ["+13235550102"]


def test_dialer_blocks_suppressed_number(monkeypatch):
    monkeypatch.setenv("RETELL_API_KEY", "k")
    monkeypatch.setenv("RETELL_FROM_NUMBER", "+15550000000")
    monkeypatch.setenv("RETELL_AGENT_ID", "a")
    from app.skills import outbound_dialer
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=True)):
        res = asyncio.run(outbound_dialer.trigger_retell_call("+13235550102", {}))
    assert res["success"] is False
    assert "DNC" in res["error"]
