"""Find a lead's social handles from its own website. RESEARCH ONLY.

## Why this exists

Instagram DM is the only first-touch channel OROVA has open. Email is closed
(AgentMail ToS §10 prohibits unsolicited messaging, and licence data carries no
addresses), and the phone lane is shelved. So the one path to a first
conversation is Mark sending DMs by hand.

He cannot do that without a handle, and a licence-registry lead has no website,
no email and no social — just a name, a phone and an address.

## What this module will NEVER do

**It sends nothing. It initiates nothing. It logs into nothing.**

That is not caution, it is the actual constraint. Instagram's API physically
cannot start a DM thread — verified from the tool definition, not from docs:

    INSTAGRAM_SEND_TEXT_MESSAGE — "Send a text message to an Instagram user via
    DM in an existing conversation. Cannot initiate new DM threads — a prior
    conversation must exist."

The recipient field needs a PSID that only exists once a conversation does.
Usernames do not work. There is no parameter that reaches a stranger.

So automation stops here, at research, by design — and that also matches the
owner playbook: "Instagram DM → Loom link → email follow-up. 5-10 per day
maximum." It was always a manual channel.

## The failure mode this guards against

Attaching the wrong Instagram account to a lead is worse than attaching none:
Mark would DM a stranger with a personalised message naming someone else's
company. Contractor sites routinely link their web designer's Instagram, a
supplier's, a trade body's, or a bare `instagram.com` icon with no handle at
all — all of which look identical to a naive scrape.

So a handle is only accepted when the page links it AND it survives the
rejection rules below.

## ⚠️ This module is only as correct as the WEBSITE it is handed

It attributes a handle to the *page it was given*. It cannot tell whether that
page is the right company — that is the caller's job, and it is not
theoretical. Live 2026-08-06, handing it "CEDAR CREEK CONSTRUCTION LLC" and the
site a naive name-guess produces returned `@cedarcreekconstruction.llc` with a
perfect name match — from a PENNSYLVANIA firm, for an Oregon lead. The
attribution was right; the input was wrong.

So callers must pass a website that was verified to belong to the business
(`website_resolver` accepts one only when the licence phone appears on the
page). Passing a guessed domain here produces a confident wrong handle, and a
DM to a stranger naming someone else's company.

## Measured

Over 10 real contractor sites, 2026-08-06: **7/10** yielded an attributable
handle. The 3 misses link no Instagram at all from their homepage — verified,
not assumed — so they are correct misses rather than extraction failures.
"""
import logging
import re
from typing import Optional
from urllib.parse import urlparse, unquote

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10.0
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_EMPTY = {"instagram": "", "facebook": "", "source": "", "confidence": 0.0,
          "evidence": ""}

# Instagram reserved paths and non-profile routes. A link to any of these is
# not a business profile.
_IG_RESERVED = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "about",
    "developer", "developers", "legal", "privacy", "terms", "directory",
    "web", "challenge", "oauth", "login", "signup", "emails", "session",
    "graphql", "api", "static", "images", "ads", "business", "creators",
    "help", "press", "blog", "download", "lite", "your_activity", "direct",
    "sharer", "share", "invites", "topics", "locations", "hashtag",
}

# Handles belonging to platforms, agencies and trade bodies that appear in
# contractor site footers. Messaging any of these reaches the wrong company.
_IG_NOT_THE_BUSINESS = {
    "instagram", "facebook", "meta", "houzz", "yelp", "angi", "angieslist",
    "homeadvisor", "thumbtack", "buildzoom", "porch", "nextdoor", "bbb_us",
    "wix", "squarespace", "godaddy", "wordpress", "shopify", "webflow",
    "duda", "weebly", "nahb", "nari_national", "buildertrend", "jobber",
    "housecallpro", "google", "youtube", "linkedin", "twitter", "tiktok",
    "pinterest", "trustpilot",
}

_IG_LINK_RE = re.compile(
    r"""https?://(?:www\.|m\.)?instagram\.com/([A-Za-z0-9._]{1,30})""",
    re.IGNORECASE)
_FB_LINK_RE = re.compile(
    r"""https?://(?:www\.|m\.|web\.)?facebook\.com/([A-Za-z0-9.\-]{1,60})""",
    re.IGNORECASE)
_FB_RESERVED = {"sharer", "share", "plugins", "tr", "dialog", "profile.php",
                "pages", "people", "groups", "events", "login", "help",
                "policies", "privacy", "terms", "business", "ads", "watch"}

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)


def _tokens(business: str) -> list:
    """Distinctive lowercase alphanumeric tokens from a business name."""
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", (business or "").lower())
    drop = {"llc", "inc", "corp", "co", "company", "ltd", "llp", "pllc",
            "the", "and", "of"}
    return [t for t in cleaned.split() if len(t) > 2 and t not in drop]


