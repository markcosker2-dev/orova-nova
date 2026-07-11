"""Owner-direct EMAIL finder + HTTP verification layer (free tiers only).

Design (see vault/20-ops/sessions/2026-07-05-owner-contact-research.md,
ranked recommendation): once owner_finder.py has resolved an owner NAME,
this module resolves the owner's direct EMAIL:

    1. Tomba.io finder   (25 searches/mo free, name+domain -> email) —
       only for leads where the website scrape found no email at all.
    2. Prospeo finder    (100 credits/mo free, /enrich-person) — a same-tier
       ALTERNATE, tried only when Tomba is unset or its quota is spent;
       never both on one lead.
    3. Verifalia verify  (25 credits/day free ≈ 750/mo) — HTTP-only
       deliverability check for PATTERN-GUESSED emails. Render blocks SMTP,
       so light_enrich's MX check can't detect catch-all domains or dead
       mailboxes; Verifalia's server-side handshake can.

Every key is optional and missing keys skip that provider cleanly (same
pattern as every other optional key in this codebase). Quotas are rationed
via owner_finder's SQLite-backed counter helper so they survive Render
restarts. Nothing here ever raises — all failures degrade to "no result"
(finders) or "no verdict" (verifier, which fails OPEN so a Verifalia outage
never blocks the existing MX-gated guess path).
"""
import os
import logging
from typing import Optional, Tuple

import httpx

from app.skills.owner_finder import _ration_check_and_increment

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10.0
# Verifalia's POST blocks server-side up to waitTime ms before returning 202;
# both bounds must stay small — this runs inside light_enrich's 25s ceiling.
_VERIFALIA_SUBMIT_WAIT_MS = 5000
_VERIFALIA_POLL_WAIT_MS = 4000

TOMBA_MONTHLY_CAP = 25
PROSPEO_MONTHLY_CAP = 100         # free tier grants 100 credits/mo (confirmed live 2026-07-10)
VERIFALIA_DAILY_CAP = 25          # free tier grants 25/day (≈750/mo)
MAX_GUESSES_TO_VERIFY = 3         # 3 credits/lead keeps ~8 leads/day verifiable

_EMPTY = {"email": "", "source": "", "status": ""}


# ═══════════════════════════════════════════════════════════════════════════
# FINDERS — name+domain -> already-verified email from the provider's index
# ═══════════════════════════════════════════════════════════════════════════

