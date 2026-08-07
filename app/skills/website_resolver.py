"""Resolve the WEBSITE for a licence-registry lead — ADR-0014 seam 2.

Licence registries (WA L&I, OR CCB) give a business name, a legally-named
principal, an address and a phone at ~100% fill. They give **no domain**, and
`enrich_lead_lite` returns immediately when a lead has no `url`
(light_enrich.py:1046) — so registry leads never reach ad-signal detection,
email extraction or owner verification at all. Resolving a domain is the single
step that opens all three.

Shape deliberately mirrors `owner_finder`: a waterfall resolving ONE field,
each tier wrapped so a failure never raises, cheapest source first. It is the
same pattern for a different field, not a new abstraction (CLAUDE.md
extension-first rule).

## Why verification is the hard part, not discovery

Measured live 2026-08-05 over 15 real OR CCB leads, guessing domains from the
business name and accepting a name match:

  · 87% "resolved" to a live page
  · **7% were actually the right company**

The failures were not near-misses, they were *other companies with the same
name in other states*: `cedarcreekconstruction.com` is a Pennsylvania firm
(area code 610) and `brightconstruction.com` resolves to Michigan/Texas/New
Jersey numbers. Attaching one of those to an Oregon lead would feed a
stranger's homepage into ad-signal detection and email extraction — fabricated
data on a lead Nova would then call.

So the rule here matches owner_finder's: **a miss must always beat a confident
wrong answer.** Discovery is cheap and generous; acceptance is strict.

## The acceptance rule: the registry phone, on the page. Nothing else.

The phone comes from a legal record at ~100% fill, so finding it printed on a
candidate page is decisive in a way no name or geography match is.

Two weaker rules were built, measured against real leads, and deleted — the
reasoning is kept in `verify_page` so nobody rebuilds them:

  · name + city         -> accepted the Pennsylvania Cedar Creek for an Oregon
                           lead. Oregon has towns called Boring, Sandy and
                           Oregon City; "city" matches almost any page.
  · name + "city, ST"   -> fired on 0 of 20 real leads over two runs. A rule
                           that never fires is noise, and an untriggered accept
                           path is just latent false-positive risk.

Measured hit rate of what shipped, over 20 real OR CCB leads: **10%**, with no
observed false positives. Low, and that is the honest number — many small
contractors simply have no website. 10% of the ~3,900 in-ICP Portland-metro
rows is still several hundred domains, for free.
"""
import os
import re
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10.0
_SERP_TIMEOUT = 20.0

# Only leads worth a rationed search reach SerpAPI. Mirrors
# owner_finder.SERP_SCORE_THRESHOLD — same quota, same bar.
SERP_SCORE_THRESHOLD = 70.0

_EMPTY = {"website": "", "domain": "", "source": "", "confidence": 0.0,
          "evidence": ""}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Legal-form tokens carry no signal in a domain guess.
_LEGAL = {"LLC", "L.L.C", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO",
          "COMPANY", "LP", "LLP", "PLLC", "LTD", "PC", "PS"}

# Trailing words common enough that dropping them yields a plausible second
# guess ("CEDAR CREEK CONSTRUCTION" -> cedarcreek.com).
_GENERIC_TAIL = {"CONSTRUCTION", "BUILDERS", "BUILDER", "REMODELING",
                 "CONTRACTING", "CONTRACTORS", "HOMES", "SERVICES", "GROUP"}

# Parked / unconfigured / for-sale pages. All observed live during the
# 2026-08-05 probe except where noted — `namebright` and `afternic` are the
# registrar landers that returned HTTP 200 with a "Coming Soon" title.
_PARKED_MARKERS = (
    "domain is for sale", "buy this domain", "this domain may be for sale",
    "is for sale", "parked free", "domain parking", "godaddy.com/forsale",
    "hugedomains", "sedoparking", "afternic", "namebright", "coming soon",
    "under construction", "website coming soon", "default web page",
    "a websitebuilder website", "squarespace.com/parked",
    "future home of something quite cool", "welcome to nginx", "apache2 ubuntu",
    "this site can't be reached",
)

# Never accept a directory/aggregator as "the business's website". Reuses the
# same judgement as lead_validator's off-ICP domain rules; kept local and
# explicit because a false accept here is a fabricated field.
_NON_BUSINESS_HOSTS = (
    "yelp.", "bbb.org", "facebook.", "linkedin.", "instagram.", "youtube.",
    "twitter.", "x.com", "indeed.", "mapquest", "yellowpages", "manta.com",
    "buildzoom", "houzz.", "angi.", "angieslist", "thumbtack", "porch.com",
    "birdeye", "nextdoor", "chamberofcommerce", "dnb.com", "bizapedia",
    "opencorporates", "zoominfo", "apollo.io", "glassdoor", "ziprecruiter",
    "trustpilot", "yellowbook", "local.com", "superpages", "citysearch",
    "expertise.com", "homeadvisor", "networx", "craigslist", "wikipedia.",
    "ccb.state.or.us", "lni.wa.gov", "cslb.ca.gov", "google.", "bing.",
    "duckduckgo", "amazon.", "pinterest.", "tiktok.", "yellow.place",
)

