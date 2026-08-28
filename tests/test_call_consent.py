"""Prior-express-consent gate for AI-voice calls (app/core/call_consent.py).

The DNC gate answers "did they ask us to stop?". For an ARTIFICIAL voice that
is the wrong question. FCC 24-17 (Feb 2024) holds AI-generated voices are
"artificial" under the TCPA, so a prerecorded/AI call needs PRIOR EXPRESS
CONSENT **regardless of the B2B exemption**. Damages: $500 per call, trebled to
$1,500 for a wilful violation.

And the B2B landline carve-out cannot be leaned on here: of the 23 numbers
queued in production on 2026-08-06, **20 classified as FIXED_OR_MOBILE** —
US number portability makes landline-vs-cell undeterminable from the number.

So this gate fails CLOSED, exactly like the DNC one, and these tests pin that.
`dnc.py` itself is NOT modified — suppression and consent are separate
questions and both must pass.
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.core import call_consent as cc


@pytest.fixture
def store(monkeypatch):
    """In-memory stand-in for DatabaseManager's state store."""
    data = {}

    async def _get(key, default=None):
        return data.get(key, default)

    async def _set(key, value):
        data[key] = value

    monkeypatch.setattr(cc.DatabaseManager, "get_state", AsyncMock(side_effect=_get))
    monkeypatch.setattr(cc.DatabaseManager, "set_state", AsyncMock(side_effect=_set))
    return data


async def _allow_dnc():
    async def _not_suppressed(_phone):
        return False
    return patch("app.core.dnc.is_suppressed", _not_suppressed)


# ── fail-closed by default ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_consent_means_no_call(store):
    assert await cc.has_call_consent("+15035550102") is False


@pytest.mark.asyncio
async def test_empty_number_is_refused(store):
    assert await cc.has_call_consent("") is False
    assert await cc.has_call_consent(None) is False


@pytest.mark.asyncio
async def test_lookup_error_blocks_the_call(monkeypatch):
    """A DB hiccup must never open the gate."""
    monkeypatch.setattr(cc.DatabaseManager, "get_state",
                        AsyncMock(side_effect=RuntimeError("db down")))
    assert await cc.has_call_consent("+15035550102") is False


# ── recording consent ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_records_and_finds_consent(store):
    ok = await cc.record_call_consent("+15035550102", "ig_dm_reply",
                                      detail="'yeah give me a call tomorrow'",
                                      actor="mark")
    assert ok is True
    assert await cc.has_call_consent("+15035550102") is True


@pytest.mark.asyncio
async def test_consent_carries_its_provenance(store):
    """Undocumented consent is worthless in the dispute where it matters."""
    await cc.record_call_consent("+15035550102", "ig_dm_reply",
                                 detail="'sure, call me'", actor="mark")
    rec = await cc.consent_record("+15035550102")
    assert rec["source"] == "ig_dm_reply"
    assert rec["detail"] == "'sure, call me'"
    assert rec["actor"] == "mark"
    assert rec["recorded_at"].endswith("Z")


@pytest.mark.asyncio
async def test_unrecognised_source_is_refused(store):
    """A source we cannot point at later is not evidence."""
    assert await cc.record_call_consent("+15035550102", "vibes") is False
    assert await cc.has_call_consent("+15035550102") is False


@pytest.mark.asyncio
async def test_scraped_from_a_licence_register_is_not_consent(store):
    """The whole point: a published business number is NOT permission to send
    an artificial voice at it."""
    assert await cc.record_call_consent("+15035550102", "licence_registry") is False
    assert await cc.has_call_consent("+15035550102") is False


@pytest.mark.asyncio
async def test_empty_number_never_recorded(store):
    assert await cc.record_call_consent("", "ig_dm_reply") is False


@pytest.mark.asyncio
async def test_matches_across_country_code_formatting(store):
    """'+15035550102' and '5035550102' are the same line written two ways."""
    await cc.record_call_consent("+15035550102", "inbound_call")
    assert await cc.has_call_consent("5035550102") is True
    assert await cc.has_call_consent("(503) 555-0102") is True


# ── the combined gate ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_refuses_an_unknown_line_type_without_consent(store):
    """The common case: a geographic number we cannot prove is a landline."""
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is False
    assert "UNKNOWN" in why


@pytest.mark.asyncio
async def test_verified_landline_needs_no_consent(store):
    """CORRECTION 2026-08-06: an earlier version required consent for every
    number. That was too broad. §227(b)(1)(B) reaches only a RESIDENTIAL line,
    and (A)(iii) reaches cellular / called-party-charged services — so a
    verified business landline is outside both, and blocking it was wrong."""
    await cc.record_line_type("+15035550102", cc.LINE_LANDLINE, source="carrier_lookup")
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is True
    assert "landline" in why


@pytest.mark.asyncio
async def test_verified_mobile_still_requires_consent(store):
    """(A)(iii) covers cellular regardless of business use."""
    await cc.record_line_type("+15035550102", cc.LINE_MOBILE, source="carrier_lookup")
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is False
    assert "mobile" in why


@pytest.mark.asyncio
async def test_toll_free_requires_consent_despite_being_a_business_line(store):
    """Counterintuitive but statutory: (A)(iii) also covers 'any service for
    which the called party is charged for the call'. Toll-free is the WORST
    AI-call candidate, not the safest."""
    for tf in ("+18885550101", "+18005550101", "+18445550101"):
        assert await cc.get_line_type(tf) == cc.LINE_TOLL_FREE
        with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)):
            allowed, why = await cc.ai_call_allowed(tf)
        assert allowed is False, tf
        assert "called party is charged" in why


@pytest.mark.asyncio
async def test_line_type_is_never_guessed_from_a_geographic_prefix(store):
    """US number portability killed prefix inference. Unknown must stay
    unknown rather than optimistically resolving to landline."""
    assert await cc.get_line_type("+15035550102") == cc.LINE_UNKNOWN
    assert await cc.record_line_type("+15035550102", "probably_landline") is False


@pytest.mark.asyncio
async def test_gate_allows_with_consent(store):
    await cc.record_call_consent("+15035550102", "ig_dm_reply", actor="mark")
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=False)):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is True
    assert "ig_dm_reply" in why


@pytest.mark.asyncio
async def test_suppression_beats_consent(store):
    """An opt-out overrides any earlier yes. Suppression always wins."""
    await cc.record_call_consent("+15035550102", "ig_dm_reply", actor="mark")
    with patch("app.core.dnc.is_suppressed", AsyncMock(return_value=True)):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is False
    assert "DNC" in why or "opt-out" in why


@pytest.mark.asyncio
async def test_dnc_lookup_failure_blocks(store):
    await cc.record_call_consent("+15035550102", "ig_dm_reply", actor="mark")
    with patch("app.core.dnc.is_suppressed", AsyncMock(side_effect=RuntimeError("x"))):
        allowed, why = await cc.ai_call_allowed("+15035550102")
    assert allowed is False


@pytest.mark.asyncio
async def test_gate_refuses_an_empty_number(store):
    allowed, why = await cc.ai_call_allowed("")
    assert allowed is False and "no phone" in why


def test_this_module_does_not_modify_dnc():
    """Owner instruction: extend the discipline, don't touch the proven gate."""
    import inspect

    from app.core import dnc
    src = inspect.getsource(cc)
    assert "def is_suppressed" not in src, "call_consent must not redefine the DNC gate"
    assert "add_suppression" not in src, "call_consent must not write to the DNC list"
    # It may READ it — that is the point of the combined gate.
    assert "is_suppressed" in src
    assert hasattr(dnc, "is_suppressed")