def extract_instagram_handles(html: str) -> list:
    """Every plausible Instagram PROFILE handle linked from this page.

    Reserved routes (/p/, /explore/, /reel/) and platform/agency handles are
    dropped here; whether a surviving handle belongs to THIS business is
    decided by `resolve_social`.
    """
    if not html:
        return []
    body = _SCRIPT_RE.sub(" ", html)
    out, seen = [], set()
    for raw in _IG_LINK_RE.findall(body):
        handle = unquote(raw).strip("/.").lower()
        if not handle or handle in seen:
            continue
        if handle in _IG_RESERVED or handle in _IG_NOT_THE_BUSINESS:
            continue
        # A bare digit-run is an internal id, not a business handle.
        if handle.isdigit():
            continue
        if len(handle) < 3:
            continue
        seen.add(handle)
        out.append(handle)
    return out


def extract_facebook_pages(html: str) -> list:
    if not html:
        return []
    body = _SCRIPT_RE.sub(" ", html)
    out, seen = [], set()
    for raw in _FB_LINK_RE.findall(body):
        page = unquote(raw).strip("/.").lower()
        if not page or page in seen or page in _FB_RESERVED or len(page) < 3:
            continue
        seen.add(page)
        out.append(page)
    return out


def score_handle(handle: str, business: str, domain: str = "") -> tuple:
    """(confidence, evidence) that `handle` is THIS business's account.

    A contractor site links its designer's Instagram as readily as its own, so
    a handle is only trusted when it demonstrably corresponds to the business:
    it echoes the business name, or it echoes the domain the page is served
    from. Otherwise it is reported at zero and the caller keeps nothing.
    """
    h = re.sub(r"[^a-z0-9]", "", (handle or "").lower())
    if not h:
        return 0.0, "empty handle"

    toks = _tokens(business)
    joined = "".join(toks)
    if joined and (h == joined or joined in h or h in joined):
        return 0.95, f"handle matches the business name ({handle!r})"

    host = re.sub(r"^www\.", "", (urlparse(domain).netloc or domain or "").lower())
    stem = re.sub(r"[^a-z0-9]", "", host.split(".")[0]) if host else ""
    if stem and (h == stem or stem in h or h in stem):
        return 0.9, f"handle matches the site's own domain ({handle!r})"

    # Most distinctive single word present is decent but not conclusive: a
    # supplier or franchise partner can share a word with the business.
    strong = [t for t in toks if len(t) >= 5]
    if strong and any(t in h for t in strong):
        return 0.6, f"handle shares a distinctive word with the name ({handle!r})"

    return 0.0, f"handle {handle!r} does not correspond to the business or domain"


async def resolve_social(business: str, website: str,
                         client: Optional[httpx.AsyncClient] = None) -> dict:
    """Find this business's own social handles from its own website.

    RESEARCH ONLY — fetches one public page and reads its links. Sends nothing,
    follows nothing, logs into nothing.

    Returns {instagram, facebook, source, confidence, evidence}; empty strings
    when nothing could be attributed to this business, which is the correct
    outcome far more often than not.
    """
    if not business or not website or not website.startswith("http"):
        return dict(_EMPTY)

    owns_client = client is None
    try:
        client = client or httpx.AsyncClient()
        try:
            resp = await client.get(website, timeout=_HTTP_TIMEOUT,
                                    follow_redirects=True,
                                    headers={"User-Agent": _UA})
        except Exception as e:
            logger.debug(f"[SOCIAL] fetch failed for {website}: {e}")
            return dict(_EMPTY)
        if resp.status_code != 200 or not resp.text:
            return dict(_EMPTY)

        html = resp.text
        best = dict(_EMPTY)
        for handle in extract_instagram_handles(html):
            conf, why = score_handle(handle, business, website)
            if conf > best["confidence"]:
                best = {"instagram": handle, "facebook": "",
                        "source": "website", "confidence": conf, "evidence": why}

        # Facebook is a weaker channel but the same page already gives it, so
        # it costs nothing. Only kept when the Instagram attribution held —
        # otherwise there is no evidence this page represents the business.
        if best["instagram"]:
            for page in extract_facebook_pages(html):
                conf, _ = score_handle(page, business, website)
                if conf >= 0.6:
                    best["facebook"] = page
                    break

        if best["instagram"]:
            logger.info(f"[SOCIAL] {business} -> @{best['instagram']} "
                        f"(conf {best['confidence']}, {best['evidence']})")
        else:
            logger.debug(f"[SOCIAL] {business}: no attributable handle on {website}")
        return best
    finally:
        if owns_client and client is not None:
            try:
                await client.aclose()
            except Exception:
                pass