_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def _normalize_phone(raw: str) -> str:
    """Bare 10/11-digit US phone -> E.164, else ''. Local copy so this module
    stays importable without pulling in lead_gen_v3's httpx client."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01":
        return ""
    return "+1" + digits


def _name_tokens(business: str) -> list:
    """Distinctive lowercase tokens from a business name."""
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", (business or "").upper())
    return [t.lower() for t in cleaned.split()
            if t not in _LEGAL and len(t) > 2]


def candidate_domains(business: str) -> list:
    """Free domain guesses from a business name, most specific first.

    Generous on purpose — acceptance is decided by _verify_candidate, not here.
    """
    cleaned = re.sub(r"[^A-Za-z0-9 &]", " ", (business or "").upper())
    toks = [t for t in cleaned.split() if t and t not in _LEGAL and t != "&"]
    if not toks:
        return []
    stems = ["".join(t.lower() for t in toks)]
    if len(toks) > 1:
        stems.append("-".join(t.lower() for t in toks))
        if toks[-1] in _GENERIC_TAIL and len(toks) > 2:
            stems.append("".join(t.lower() for t in toks[:-1]))
    out, seen = [], set()
    for s in stems:
        if 3 <= len(s) <= 40 and s not in seen:
            seen.add(s)
            out.append(f"{s}.com")
    return out[:3]


def is_non_business_host(url: str) -> bool:
    try:
        host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    except Exception:
        return True
    return any(marker in host for marker in _NON_BUSINESS_HOSTS)


def _page_phones(text: str) -> set:
    found = set()
    for m in _PHONE_RE.finditer(text or ""):
        n = _normalize_phone(m.group(0))
        if n:
            found.add(n)
    return found


def verify_page(html: str, business: str, phone: str) -> dict:
    """Decide whether `html` really belongs to this business.

    Returns {"confidence": 0.0 or 0.95, "evidence": str}. Pure and synchronous
    so the acceptance rule is directly testable against real captured pages.
    """
    if not html:
        return {"confidence": 0.0, "evidence": "empty response"}
    body = _TAG_RE.sub(" ", html)
    low = body.lower()
    text = re.sub(r"<[^>]+>", " ", body)

    title_m = _TITLE_RE.search(html)
    title = (title_m.group(1).strip() if title_m else "")

    for marker in _PARKED_MARKERS:
        if marker in low or marker in title.lower():
            return {"confidence": 0.0, "evidence": f"parked/placeholder ({marker!r})"}
    # A live business homepage has a title and some prose. The 2026-08-05 probe
    # found several registrar landers returning 200 with an empty <title> and
    # no text at all.
    if not title.strip() and len(text.split()) < 40:
        return {"confidence": 0.0, "evidence": "no title and almost no content"}

    e164 = _normalize_phone(phone)
    if e164 and e164 in _page_phones(text):
        return {"confidence": 0.95,
                "evidence": f"registry phone {e164} present on page"}

    # NAME SIMILARITY IS NOT ACCEPTED, ON PURPOSE.
    #
    # Two weaker rules were built, measured against real leads, and deleted:
    #
    #   · name tokens + city          -> accepted the PENNSYLVANIA Cedar Creek
    #                                    Construction for an Oregon lead. Oregon
    #                                    has towns called Boring, Sandy and
    #                                    Oregon City; "city" matches any page.
    #   · name tokens + "city, ST"    -> fired on 0 of 20 real leads across two
    #                                    runs. A rule that never fires is noise,
    #                                    not signal, and an untriggered accept
    #                                    path is just latent false-positive risk.
    #
    # What remains is the one signal that is genuinely decisive: the phone from
    # the licence record, printed on the page. Everything else is a miss, and a
    # miss is always cheaper than attaching a stranger's homepage to a lead
    # Nova is about to call.
    toks = _name_tokens(business)
    if toks and all(t in low for t in toks):
        return {"confidence": 0.0,
                "evidence": "name matches but the registry phone is absent — "
                            "cannot distinguish this from a same-named "
                            "business elsewhere"}
    return {"confidence": 0.0, "evidence": "no registry phone on page"}


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        r = await client.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True,
                             headers={"User-Agent": _UA})
    except Exception:
        return None
    if r.status_code != 200 or not r.text:
        return None
    # A redirect off-host to a directory is not this business's site.
    if is_non_business_host(str(r.url)):
        return None
    return r.text


async def _serpapi_candidates(business: str, city: str, state: str,
                              score: float) -> list:
    """Rationed SerpAPI lookup for domains guessing cannot reach.

    Shares `owner_finder`'s monthly counter — SerpAPI's 250/month is ONE pool
    across discovery, owner_finder and this module, so a private counter here
    would silently overrun the real cap.
    """
    # Defaults OFF. SerpAPI's 250/month is a shared pool that owner_finder's
    # decision-maker fallback also draws on, and the hunt lane runs hourly at
    # 5 leads a run — enabled by default this would drain a month of quota in
    # about two days and starve the owner lookups. Turned on deliberately or
    # not at all.
    if os.getenv("WEBSITE_RESOLUTION_SERPAPI", "0") != "1":
        return []
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or not business:
        return []
    if score < SERP_SCORE_THRESHOLD:
        return []
    from app.skills.owner_finder import (
        _ration_check_and_increment, SERPAPI_MONTHLY_CAP,
    )
    if not await _ration_check_and_increment(
            "owner_finder:serp_monthly", SERPAPI_MONTHLY_CAP, "month"):
        logger.info("[WEBSITE] SerpAPI monthly cap reached, skipping")
        return []
    where = " ".join(p for p in (city, state) if p)
    try:
        async with httpx.AsyncClient(timeout=_SERP_TIMEOUT) as client:
            resp = await client.get("https://serpapi.com/search", params={
                "q": f'"{business}" {where}'.strip(),
                "api_key": api_key, "engine": "google", "num": 8,
            })
        if resp.status_code != 200:
            return []
        results = resp.json().get("organic_results", []) or []
    except Exception as e:
        logger.debug(f"[WEBSITE] SerpAPI lookup failed for {business}: {e}")
        return []
    out, seen = [], set()
    for res in results:
        link = (res.get("link") or "").strip()
        if not link.startswith("http") or is_non_business_host(link):
            continue
        host = link.split("//", 1)[-1].split("/", 1)[0].lower()
        if host in seen:
            continue
        seen.add(host)
        out.append(f"https://{host}")
    return out[:5]


async def resolve_website(business: str, phone: str = "", city: str = "",
                          state: str = "", score: float = 0.0) -> dict:
    """Find and VERIFY this business's website. Never raises.

    Returns {website, domain, source, confidence, evidence}; `website` is ""
    when nothing could be verified — which is the correct, common outcome.

    Kill switch: WEBSITE_RESOLUTION_ENABLED=0.
    """
    if os.getenv("WEBSITE_RESOLUTION_ENABLED", "1") != "1":
        return dict(_EMPTY)
    if not business:
        return dict(_EMPTY)

    best = dict(_EMPTY)
    try:
        async with httpx.AsyncClient(verify=True) as client:
            # ── Tier 1: free guesses. ~7% verified, zero marginal cost, and
            # every hit here is one SerpAPI call not spent.
            for domain in candidate_domains(business):
                for scheme in ("https://", "http://"):
                    html = await _fetch(client, scheme + domain)
                    if html is None:
                        continue
                    v = verify_page(html, business, phone)
                    if v["confidence"] > best["confidence"]:
                        best = {"website": scheme + domain, "domain": domain,
                                "source": "domain_guess",
                                "confidence": v["confidence"],
                                "evidence": v["evidence"]}
                    if best["confidence"] >= 0.95:
                        logger.info(f"[WEBSITE] {business} -> {best['website']} "
                                    f"(guess, {best['evidence']})")
                        return best
                    break        # https answered; no need to retry http

            # ── Tier 2: rationed search, only for leads worth the quota.
            for url in await _serpapi_candidates(business, city, state, score):
                html = await _fetch(client, url)
                if html is None:
                    continue
                v = verify_page(html, business, phone)
                if v["confidence"] > best["confidence"]:
                    best = {"website": url,
                            "domain": url.split("//", 1)[-1].split("/", 1)[0],
                            "source": "serpapi",
                            "confidence": v["confidence"],
                            "evidence": v["evidence"]}
                if best["confidence"] >= 0.95:
                    break
    except Exception as e:
        logger.debug(f"[WEBSITE] resolution failed for {business}: {e}")
        return dict(_EMPTY)

    if best["website"]:
        logger.info(f"[WEBSITE] {business} -> {best['website']} "
                    f"({best['source']}, conf {best['confidence']}, "
                    f"{best['evidence']})")
    else:
        logger.debug(f"[WEBSITE] {business}: no domain verified")
    return best
