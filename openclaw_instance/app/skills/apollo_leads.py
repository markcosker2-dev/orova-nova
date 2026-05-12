"""
app/skills/apollo_leads.py
Apollo-like B2B leads scraper skill using Apify actor for lead enrichment.
"""

import json
import os
import logging
from typing import Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger("orova.apollo_leads")

DEFAULT_ACTOR_ID = "LurATYM4hkEo78GVj"
DEFAULT_TIMEOUT_SEC = 1800
VALID_SENIORITY = {
    "owner", "cxo", "partner", "vp", "director", "manager", "senior", "entry", "training", "unpaid"
}


class ApolloLeadsError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_token() -> str:
    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        raise ApolloLeadsError("APIFY_TOKEN environment variable not set.")
    return token


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Map Apollo-style aliases to actor fields
    aliases = {
        "personTitleIncludes": "job_titles",
        "seniorityIncludes": "job_title_seniority",
        "personLocationCityIncludes": "person_location_locality",
        "personLocationStateIncludes": "person_location_region",
        "personLocationCountryIncludes": "person_location_country",
        "companyLocationCityIncludes": "company_location_locality",
        "companyLocationStateIncludes": "company_location_region",
        "companyLocationCountryIncludes": "company_location_country",
        "hasEmail": "include_emails",
        "hasPhone": "include_phones",
        "emailStatus": "email_status",
    }
    for src, dst in aliases.items():
        if src in payload and dst not in payload:
            payload[dst] = payload.pop(src)

    # Normalize seniority
    raw_seniority = payload.get("job_title_seniority")
    if isinstance(raw_seniority, list):
        normalized: List[str] = []
        for value in raw_seniority:
            if not isinstance(value, str):
                continue
            v = value.strip().lower()
            if v in {"founder", "co-founder", "cofounder"}:
                v = "owner"
            if v in VALID_SENIORITY:
                normalized.append(v)
        if normalized:
            payload["job_title_seniority"] = sorted(set(normalized))
        else:
            payload.pop("job_title_seniority", None)

    return payload


def run_actor_sync(token: str, actor_id: str, payload: Dict[str, Any], timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> Dict[str, Any]:
    """Run Apify actor synchronously and return results."""
    import urllib.error
    import urllib.parse
    import urllib.request

    base_url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
    params = {
        "token": token,
        "timeout": timeout_sec,
        "clean": "true",
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=min(timeout_sec + 30, 3600)) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise ApolloLeadsError(f"Apify API error {exc.code}: {text[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise ApolloLeadsError(f"Network error calling Apify: {exc}") from exc

    if status_code >= 400:
        raise ApolloLeadsError(f"Apify API error {status_code}: {raw[:1000]}")

    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApolloLeadsError("Apify response is not valid JSON.") from exc

    if not isinstance(rows, list):
        raise ApolloLeadsError("Expected actor output as JSON array.")

    return {
        "ok": True,
        "actorId": actor_id,
        "fetchedAt": utc_now(),
        "leadsCount": len(rows),
        "inputUsed": payload,
        "rows": rows,
    }


def quick_founders_us_50() -> Dict[str, Any]:
    """Run preset for 50 US founders with verified emails."""
    token = resolve_token()
    payload = {
        "max_results": 50,
        "job_titles": ["Founder", "Co-Founder", "CEO"],
        "job_title_seniority": ["owner", "cxo"],
        "person_location_country": ["United States"],
        "employee_size": ["1-10", "11-50", "51-200"],
        "email_status": "verified",
        "include_emails": True,
        "include_phones": False,
    }
    payload = normalize_payload(payload)
    return run_actor_sync(token, DEFAULT_ACTOR_ID, payload)


def run_custom_leads(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run custom lead collection payload."""
    token = resolve_token()
    payload = normalize_payload(payload)
    return run_actor_sync(token, DEFAULT_ACTOR_ID, payload)


def enrich_lead(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich a single lead using Apify actor. Placeholder for future enrichment."""
    # For now, just return the data as is. Could integrate with router for AI enrichment.
    return lead_data


def register_apollo_leads_skills(TOOLS, tool_decorator):
    """Register Apollo Leads skills."""

    @tool_decorator("quick_founders_us_50", "Run preset for 50 US founders with verified emails")
    def _quick_founders():
        try:
            result = quick_founders_us_50()
            return result
        except ApolloLeadsError as e:
            return {"ok": False, "error": str(e)}

    @tool_decorator("run_apollo_leads", "Run custom Apollo-like leads collection with payload")
    def _run_custom(payload: Dict[str, Any]):
        try:
            result = run_custom_leads(payload)
            return result
        except ApolloLeadsError as e:
            return {"ok": False, "error": str(e)}

    @tool_decorator("enrich_lead", "Enrich lead data using Apify (placeholder)")
    def _enrich(lead_data: Dict[str, Any]):
        return enrich_lead(lead_data)

    TOOLS["quick_founders_us_50"] = {"func": _quick_founders, "description": "Preset: 50 US founders"}
    TOOLS["run_apollo_leads"] = {"func": _run_custom, "description": "Custom leads run"}
    TOOLS["enrich_lead"] = {"func": _enrich, "description": "Enrich lead data"}

    return TOOLS</content>
<parameter name="filePath">C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\openclaw_instance\app\skills\apollo_leads.py