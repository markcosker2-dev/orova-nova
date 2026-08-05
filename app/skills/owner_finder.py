"""Owner-name-FIRST resolver — public registries before free-text scraping.

Design (see vault/20-ops/sessions/2026-07-04-lead-engine-research.md, Job 3):
today's pipeline finds an owner name by regex-mining website text or DDG
snippets, which only works if the business happens to publish a name in a
matchable sentence. This module flips the order: look the business up in a
public registry that is legally required to name a real person FIRST, and
only fall back to text-mining when the registry has no hit.

Fallback chain (first hit wins, each step wrapped so a failure never raises):
    1. State-routed registry
         WA  -> WA L&I contractor licence registry on data.wa.gov (Socrata,
                no key, no quota). Replaced the WA SoS corporations API, which
                is anti-bot gated and never returned a name server-side.
         CA  -> CA Statement of Information, gated behind CA_SOS_API_KEY
                (free-tier cost UNCONFIRMED per research doc — default OFF)
         OR  -> OR registry HTML best-effort parse
         other/unknown -> OpenCorporates (needs OPENCORPORATES_API_KEY,
                rationed to 50/day)
    2. Website scrape (existing regex/JSON-LD path in lead_gen_v3, reused
       as-is — not reimplemented)
    3. SERP fallback (SerpAPI, needs SERPAPI_KEY, only for leads scoring
       above a threshold, rationed to ~250/month)

Every external key is optional; missing/unset keys skip that source cleanly.
A state_store cache (30-day TTL) avoids repeat lookups burning quota, and
day/month ration counters persist in state_store (mirrors worker.py's
daily_hunt_counter pattern, but SQLite-backed since this module has no
long-lived in-process globals to rely on across Render restarts).
"""
import os
import re
import time
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 8.0
_SERP_TIMEOUT = 20.0                         # SerpAPI runs a live Google search — slower
CACHE_TTL_SECONDS = 30 * 24 * 3600           # 30 days
OPENCORPORATES_DAILY_CAP = 50
SERPAPI_MONTHLY_CAP = 250

_EMPTY = {"owner": "", "title": "", "source": "", "confidence": 0.0}


def _cache_key(business: str, state: str) -> str:
    return f"owner_cache:{(business or '').strip().lower()}|{(state or '').strip().upper()}"


async def _get_db():
    """Import lazily to dodge any import-order issues / keep this module standalone-testable."""
    from app.core.database import DatabaseManager
    return DatabaseManager


async def _cache_get(business: str, state: str) -> Optional[dict]:
    try:
        db = await _get_db()
        entry = await db.get_state(_cache_key(business, state))
        if not entry or not isinstance(entry, dict):
            return None
        if time.time() - entry.get("_cached_at", 0) > CACHE_TTL_SECONDS:
            return None
        return entry.get("result")
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] cache read failed: {e}")
        return None


async def _cache_set(business: str, state: str, result: dict) -> None:
    try:
        db = await _get_db()
        await db.set_state(_cache_key(business, state), {"_cached_at": time.time(), "result": result})
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] cache write failed: {e}")


async def _ration_check_and_increment(counter_key: str, cap: int, period: str, amount: int = 1) -> bool:
    """Return True if under cap (and increments usage by `amount`).
    period: 'day' or 'month'. `amount` > 1 covers per-item quotas like
    Verifalia's, where one HTTP call charges one credit per email submitted.

    Persisted in state_store so the ration survives process restarts on
    Render's free tier, mirroring the intent of worker.py's daily counters.
    """
    try:
        db = await _get_db()
        now = time.localtime()
        bucket = f"{now.tm_year}-{now.tm_yday}" if period == "day" else f"{now.tm_year}-{now.tm_mon}"
        state = await db.get_state(counter_key) or {}
        if state.get("bucket") != bucket:
            state = {"bucket": bucket, "count": 0}
        if state["count"] + amount > cap:
            return False
        state["count"] += amount
        await db.set_state(counter_key, state)
        return True
    except Exception as e:
        # Bookkeeping error (e.g. DB briefly unavailable): fail OPEN. One extra
        # API call can't blow a 250/mo quota, whereas failing closed here would
        # zero out discovery/enrichment on any transient DB hiccup — far worse.
        logger.debug(f"[OWNER_FINDER] ration check failed for {counter_key}: {e} — proceeding")
        return True