async def _tomba_finder(owner: str, domain: str) -> dict:
    """Tomba.io email finder — needs TOMBA_API_KEY + TOMBA_SECRET.

    Failed/no-result searches aren't charged by Tomba, but the ration counts
    attempts anyway: conservative bookkeeping beats discovering mid-month
    that the vendor changed their metering.
    """
    api_key, secret = os.getenv("TOMBA_API_KEY"), os.getenv("TOMBA_SECRET")
    if not api_key or not secret or not owner or not domain:
        return dict(_EMPTY)
    if not await _ration_check_and_increment("email_finder:tomba_monthly", TOMBA_MONTHLY_CAP, "month"):
        logger.info("[EMAIL_FINDER] Tomba monthly cap reached, skipping")
        return dict(_EMPTY)
    try:
        url = "https://api.tomba.io/v1/email-finder"
        params = {"domain": domain, "full_name": owner}
        headers = {"X-Tomba-Key": api_key, "X-Tomba-Secret": secret, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return dict(_EMPTY)
        data = resp.json().get("data") or {}
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return dict(_EMPTY)
        verification = (data.get("verification") or {}).get("status") or ""
        score = data.get("score") or 0
        status = "verified" if (verification == "valid" or score >= 80) else "found"
        return {"email": email, "source": "tomba", "status": status}
    except Exception as e:
        logger.debug(f"[EMAIL_FINDER] Tomba lookup failed for {domain}: {e}")
    return dict(_EMPTY)


async def _prospeo_finder(owner: str, domain: str) -> dict:
    """Prospeo email finder via the /enrich-person API — needs PROSPEO_API_KEY.

    Endpoint + shapes verified live 2026-07-10 (iLusso -> todd@ilusso.com):
    the older /email-finder path Prospeo shipped in early 2026 now 400s with
    error_code DEPRECATED, so this targets the current /enrich-person route.
    A credit is charged only when an email is actually revealed, so a miss
    (person found, email masked, or no person) costs nothing on Prospeo's
    side — but the ration still counts the attempt (conservative bookkeeping).
    """
    api_key = os.getenv("PROSPEO_API_KEY")
    if not api_key or not owner or not domain:
        return dict(_EMPTY)
    if not await _ration_check_and_increment("email_finder:prospeo_monthly", PROSPEO_MONTHLY_CAP, "month"):
        logger.info("[EMAIL_FINDER] Prospeo monthly cap reached, skipping")
        return dict(_EMPTY)
    try:
        url = "https://api.prospeo.io/enrich-person"
        headers = {"Content-Type": "application/json", "X-KEY": api_key}
        payload = {"data": {"full_name": owner, "company_website": domain}}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            return dict(_EMPTY)
        body = resp.json()
        if body.get("error"):
            return dict(_EMPTY)
        email_obj = ((body.get("person") or {}).get("email")) or {}
        # revealed=false means the address is masked (e.g. "t***@x.com") — not
        # usable for outreach, so require an explicit reveal + a real address.
        if not email_obj.get("revealed"):
            return dict(_EMPTY)
        email = (email_obj.get("email") or "").strip().lower()
        if not email or "@" not in email or "*" in email:
            return dict(_EMPTY)
        status = "verified" if (email_obj.get("status") or "").upper() == "VERIFIED" else "found"
        return {"email": email, "source": "prospeo", "status": status}
    except Exception as e:
        logger.debug(f"[EMAIL_FINDER] Prospeo lookup failed for {domain}: {e}")
    return dict(_EMPTY)


async def find_owner_email(owner: str, domain: str) -> dict:
    """Resolve an owner's direct email via free-tier finder APIs.

    Tomba first; Prospeo only when Tomba is unset/spent/missed — the two
    quotas are never spent on the same lead unless Tomba came up empty.
    Never raises. Returns {"email": str, "source": str, "status": str}
    (all empty strings when nothing was found).
    """
    owner = (owner or "").strip()
    domain = (domain or "").strip().lower()
    if not owner or not domain:
        return dict(_EMPTY)
    try:
        hit = await _tomba_finder(owner, domain)
        if hit["email"]:
            return hit
        return await _prospeo_finder(owner, domain)
    except Exception as e:
        logger.debug(f"[EMAIL_FINDER] find_owner_email unexpected error for {domain}: {e}")
        return dict(_EMPTY)


# ═══════════════════════════════════════════════════════════════════════════
# VERIFIER — HTTP-only deliverability check for pattern-guessed emails
# ═══════════════════════════════════════════════════════════════════════════

async def _verifalia_classify(candidates: list) -> Optional[dict]:
    """Verify candidate emails via Verifalia's REST API (HTTP Basic auth,
    VERIFALIA_USERNAME/VERIFALIA_PASSWORD). One job checks all candidates
    (one credit each — the ration counts len(candidates), not calls).

    Returns {email: classification} where classification is one of
    Verifalia's "Deliverable" / "Undeliverable" / "Risky" / "Unknown",
    or None when the check itself couldn't run (creds unset, quota spent,
    network/API failure) — callers must treat None as "no verdict", never
    as "bad email".
    """
    username, password = os.getenv("VERIFALIA_USERNAME"), os.getenv("VERIFALIA_PASSWORD")
    if not username or not password or not candidates:
        return None
    if not await _ration_check_and_increment(
        "email_finder:verifalia_daily", VERIFALIA_DAILY_CAP, "day", amount=len(candidates)
    ):
        logger.info("[EMAIL_FINDER] Verifalia daily cap reached, skipping verification")
        return None
    try:
        base = "https://api.verifalia.com/v2.4/email-validations"
        payload = {"entries": [{"inputData": e} for e in candidates]}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, auth=(username, password)) as client:
            resp = await client.post(base, params={"waitTime": _VERIFALIA_SUBMIT_WAIT_MS}, json=payload)
            if resp.status_code == 202:
                # Job accepted but not finished inside waitTime — poll once,
                # then give up (fail open) to respect the enrichment ceiling.
                job_id = (resp.json().get("overview") or {}).get("id")
                if not job_id:
                    return None
                resp = await client.get(f"{base}/{job_id}", params={"waitTime": _VERIFALIA_POLL_WAIT_MS})
            if resp.status_code != 200:
                return None
            data = resp.json()
        entries = (data.get("entries") or {}).get("data") or []
        verdicts = {
            (entry.get("inputData") or "").lower(): entry.get("classification") or ""
            for entry in entries
            if entry.get("inputData")
        }
        return verdicts or None
    except Exception as e:
        logger.debug(f"[EMAIL_FINDER] Verifalia verification failed: {e}")
        return None


async def select_best_guess(guesses: list) -> Tuple[Optional[str], str]:
    """Pick the best pattern-guessed email, Verifalia-checked when possible.

    Returns (email, status):
      - ("x@y.com", "verified")  first Deliverable candidate
      - ("x@y.com", "guessed")   no verdict available, or no Deliverable but
                                 at least one candidate isn't a hard bounce
      - (None, "")               every checked candidate is Undeliverable —
                                 sending any of them would bounce and damage
                                 sender reputation, so drop the email entirely
    Never raises.
    """
    if not guesses:
        return None, ""
    try:
        checked = guesses[:MAX_GUESSES_TO_VERIFY]
        verdicts = await _verifalia_classify(checked)
        if not verdicts:
            return guesses[0], "guessed"
        for guess in checked:
            if verdicts.get(guess.lower()) == "Deliverable":
                return guess, "verified"
        survivors = [g for g in checked if verdicts.get(g.lower()) != "Undeliverable"]
        if survivors:
            return survivors[0], "guessed"
        # All top candidates hard-bounce; the remaining lower-ranked patterns
        # are worse bets than no email at all (bounces poison the sender).
        return None, ""
    except Exception as e:
        logger.debug(f"[EMAIL_FINDER] select_best_guess unexpected error: {e}")
        return guesses[0], "guessed"
