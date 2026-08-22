"""The bot-wall detector that was discarding real prospect sites (2026-08-22).

Measured against every reachable prospect website in production: a bare
"captcha" substring discarded **9 of 10**. All ten returned HTTP 200 with real
content. The match was invariably an attribute on the business's own contact
form:

    id="1869027111" captcha="true" data-captcha-position="bottomleft"

Worse than a random 90% loss, because a contact form is exactly what a GOOD
contractor site has — the detector preferentially destroyed the best prospects.

Everything downstream of `_fetch_page` fails open, so nothing ever raised:
`build_dossier` returned {} (icebreaker 0/10), `contact_waterfall` found no
owner titles (0/10), and the light_enrich crawl found nothing. Four separate
symptoms, one cause, and no error anywhere.

Same shape as the Houzz ad-signal false positive: a detector that fires on
almost everything is not a detector.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skills.light_enrich import (  # noqa: E402
    _HARD_BLOCK_SIGNALS,
    _WEAK_BLOCK_MAX_CHARS,
    _WEAK_BLOCK_SIGNALS,
    _is_blocked,
)

# The exact markup that broke it, from a real prospect's contact form.
_REAL_FORM = (
    '<div class="dmform default native-inputs" data-element-type="dContactUsRespId" '
    'id="1869027111" captcha="true" data-captcha-position="bottomleft" '
    'data-captcha-message="VGhpcyBzaXRlIGlz">'
)


def _real_page(extra: str = "", size: int = 60_000) -> str:
    """A full contractor site: lots of content, and a contact form."""
    body = ("<p>We build custom homes across the Puget Sound region. "
            "Kitchen and bath remodeling, additions, design-build.</p>") * 400
    return ("<html><head><title>Copper Valley Construction</title></head><body>"
            + body + _REAL_FORM + extra + "</body></html>").lower()[:max(size, 20_000)]


def _interstitial(marker: str) -> str:
    """A genuine challenge page: it IS the response, and it is tiny."""
    return ("<html><head><title>just a moment...</title></head><body>"
            f"<div>{marker}</div></body></html>").lower()


# ── must NOT block: real sites ──────────────────────────────────────────────

def test_a_real_site_with_a_contact_form_captcha_is_not_blocked():
    """The exact 9-of-10 failure. This is the whole point of the change."""
    page = _real_page()
    assert "captcha" in page, "fixture must contain the trigger to be meaningful"
    assert _is_blocked(page) is False


def test_a_large_page_is_never_blocked_by_a_generic_word_alone():
    for weak in _WEAK_BLOCK_SIGNALS:
        page = _real_page(extra=f"<span>{weak}</span>")
        assert len(page) > _WEAK_BLOCK_MAX_CHARS
        assert _is_blocked(page) is False, f"{weak!r} blocked a full page"


def test_the_smallest_real_site_measured_still_passes():
    """The smallest reachable prospect site was 19KB; the cutoff is 12KB."""
    page = _real_page(size=19_000)
    assert len(page) > _WEAK_BLOCK_MAX_CHARS
    assert _is_blocked(page) is False


# ── must block: genuine interstitials ───────────────────────────────────────

def test_hard_signals_block_at_any_size():
    for sig in _HARD_BLOCK_SIGNALS:
        small = _interstitial(sig)
        assert _is_blocked(small) is True, f"{sig!r} missed on a small page"
        big = _real_page(extra=f"<div>{sig}</div>")
        assert _is_blocked(big) is True, f"{sig!r} missed on a large page"


def test_a_small_challenge_page_with_a_captcha_is_still_blocked():
    """Narrowing the rule must not blind it to the real thing."""
    for weak in _WEAK_BLOCK_SIGNALS:
        page = _interstitial(weak).replace("just a moment...", "verify")
        assert len(page) <= _WEAK_BLOCK_MAX_CHARS
        assert _is_blocked(page) is True, f"{weak!r} missed on an interstitial"


def test_an_ordinary_page_with_no_signals_passes():
    assert _is_blocked(_real_page().replace("captcha", "contact")) is False


def test_weak_and_hard_lists_are_disjoint():
    """A signal in both lists would silently get hard treatment."""
    assert not (set(_HARD_BLOCK_SIGNALS) & set(_WEAK_BLOCK_SIGNALS))