def _is_plausible_name(text: str) -> bool:
    if not text or len(text) < 4 or len(text) > 50:
        return False
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Za-z'\-]+$", p) for p in parts):
        return False
    if not parts[0][0].isupper():
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1a — Washington L&I contractor licence registry (no key, open data)
# ═══════════════════════════════════════════════════════════════════════════
#
# Replaces the WA Secretary of State corporations search this function used to
# call. That host (ccfs-api.prod.sos.wa.gov) is anti-bot gated — verified live
# 2026-07-04 it answers "System verification in progress, please wait." to any
# non-browser client, and Render cannot run a browser — so the source was dead
# and shipped defaulted OFF behind WA_SOS_ENABLED. It never produced a name.
#
# WA L&I publishes licensed-contractor data on the state's Socrata open-data
# portal instead: no key, no quota, and a better fit than the SoS registry
# because it is contractor-specific rather than all corporations. Verified live
# 2026-07-25: 75,515 rows at status ACTIVE, and over a 1,000-row sample
# businessname / primaryprincipalname / phonenumber / address were each 100%
# populated.
#
# Only the principal's NAME is consumed here, to keep this function's contract
# unchanged. The same row also carries phone + full address, which is worth a
# follow-up seam (it would give the call lane a number and finally populate
# lead["state"]) but is deliberately out of scope for this change.
_WA_LNI_DATASET = "https://data.wa.gov/resource/m8qx-ubtq.json"

# Legal-form suffixes are noise when matching a licence record to a scraped
# business name ("ACME BUILDERS LLC" vs "Acme Builders"). Stripped from both
# sides before comparison.
_BIZ_SUFFIXES = {
    "LLC", "L.L.C", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO",
    "COMPANY", "LP", "LLP", "PLLC", "LTD", "PC", "PS", "AND", "&",
}


def _normalize_business(name: str) -> str:
    """Upper-case, strip punctuation and legal-form suffixes, collapse space."""
    cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", (name or "").upper())
    tokens = [t for t in cleaned.split() if t and t not in _BIZ_SUFFIXES]
    return " ".join(tokens)


def _person_from_principal(raw: str) -> str:
    """'POWER, GREGORY MARK JR' -> 'Gregory Power'.

    L&I stores principals surname-first in caps. Middle names and generational
    suffixes are dropped so the result is a clean two-token person name (what
    _is_plausible_name accepts, and what reads correctly in a call script).
    """
    raw = (raw or "").strip()
    if not raw:
        return ""
    surname, _, remainder = raw.partition(",")
    if not remainder.strip():          # no comma — already "FIRST LAST"
        parts = raw.split()
        if len(parts) < 2:
            return ""
        first, surname = parts[0], parts[-1]
    else:
        drop = {"JR", "SR", "II", "III", "IV", "V", "MD", "DDS"}
        given = [t for t in remainder.split() if t.strip(".").upper() not in drop]
        if not given:
            return ""
        first = given[0]
    first, surname = first.strip(), surname.strip()
    if not first or not surname:
        return ""
    return f"{first.capitalize()} {surname.capitalize()}"


