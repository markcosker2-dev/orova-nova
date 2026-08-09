# -*- coding: utf-8 -*-
import os
import logging
import httpx
from typing import Dict, Any

logger = logging.getLogger(__name__)

def _crew_status(principal_count) -> str:
    """'solo' | 'has_crew' | 'unknown' — which pain the script should open on.

    Derived from the named principals on the state licence (free). Never
    guesses: an unknown count returns "unknown" so the prompt asks rather than
    assumes. Opening on payroll pressure to a one-man operation, or on his
    personal calendar to a firm with eight staff, wastes the only question the
    call gets.
    """
    try:
        n = int(principal_count or 0)
    except (TypeError, ValueError):
        return "unknown"
    if n <= 0:
        return "unknown"
    return "solo" if n == 1 else "has_crew"


async def trigger_retell_call(phone: str, context: Dict[str, str]) -> Dict[str, Any]:
    """
    Trigger a Retell AI cold call. Gracefully skips if no API key is configured.
    Returns {"success": True/False, "call_id"/"error", "skipped": bool}
    """
    # ── Graceful degradation: skip if no API key ──
    api_key = os.getenv("RETELL_API_KEY")
    from_number = os.getenv("RETELL_FROM_NUMBER")
    agent_id = os.getenv("RETELL_AGENT_ID")

    if not api_key or not from_number or not agent_id:
        missing = []
        if not api_key: missing.append("RETELL_API_KEY")
        if not from_number: missing.append("RETELL_FROM_NUMBER")
        if not agent_id: missing.append("RETELL_AGENT_ID")
        logger.warning(f"[Retell] Skipping call — missing env vars: {', '.join(missing)}")
        return {"success": False, "skipped": True, "error": f"Missing env vars: {', '.join(missing)}. Cold calling is disabled — set these to enable."}

    # ── DNC/consent gate: never dial a suppressed number (TCPA guardrail) ──
    from app.core.dnc import is_suppressed, is_dnc_registered
    if await is_suppressed(phone):
        logger.warning("[Retell] Blocked call — number is on the DNC/suppression list.")
        return {"success": False, "skipped": True, "error": "Number on DNC/suppression list — call blocked."}
    # National DNC Registry scrub (additive gate; no-ops when unconfigured).
    if await is_dnc_registered(phone):
        logger.warning("[Retell] Blocked call — number is on the National DNC Registry.")
        return {"success": False, "skipped": True, "error": "Number on National DNC Registry — call blocked."}

    # ── §227(b) ARTIFICIAL-VOICE CONSENT GATE — the chokepoint, not the lane ──
    # The DNC checks above are §227(c) (opt-out). They say NOTHING about whether
    # an ARTIFICIAL VOICE may lawfully call this number, which is a separate
    # statute with separate damages ($500/call, trebled to $1,500 if wilful).
    #
    # This gate lived only in `run_phone_first_lane` (worker.py). Four other
    # paths reach this function without it — `_execute_approved_call` (the Fast
    # Lane that fires on Mark's own "Approved" click), `run_cold_lead_escalation`
    # (Lane 4), `outreach_orchestrator.execute_call`, and `planner`, which
    # exposes `trigger_retell_call` to the LLM as a callable TOOL. Gating at
    # each call site is how that hole opened, and an LLM-invokable path cannot
    # be gated by convention at all.
    #
    # So the gate goes HERE, where every path converges — the same pattern
    # CLAUDE.md's single-source-of-truth rule applies to lead storage. Callers
    # may still check first for a better log line; `ai_call_allowed` is a
    # read-only cache/prefix check (no paid lookup, no spend), so calling it
    # twice on the phone-first path is free and harmless.
    try:
        from app.core.call_consent import ai_call_allowed
        allowed, why = await ai_call_allowed(phone)
    except Exception as e:
        # Fail CLOSED. A gate that opens when it errors is not a gate, and the
        # downside here is a four-figure statutory penalty per call.
        logger.error(f"[Retell] Consent gate errored for {phone} ({e}) — blocking call (fail-closed).")
        return {"success": False, "skipped": True, "error": f"TCPA consent gate error — call blocked (fail-closed): {e}"}
    if not allowed:
        logger.warning(f"[Retell] Blocked call — §227(b) consent gate: {why}")
        return {"success": False, "skipped": True, "error": f"AI-voice consent gate: {why}"}

    url = "https://api.retellai.com/v2/create-phone-call"
    owner_name = context.get("owner_name") or ""
    payload = {
        "from_number": from_number,
        "to_number": phone,
        "agent_id": agent_id,
        # Every variable the Nova voice prompt references — an unset variable
        # renders as a literal "{{name}}" on the call, which kills credibility.
        "retell_llm_dynamic_variables": {
            "business_name": context.get("business_name") or "your business",
            "icebreaker": context.get("icebreaker") or "",
            "name": owner_name.split()[0] if owner_name else "there",
            "full_name": owner_name,
            "owner_title": context.get("owner_title") or "owner",
            "niche": context.get("niche") or "your industry",
            # Sole operator or has a crew (2026-08-09). The pain hook differs
            # completely: a contractor with staff feels payroll every Friday,
            # a one-man operation feels his OWN calendar. Asking "do you have
            # guys working with you" burns the one question the script gets,
            # and we already know the answer for free from the licence
            # registry's named principals.
            #
            # "unknown" is a first-class value, not a fallback to either side:
            # 58.9% of WA contractors are single-principal, so guessing wrong
            # is a coin flip that opens the call on the wrong pain.
            "crew_status": _crew_status(context.get("principal_count")),
        },
        # lead_id round-trips through Retell's post-call webhook so outcomes
        # land on the right lead in the DB.
        "metadata": {"lead_id": context.get("lead_id"), "client_id": context.get("client_id", 0)},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
        resp_json = resp.json() if resp.content else {}
        if resp.status_code == 201:
            return {"success": True, "call_id": resp_json.get("call_id"), "data": resp_json, "skipped": False}
        return {"success": False, "error": resp.text, "status_code": resp.status_code, "skipped": False}
    except Exception as e:
        return {"success": False, "error": str(e), "skipped": False}
