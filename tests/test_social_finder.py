"""Social-handle research for the manual DM channel (app/skills/social_finder.py).

Instagram DM is the only first-touch channel OROVA has open — email is closed
by ToS and the phone lane is shelved — and Mark cannot send one without a
handle. Registry leads have none.

Two hard constraints are asserted here, not just described:

  1. THE MODULE SENDS NOTHING. Instagram's API physically cannot start a DM
     thread, so automation stops at research by design. A test greps the
     module for send/DM/login surface area.
  2. A WRONG HANDLE IS WORSE THAN NONE. Contractor sites routinely link their
     web designer's Instagram, a supplier's, or a bare platform icon. Mark
     DMing a stranger with a message naming someone else's company is the
     failure this guards against.

Fixtures use the real link shapes found on live contractor sites 2026-08-06.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.skills import social_finder as sf
from app.skills.social_finder import (
    extract_facebook_pages, extract_instagram_handles, resolve_social,
    score_handle,
)


def _page(*links, extra=""):
    body = " ".join(f'<a href="{u}">x</a>' for u in links)
    return f"<html><body><footer>{body}</footer>{extra}</body></html>"


# ── extraction: profile links only ─────────────────────────────────────────

def test_extracts_a_plain_profile_handle():
    html = _page("https://www.instagram.com/vitanconstruction/")
    assert extract_instagram_handles(html) == ["vitanconstruction"]


@pytest.mark.parametrize("url", [
    "https://instagram.com/vitanconstruction",
    "https://www.instagram.com/vitanconstruction/",
    "http://m.instagram.com/vitanconstruction",
    "https://www.instagram.com/vitanconstruction/?hl=en",
])
def test_handle_survives_url_variants(url):
    assert "vitanconstruction" in extract_instagram_handles(_page(url))


@pytest.mark.parametrize("url", [
    "https://www.instagram.com/p/CxYzAbC123/",        # a post
    "https://www.instagram.com/reel/CxYzAbC123/",     # a reel
    "https://www.instagram.com/explore/tags/remodel/",
    "https://www.instagram.com/accounts/login/",
    "https://www.instagram.com/stories/someone/",
])
def test_reserved_routes_are_not_handles(url):
    assert extract_instagram_handles(_page(url)) == [], url


@pytest.mark.parametrize("handle", ["houzz", "yelp", "wix", "squarespace",
                                    "angi", "buildertrend", "instagram"])
def test_platform_and_agency_handles_are_dropped(handle):
    """A site's footer links its own builder/platform as readily as itself."""
    html = _page(f"https://www.instagram.com/{handle}/")
    assert extract_instagram_handles(html) == [], handle


def test_empty_html_is_safe():
    assert extract_instagram_handles("") == []
    assert extract_instagram_handles(None) == []


def test_scripts_are_stripped_before_matching():
    html = ("<html><body><script>var u='https://instagram.com/sometracker';</script>"
            "</body></html>")
    assert extract_instagram_handles(html) == []


# ── attribution: does the handle belong to THIS business? ──────────────────

def test_handle_matching_the_business_name_is_trusted():
    conf, why = score_handle("vitanconstruction", "VITAN CONSTRUCTION LLC")
    assert conf >= 0.9 and "business name" in why


def test_handle_matching_the_domain_is_trusted():
    conf, why = score_handle("hammerandhandbuilds", "HAMMER & HAND",
                             "https://hammerandhandbuilds.com")
    assert conf >= 0.9


def test_unrelated_handle_is_rejected():
    """The web designer's Instagram in the footer."""
    conf, why = score_handle("pixelcraftdesignstudio", "VITAN CONSTRUCTION LLC",
                             "https://vitanconstruction.com")
    assert conf == 0.0
    assert "does not correspond" in why


def test_legal_suffixes_do_not_block_a_match():
    assert score_handle("cedarcreekconstruction",
                        "CEDAR CREEK CONSTRUCTION LLC")[0] >= 0.9


def test_shared_word_alone_is_weak_not_conclusive():
    conf, _ = score_handle("seattleremodelsupply", "CEDAR REMODEL LLC")
    assert 0 < conf < 0.9, "a shared word must not be treated as proof"


# ── the resolver ───────────────────────────────────────────────────────────