async def _wa_registry_lookup(business: str) -> dict:
    """Resolve a WA contractor's licence principal — the legally named person.

    Matching is deliberately STRICT: only a licence whose normalized business
    name equals the query's exactly is accepted, and if several matching
    licences name different principals the lookup returns empty rather than
    picking one. Returning a real person attached to the wrong company would be
    fabricated lead data, which is the one unforgivable failure here — a miss
    is always cheaper than a confident wrong name.

    Kill switch: WA_LNI_ENABLED=0. Defaults ON because the source needs no key
    and costs nothing (unlike the dead SoS endpoint this replaces, which had to
    default OFF).
    """
    if not business or os.getenv("WA_LNI_ENABLED", "1") != "1":
        return dict(_EMPTY)
    target = _normalize_business(business)
    # A single-token name is too collision-prone to match on. Live 2026-07-25:
    # the bare query "Acme" exact-matched a real WA licence literally named
    # "ACME" and returned its principal — a correct match to the wrong company,
    # since our scraped business names are frequently truncated or generic.
    # Two tokens is the cheapest guard against that, and every real remodeler
    # name in the verification sample cleared it.
    if not target or len(target.split()) < 2:
        return dict(_EMPTY)
    try:
        # Prefix on the first TWO normalized tokens, then exact-match on the
        # normalized form client-side. The client-side equality check is what
        # actually decides acceptance, so a longer name like "ACME ROOFING AND
        # SIDING" is still rejected — a looser search window does not loosen
        # what is accepted.
        #
        # NOT the full normalized name. Normalization strips punctuation and
        # legal-form tokens, but the prefix is matched against the RAW
        # `businessname`, so any stripped character in the MIDDLE of the name
        # made it unmatchable. Measured live 2026-08-06 against real ACTIVE WA
        # licences whose own names contain '&', '.' or ',': the lookup resolved
        # only 2 of 14 — it could not find owners for names in its own
        # registry. "168 KITCHEN & BATH CORP" normalizes to "168 KITCHEN BATH",
        # which is not a prefix of the stored name.
        #
        # NOT one token either: live 2026-07-25 'TOP' matched 398 licences and
        # 'BLACK' 368, so with a per-request window the true match fell outside
        # it. Two tokens is selective enough.
        prefix = " ".join(target.split()[:2]).replace("'", "''")
        select = "businessname,primaryprincipalname,contractorlicensestatus"

        async def _fetch(where: str, limit: str) -> list:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resp = await client.get(
                    _WA_LNI_DATASET,
                    params={"$where": where, "$select": select, "$limit": limit},
                    headers={"Accept": "application/json"})
            if resp.status_code != 200:
                logger.debug(f"[OWNER_FINDER] WA L&I status {resp.status_code} "
                             f"for {business}")
                return []
            return resp.json() or []

        rows = await _fetch(f"upper(businessname) like '{prefix}%'", "50")
        exact = [r for r in rows
                 if _normalize_business(r.get("businessname", "")) == target]

        # Fallback for punctuation INSIDE the first two tokens, where even a
        # two-token prefix cannot match: "E&K SOLUTIONS LLC" normalizes to
        # "E K SOLUTIONS", and "E K" is not a prefix of "E&K SOLUTIONS LLC".
        # Retry as a CONTAINS on the longest token — the most selective single
        # word available, and immune to punctuation anywhere. Costs a second
        # request only when the first found nothing.
        if not exact:
            tokens = sorted((t for t in target.split() if len(t) >= 5),
                            key=len, reverse=True)
            if tokens:
                needle = tokens[0].replace("'", "''")
                rows = await _fetch(
                    f"upper(businessname) like '%{needle}%'", "400")
                exact = [r for r in rows
                         if _normalize_business(r.get("businessname", "")) == target]
        if not exact:
            return dict(_EMPTY)
        # An active licence is the better record when duplicates exist.
        active = [r for r in exact
                  if (r.get("contractorlicensestatus") or "").upper() == "ACTIVE"]
        candidates = active or exact
        names = {_person_from_principal(r.get("primaryprincipalname", ""))
                 for r in candidates}
        names.discard("")
        if len(names) != 1:
            # Zero names, or an ambiguous multi-principal match — do not guess.
            logger.debug(f"[OWNER_FINDER] WA L&I ambiguous/empty principal for "
                         f"{business} ({len(names)} distinct names)")
            return dict(_EMPTY)
        name = names.pop()
        if _is_plausible_name(name):
            return {"owner": name, "title": "Licence Principal",
                    "source": "wa_lni", "confidence": 0.9}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] WA L&I lookup failed for {business}: {e}")
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1b — California Statement of Information (gated, free-tier UNCONFIRMED)
# ═══════════════════════════════════════════════════════════════════════════

async def _ca_registry_lookup(business: str) -> dict:
    """CA Statement of Information via the CALICO developer portal.

    Per the research doc, CALICO's free-tier cost for the Business Entity
    Search product was NOT confirmed from public docs (pricing page requires
    sign-in). To keep CA uncertainty from ever blocking the pipeline, this
    source is entirely gated behind CA_SOS_API_KEY and defaults to a clean
    skip when unset or on any error — never raises, never blocks.
    """
    api_key = os.getenv("CA_SOS_API_KEY")
    if not api_key or not business:
        return dict(_EMPTY)
    try:
        url = "https://calicodev.sos.ca.gov/api/BusinessEntitySearch"
        headers = {"Ocp-Apim-Subscription-Key": api_key, "Accept": "application/json"}
        params = {"entityName": business}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json()
        entities = data.get("entities") or data.get("Entities") or []
        if not entities:
            return dict(_EMPTY)
        entity = entities[0]
        officers = entity.get("officers") or entity.get("Officers") or []
        for officer in officers:
            name = (officer.get("name") or officer.get("Name") or "").strip()
            title = (officer.get("title") or officer.get("Title") or "Officer").strip()
            if name and _is_plausible_name(name):
                return {"owner": name, "title": title, "source": "ca_sos", "confidence": 0.9}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] CA registry lookup failed for {business}: {e}")
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1c — Oregon registry (best-effort HTML parse, no documented API)
# ═══════════════════════════════════════════════════════════════════════════

