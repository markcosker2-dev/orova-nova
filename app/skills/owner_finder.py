"""Owner-name-FIRST resolver — public registries before free-text scraping.

Design (see vault/20-ops/sessions/2026-07-04-lead-engine-research.md, Job 3):
today's pipeline finds an owner name by regex-mining website text or DDG
snippets, which only works if the business happens to publish a name in a
matchable sentence. This module flips the order: look the business up in a
public registry that is legally required to name a real person FIRST, and
only fall back to text-mining when the registry has no hit.

Fallback chain (first hit wins, each step wrapped so a failure never raises):
    1. State-routed registry
         WA  -> WA SoS JSON API (no key, most robust — built first/most)
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


async def _ration_check_and_increment(counter_key: str, cap: int, period: str) -> bool:
    """Return True if under cap (and increments usage). period: 'day' or 'month'.

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
        if state["count"] >= cap:
            return False
        state["count"] += 1
        await db.set_state(counter_key, state)
        return True
    except Exception as e:
        # Fail OPEN on ration bookkeeping errors would risk quota overrun;
        # fail CLOSED (skip the source) is the safer default here.
        logger.debug(f"[OWNER_FINDER] ration check failed for {counter_key}: {e}")
        return False


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
# STAGE 1a — Washington Secretary of State (no key, documented API)
# ═══════════════════════════════════════════════════════════════════════════

async def _wa_registry_lookup(business: str) -> dict:
    """WA SoS corporations search — DORMANT by default (anti-bot gated).

    Verified live 2026-07-04: WA's real API host (ccfs-api.prod.sos.wa.gov)
    returns "System verification in progress, please wait." to any non-browser
    client — it is anti-bot gated and cannot be used server-side (Render has no
    browser). So this source only runs when WA_SOS_ENABLED=1; otherwise it
    returns empty immediately and the chain falls through (no wasted call).
    Re-enabling for real needs a browser-obtained verification token + a POST to
    the ccfs-api host — the GET stub here just keeps the flag path exercisable.
    """
    if not business or os.getenv("WA_SOS_ENABLED", "0") != "1":
        return dict(_EMPTY)
    try:
        url = "https://ccfs-api.prod.sos.wa.gov/api/BusinessSearch/GetBusinessSearchList"
        params = {
            "SearchEntityName": business,
            "SearchType": "BusinessName",
            "SearchCriteria": "Contains",
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json()
        rows = data if isinstance(data, list) else data.get("Rows") or data.get("rows") or []
        if not rows:
            return dict(_EMPTY)
        row = rows[0]
        name = (
            row.get("GovernorName") or row.get("AgentName")
            or row.get("RegisteredAgentName") or ""
        ).strip()
        title = "Governor/Officer" if row.get("GovernorName") else "Registered Agent"
        if name and _is_plausible_name(name):
            return {"owner": name, "title": title, "source": "wa_sos", "confidence": 0.85}
    except Exception as e:
        logger.debug(f"[OWNER_FINDER] WA registry lookup failed for {business}: {e}")
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