def _client(html, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    c = MagicMock()
    c.get = AsyncMock(return_value=resp)
    c.aclose = AsyncMock()
    return c


@pytest.mark.asyncio
async def test_resolves_the_businesss_own_handle():
    html = _page("https://www.instagram.com/vitanconstruction/",
                 "https://www.facebook.com/vitanconstruction")
    with patch.object(sf.httpx, "AsyncClient",
                      return_value=_client(html)):
        out = await resolve_social("VITAN CONSTRUCTION LLC",
                                   "https://vitanconstruction.com")
    assert out["instagram"] == "vitanconstruction"
    assert out["facebook"] == "vitanconstruction"
    assert out["confidence"] >= 0.9
    assert out["source"] == "website"


@pytest.mark.asyncio
async def test_returns_nothing_when_only_an_unrelated_handle_is_present():
    """A miss must beat a DM to a stranger."""
    html = _page("https://www.instagram.com/pixelcraftdesignstudio/")
    with patch.object(sf.httpx, "AsyncClient", return_value=_client(html)):
        out = await resolve_social("VITAN CONSTRUCTION LLC",
                                   "https://vitanconstruction.com")
    assert out["instagram"] == ""
    assert out["confidence"] == 0.0


@pytest.mark.asyncio
async def test_picks_the_business_handle_over_the_agency_one():
    html = _page("https://www.instagram.com/pixelcraftdesignstudio/",
                 "https://www.instagram.com/vitanconstruction/")
    with patch.object(sf.httpx, "AsyncClient", return_value=_client(html)):
        out = await resolve_social("VITAN CONSTRUCTION LLC",
                                   "https://vitanconstruction.com")
    assert out["instagram"] == "vitanconstruction"


@pytest.mark.asyncio
async def test_facebook_is_only_kept_alongside_a_trusted_instagram():
    """Without an attributable IG handle there is no evidence the page
    represents this business, so its Facebook link is not trusted either."""
    html = _page("https://www.facebook.com/someoneelse")
    with patch.object(sf.httpx, "AsyncClient", return_value=_client(html)):
        out = await resolve_social("VITAN CONSTRUCTION LLC",
                                   "https://vitanconstruction.com")
    assert out["facebook"] == ""


@pytest.mark.asyncio
async def test_non_200_returns_empty():
    with patch.object(sf.httpx, "AsyncClient", return_value=_client("", 503)):
        out = await resolve_social("X CONSTRUCTION", "https://x.com")
    assert out["instagram"] == ""


@pytest.mark.asyncio
async def test_network_failure_is_swallowed():
    c = MagicMock()
    c.get = AsyncMock(side_effect=RuntimeError("boom"))
    c.aclose = AsyncMock()
    with patch.object(sf.httpx, "AsyncClient", return_value=c):
        out = await resolve_social("X CONSTRUCTION", "https://x.com")
    assert out["instagram"] == ""


@pytest.mark.asyncio
async def test_requires_a_website():
    assert (await resolve_social("X CONSTRUCTION", ""))["instagram"] == ""
    assert (await resolve_social("", "https://x.com"))["instagram"] == ""
    assert (await resolve_social("X", "not-a-url"))["instagram"] == ""


# ── the hard compliance line ───────────────────────────────────────────────

def test_module_has_no_sending_surface():
    """Instagram's API cannot initiate a DM thread, and this module must never
    pretend otherwise. Research only: no send, no DM, no login, no POST."""
    import ast
    import io
    import tokenize

    src = Path(sf.__file__).read_text(encoding="utf-8")

    # Examine CODE, not data. The module's rejection lists legitimately contain
    # the words "login" and "oauth" as Instagram paths to REJECT, and the
    # docstring discusses DMs in order to explain why none are sent. Tokenising
    # and dropping strings/comments is what separates "calls login()" from
    # "refuses to follow /login/".
    code_tokens = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            continue
        code_tokens.append(tok.string)
    code = " ".join(code_tokens).lower()

    for forbidden in ("send_message", "send_text", "sendmessage",
                      "direct_message", "login", "oauth", "post"):
        assert forbidden not in code, (
            f"social_finder gained a {forbidden!r} surface — it is research-only"
        )

    # And structurally: the only HTTP verb it may use is GET.
    tree = ast.parse(src)
    verbs = {node.attr for node in ast.walk(tree)
             if isinstance(node, ast.Attribute)
             and node.attr in {"get", "post", "put", "patch", "delete"}}
    assert verbs <= {"get"}, f"social_finder issues non-GET requests: {verbs}"