async def _or_registry_lookup(business: str) -> dict:
    """OR Business Registry search — no JSON API, so this is a best-effort
    HTML parse of the public search results page. Skips cleanly on any
    layout/parse failure since there's no documented, stable structure."""
    if not business:
        return dict(_EMPTY)
    try:
        url = "https://secure.sos.state.or.us/cbrmanager/search.action"
        params = {"businessName": business}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return dict(_EMPTY)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # No re.IGNORECASE: the capture group's own [A-Z][a-z]+ shape is what
        # bounds a real title-case name — case-insensitive would let the match
        # run on into surrounding lowercase prose (matches lead_gen_v3's
        # existing _state_registry_lookup pattern for the same reason).
        match = re.search(
            r'(?:Registered\s+Agent|Agent\s+Name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            text,
        )
        if match:
            name = match.group(1).strip()
            if _is_plausible_name(name):
                return {"owner": name, "title": "Registered Agent", "source": "or_sos", "confidence": 0.7}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] OR registry lookup failed for {business}: {e}")
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1d — OpenCorporates (cross-state catch-all, rationed 50/day)
# ═══════════════════════════════════════════════════════════════════════════

async def _opencorporates_lookup(business: str) -> dict:
    api_key = os.getenv("OPENCORPORATES_API_KEY")
    if not api_key or not business:
        return dict(_EMPTY)
    if not await _ration_check_and_increment("owner_finder:oc_daily", OPENCORPORATES_DAILY_CAP, "day"):
        logger.info("[OWNER_FINDER] OpenCorporates daily cap reached, skipping")
        return dict(_EMPTY)
    try:
        url = "https://api.opencorporates.com/v0.4/companies/search"
        params = {"q": business, "api_token": api_key, "per_page": 1}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json()
        companies = data.get("results", {}).get("companies", [])
        if not companies:
            return dict(_EMPTY)
        company = companies[0].get("company", {})
        officers = company.get("officers") or []
        for entry in officers:
            officer = entry.get("officer", entry)
            name = (officer.get("name") or "").strip()
            title = (officer.get("position") or "Officer").strip()
            if name and _is_plausible_name(name):
                return {"owner": name, "title": title, "source": "opencorporates", "confidence": 0.75}
        # No inline officers — a company hit with no officer data is still
        # not useful for owner_name, so fall through empty rather than
        # burning a second call against the daily cap for /officers/search.
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] OpenCorporates lookup failed for {business}: {e}")
    return dict(_EMPTY)


async def _registry_lookup(business: str, state: str) -> dict:
    """Route to the right state registry; unknown/other states go to OpenCorporates."""
    state = (state or "").strip().upper()
    if state == "WA":
        hit = await _wa_registry_lookup(business)
        if hit["owner"]:
            return hit
    elif state == "CA":
        hit = await _ca_registry_lookup(business)
        if hit["owner"]:
            return hit
    elif state == "OR":
        hit = await _or_registry_lookup(business)
        if hit["owner"]:
            return hit
    else:
        hit = await _opencorporates_lookup(business)
        if hit["owner"]:
            return hit
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2 — Website scrape fallback (reuses existing lead_gen_v3 strategy)
# ═══════════════════════════════════════════════════════════════════════════

async def _website_scrape_fallback(domain: str) -> dict:
    """Delegate to lead_gen_v3's existing regex/JSON-LD website scraper —
    intentionally not reimplemented per the task brief."""
    if not domain:
        return dict(_EMPTY)
    try:
        from app.skills.lead_gen_v3 import _scrape_website
        url = domain if domain.startswith("http") else f"https://{domain}"
        result = await _scrape_website(url)
        name = (result or {}).get("owner_name", "")
        if name and _is_plausible_name(name):
            return {"owner": name, "title": "", "source": "website_scrape", "confidence": 0.5}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] website scrape fallback failed for {domain}: {e}")
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 3 — SerpAPI fallback (rationed ~250/month, high-score leads only)
# ═══════════════════════════════════════════════════════════════════════════

SERP_SCORE_THRESHOLD = 70.0


async def _serpapi_fallback(business: str, score: float) -> dict:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key or not business:
        return dict(_EMPTY)
    if score < SERP_SCORE_THRESHOLD:
        return dict(_EMPTY)
    if not await _ration_check_and_increment("owner_finder:serp_monthly", SERPAPI_MONTHLY_CAP, "month"):
        logger.info("[OWNER_FINDER] SerpAPI monthly cap reached, skipping")
        return dict(_EMPTY)
    try:
        url = "https://serpapi.com/search"
        params = {
            "q": f'"{business}" owner OR founder OR CEO OR president',
            "api_key": api_key,
            "engine": "google",
            "num": 5,
        }
        async with httpx.AsyncClient(timeout=_SERP_TIMEOUT) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json()
        results = data.get("organic_results", [])
        # Mirrors lead_gen_v3.OWNER_PATTERNS's multi-shape approach: a snippet
        # like "owner OR founder OR CEO" search results in "Founded by Jane
        # Doe" or "Jane Doe, owner of ..." phrasing more often than the bare
        # "owner: Name" shape, so both directions are covered here.
        # No re.IGNORECASE on any of these: the [A-Z] anchors are what bound
        # a real title-case name inside a full sentence (same reasoning as
        # the OR-registry pattern above) — case-insensitive matching lets
        # the capture run on into surrounding lowercase words like "of"/"by".
        # Role-prefixed patterns (1 & 2) capture exactly first+last (2 words):
        # a live SerpAPI test returned "Kim Malek Built" from "...Founder Kim
        # Malek Built the..." — the {1,3} let a trailing title-case verb ride
        # along. Capping at {1} kills that over-capture (we lose rare 3-word
        # names, but a wrong name in outreach is worse than a shorter one).
        # Pattern 3 keeps {1,2} — the trailing role keyword bounds it safely.
        _serp_owner_patterns = [
            re.compile(r'(?:[Oo]wner|[Ff]ounder|CEO|[Pp]resident|[Pp]rincipal)[:\s,\-–]+([A-Z][a-zA-Z\'\-]+(?:\s+[A-Z][a-zA-Z\'\-]+){1})'),
            re.compile(r'(?:[Ff]ounded|[Oo]wned|[Rr]un|[Oo]perated|[Ss]tarted|[Ll]ed)\s+by\s+([A-Z][a-zA-Z\'\-]+(?:\s+[A-Z][a-zA-Z\'\-]+){1})'),
            re.compile(r'([A-Z][a-zA-Z\'\-]+(?:\s+[A-Z][a-zA-Z\'\-]+){1,2}),?\s+(?:[Oo]wner|[Ff]ounder|CEO|[Pp]resident|[Pp]rincipal)'),
        ]
        for res in results:
            text = f"{res.get('title', '')} {res.get('snippet', '')}"
            for owner_pattern in _serp_owner_patterns:
                match = owner_pattern.search(text)
                if not match:
                    continue
                name = match.group(1).strip()
                if _is_plausible_name(name):
                    return {"owner": name, "title": "", "source": "serpapi", "confidence": 0.4}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] SerpAPI fallback failed for {business}: {e}")
    return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

async def resolve_owner(business: str, state: str = "", domain: str = "", score: float = 0.0) -> dict:
    """Resolve a business's real owner/officer name.

    Fallback order: cache -> state-routed registry (WA/CA/OR/OpenCorporates)
    -> website scrape -> SerpAPI (score-gated). Never raises — any failure
    at any stage falls through to the next, and if every stage misses this
    returns an empty-owner dict (never None, never an exception).

    Returns: {"owner": str, "title": str, "source": str, "confidence": float}
    """
    business = (business or "").strip()
    if not business:
        return dict(_EMPTY)

    cached = await _cache_get(business, state)
    if cached is not None:
        return cached

    result = dict(_EMPTY)
    try:
        result = await _registry_lookup(business, state)
        if not result["owner"]:
            result = await _website_scrape_fallback(domain)
        if not result["owner"]:
            result = await _serpapi_fallback(business, score)
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] resolve_owner unexpected error for {business}: {e}")
        result = dict(_EMPTY)

    # Cache positive hits only. Caching a miss for the full 30-day TTL would
    # suppress retries after a key/registry is later configured — and misses on
    # keyless sources are cheap while rationed sources are already quota-capped.
    if result.get("owner"):
        await _cache_set(business, state, result)
    return result
