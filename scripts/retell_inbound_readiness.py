#!/usr/bin/env python
"""Read-only readiness gate for OROVA's prospect-initiated Retell demo.

This command performs GET requests only. It never prints API responses,
prompts, phone numbers, credentials, tool secrets, or caller data. Its job is
to answer one operational question: is the inbound number still bound to the
reviewed agent, and do that agent's live prompt and Cal tools clear the minimum
truthfulness/consent gates before Mark puts the number in a DM?

    python scripts/retell_inbound_readiness.py

Exit 0 means the machine-verifiable gates pass. Exit 2 means HOLD demo traffic.
The final paid phone-call test remains a human approval step either way.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RETELL_BASE = "https://api.retellai.com"
EXPECTED_AGENT_ID = "agent_850b1ed50ca29bcd7b66ac3a55"
EXPECTED_LLM_ID = "llm_2e8ffc461d20535ee17bcd64bdd5"
EXPECTED_EVENT_TYPE_ID = 2804866
EXPECTED_PHONE_NUMBER = "+17166703920"
EXPECTED_CAL_EVENT_URL = "https://cal.com/mark-b.-cosker-j4zcat/discovery-call"
LEGACY_CAL_TOOL_NAMES = {"check_availability_cal", "book_appointment_cal"}

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _git(*args: str) -> str:
    try:
        return subprocess.run(  # noqa: S603
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            timeout=15, check=False,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _env_path() -> Path | None:
    direct = ROOT / ".env"
    if direct.exists():
        return direct
    common = _git("rev-parse", "--path-format=absolute", "--git-common-dir")
    if common:
        candidate = Path(common).parent / ".env"
        if candidate.exists():
            return candidate
    return None


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = _env_path()
    if path:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in os.environ.items():
        env[key] = value
    return env


def _get_json(url: str, *, bearer: str, headers: dict[str, str] | None = None,
              timeout: int = 30) -> tuple[int, dict[str, Any] | None]:
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {bearer}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", "orova-retell-readiness/1.0")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
            return response.status, payload if isinstance(payload, dict) else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:  # noqa: BLE001 - status only; never print secret-bearing body
        return 0, None


def _canonical_duration() -> int:
    facts = json.loads((ROOT / "knowledge" / "facts" / "company.json").read_text(
        encoding="utf-8"
    ))
    return int(facts["meeting"]["duration_minutes"])


def _all_tools(llm: dict[str, Any]) -> list[dict[str, Any]]:
    tools = [t for t in (llm.get("general_tools") or []) if isinstance(t, dict)]
    for state in llm.get("states") or []:
        if isinstance(state, dict):
            tools.extend(t for t in (state.get("tools") or []) if isinstance(t, dict))
    return tools


def _event_type_id(tool: dict[str, Any]) -> int | None:
    for key in ("event_type_id", "eventTypeId"):
        value = tool.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    # Current integration-app tools store fixed inputs in a JSON-schema-like
    # parameter definition instead of the legacy top-level field.
    for parameter in tool.get("parameters") or []:
        if not isinstance(parameter, dict):
            continue
        properties = parameter.get("properties") or {}
        if not isinstance(properties, dict):
            continue
        event_field = properties.get("event_type_id") or properties.get("eventTypeId")
        if isinstance(event_field, dict):
            value = event_field.get("const")
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None
    return None


def _check(label: str, passed: bool, detail: str, *, severity: str = "BLOCK") -> dict[str, Any]:
    return {"label": label, "passed": bool(passed), "detail": detail,
            "severity": severity}


def _analysis_field(agent: dict[str, Any], name: str) -> dict[str, Any]:
    for field in agent.get("post_call_analysis_data") or []:
        if isinstance(field, dict) and str(field.get("name") or "").lower() == name.lower():
            return field
    return {}


def evaluate_snapshot(phone: dict[str, Any], agent: dict[str, Any],
                      llm: dict[str, Any], cal_duration: int | None) -> dict[str, Any]:
    """Evaluate already-fetched, secret-bearing objects without returning them."""
    checks: list[dict[str, Any]] = []
    inbound = phone.get("inbound_agents") or []
    bindings = [b for b in inbound if isinstance(b, dict)
                and b.get("agent_id") == EXPECTED_AGENT_ID]
    checks.append(_check("number binding", bool(bindings),
                         "expected inbound agent is bound" if bindings
                         else "expected inbound agent is NOT bound"))
    tag_bound = any(str(b.get("agent_version", "")).lower() == "prod" for b in bindings)
    checks.append(_check("version binding", tag_bound,
                         "number follows the prod tag" if tag_bound
                         else "number is not bound through the prod rollback tag",
                         severity="WARN"))

    checks.append(_check("agent identity", agent.get("agent_id") == EXPECTED_AGENT_ID,
                         "prod resolves to reviewed inbound agent"))
    response_engine = agent.get("response_engine") or {}
    checks.append(_check(
        "response engine",
        response_engine.get("type") == "retell-llm"
        and response_engine.get("llm_id") == EXPECTED_LLM_ID,
        "reviewed Retell LLM is attached",
    ))
    tags = {str(tag).lower() for tag in (agent.get("assigned_tags") or [])}
    checks.append(_check("prod tag", "prod" in tags,
                         "resolved version carries prod" if "prod" in tags
                         else "resolved version does not report prod",
                         severity="WARN"))

    storage = str(agent.get("data_storage_setting") or "unknown").lower()
    checks.append(_check(
        "data storage", storage != "everything",
        "sensitive artifacts are limited" if storage != "everything"
        else "Everything stores transcripts, recordings, and logs; review retention/PII",
        severity="WARN",
    ))
    handbook = agent.get("handbook_config") or {}
    checks.append(_check(
        "AI handbook", handbook.get("ai_disclosure") is True,
        "AI disclosure preset enabled" if handbook.get("ai_disclosure") is True
        else "AI disclosure preset is not enabled (prompt wording is checked separately)",
        severity="WARN",
    ))

    appointment_time = _analysis_field(agent, "appointment date and time")
    time_description = str(appointment_time.get("description") or "").lower()
    appointment_time_safe = (
        appointment_time.get("required") is False
        and "15-minute" in time_description
        and "booking tool succeeds" in time_description
    )
    checks.append(_check(
        "appointment time field",
        appointment_time_safe,
        "confirmed 15-minute bookings only; unconfirmed preferences stay separate"
        if appointment_time_safe
        else "appointment date/time extraction field is missing or unsafe",
    ))
    appointment_booked = _analysis_field(agent, "appointment booked")
    booked_description = str(appointment_booked.get("description") or "").lower()
    appointment_booked_safe = (
        appointment_booked.get("required") is False
        and "book_calcom_appointment" in booked_description
        and "preferred times alone are not a booking" in booked_description
    )
    checks.append(_check(
        "appointment booked field",
        appointment_booked_safe,
        "true only after booking success or Mark's confirmation"
        if appointment_booked_safe
        else "appointment-booked extraction field is missing or unsafe",
    ))

    checks.append(_check("LLM identity", llm.get("llm_id") == EXPECTED_LLM_ID,
                         "reviewed response engine retrieved"))
    prompt = " ".join(str(llm.get(key) or "") for key in ("begin_message", "general_prompt"))
    normalized = re.sub(r"[\s‐‑‒–—−]+", " ", prompt.lower())
    prompt_gates = {
        "AI disclosure": "ai assistant" in normalized,
        "recording consent": "record" in normalized and any(
            marker in normalized for marker in ("okay to continue", "permission", "consent")
        ),
        "demo simulation": "simulation" in normalized,
        "post-demo diagnosis": "too few leads" in normalized
        and any(marker in normalized for marker in ("chasing", "screening", "qualif")),
        "15-minute handoff": bool(re.search(r"\b15[ -]?minute\b", normalized)),
        "no-offer boundary": all(marker in normalized for marker in (
            "no price", "no trial", "no pilot"
        )),
    }
    for label, passed in prompt_gates.items():
        checks.append(_check(label, passed,
                             "live prompt contains required boundary" if passed
                             else "live prompt is missing required boundary"))

    tools = _all_tools(llm)
    by_name = {str(tool.get("name") or ""): tool for tool in tools}
    tool_roles = {
        "Cal availability tool": ("check_calcom_availability", "check_availability_cal"),
        "Cal booking tool": ("book_calcom_appointment", "book_appointment_cal"),
    }
    for label, candidates in tool_roles.items():
        tool = next((by_name[name] for name in candidates if name in by_name), None)
        checks.append(_check(
            label, bool(tool) and _event_type_id(tool) == EXPECTED_EVENT_TYPE_ID,
            "tool points to reviewed event type" if tool
            and _event_type_id(tool) == EXPECTED_EVENT_TYPE_ID
            else "tool missing or points to another event type",
        ))

    legacy_present = any(name in by_name for name in LEGACY_CAL_TOOL_NAMES)
    checks.append(_check(
        "Cal migration", not legacy_present,
        "new Retell Cal integration is in use" if not legacy_present
        else "legacy built-in Cal tools: edits end 2026-09-30; runtime migration is due by 2026-10-31",
    ))
    canonical = _canonical_duration()
    checks.append(_check(
        "Cal duration", cal_duration == canonical,
        f"event duration is canonical {canonical} minutes" if cal_duration == canonical
        else ("event duration could not be independently verified"
              if cal_duration is None else
              f"event duration is {cal_duration}, canonical is {canonical}"),
    ))

    blockers = [c for c in checks if c["severity"] == "BLOCK" and not c["passed"]]
    warnings = [c for c in checks if c["severity"] == "WARN" and not c["passed"]]
    return {"ready": not blockers, "checks": checks,
            "blocker_count": len(blockers), "warning_count": len(warnings)}


def _cal_duration(env: dict[str, str]) -> int | None:
    key = env.get("CAL_API_KEY") or env.get("CALCOM_API_KEY")
    if key:
        event_id = EXPECTED_EVENT_TYPE_ID
        # API v2 first. The v1 fallback keeps the read-only check useful for
        # older Cal accounts while the migration is in progress.
        status, payload = _get_json(
            f"https://api.cal.com/v2/event-types/{event_id}", bearer=key,
            headers={"cal-api-version": "2024-08-13"},
        )
        data = (payload or {}).get("data") if status == 200 else None
        if isinstance(data, dict):
            for field in ("lengthInMinutes", "length"):
                try:
                    return int(data[field])
                except (KeyError, TypeError, ValueError):
                    pass
        quoted = urllib.parse.quote(key, safe="")
        status, payload = _get_json(
            f"https://api.cal.com/v1/event-types/{event_id}?apiKey={quoted}",
            bearer=key,
        )
        if status == 200 and isinstance(payload, dict):
            for field in ("length", "lengthInMinutes"):
                try:
                    return int(payload[field])
                except (KeyError, TypeError, ValueError):
                    pass

    # The booking page is public and embeds the event's exact length. This is
    # independent of Retell and avoids turning a missing local Cal API key into
    # a permanent false blocker. Require the reviewed event ID to be present so
    # a redirect or another public event cannot silently clear the gate.
    public_url = env.get("CAL_PUBLIC_EVENT_URL") or EXPECTED_CAL_EVENT_URL
    request = urllib.request.Request(
        public_url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", "replace")
        if str(EXPECTED_EVENT_TYPE_ID) not in page:
            return None
        match = re.search(r'\\"length\\":(\d+)', page)
        return int(match.group(1)) if match else None
    except Exception:  # noqa: BLE001 - status only; never dump the page
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version", default="prod",
        help="Retell agent version or environment tag to inspect (default: prod)",
    )
    args = parser.parse_args()
    version = str(args.version).strip().lower()
    if not re.fullmatch(r"(?:prod|staging|\d+)", version):
        parser.error("--version must be prod, staging, or a non-negative integer")

    env = load_env()
    api_key = env.get("RETELL_API_KEY", "")
    phone_number = env.get("RETELL_INBOUND_NUMBER") or EXPECTED_PHONE_NUMBER
    print(f"\n  OROVA INBOUND DEMO — READ-ONLY READINESS ({version})")
    if not api_key:
        missing = ["RETELL_API_KEY"]
        print(f"  HOLD  missing local configuration: {', '.join(missing)}")
        return 2

    digits = re.sub(r"\D", "", phone_number)
    normalized_phone = f"+{digits}" if digits else phone_number
    # Retell's router expects the literal E.164 '+' in this path; encoding it
    # as %2B returns 404 even though both forms are semantically equivalent.
    encoded_phone = urllib.parse.quote(normalized_phone, safe="+")
    phone_status, phone = _get_json(
        f"{RETELL_BASE}/get-phone-number/{encoded_phone}", bearer=api_key)
    agent_status, agent = _get_json(
        f"{RETELL_BASE}/get-agent/{EXPECTED_AGENT_ID}?version={version}", bearer=api_key)
    if phone_status != 200 or agent_status != 200 or not phone or not agent:
        print(f"  HOLD  Retell reads failed (number={phone_status}, agent={agent_status})")
        return 2
    engine = agent.get("response_engine") or {}
    llm_id = engine.get("llm_id") or EXPECTED_LLM_ID
    llm_version = engine.get("version")
    llm_query = (f"?version={urllib.parse.quote(str(llm_version), safe='')}"
                 if llm_version is not None else "")
    llm_status, llm = _get_json(
        f"{RETELL_BASE}/get-retell-llm/{urllib.parse.quote(str(llm_id), safe='')}{llm_query}",
        bearer=api_key,
    )
    if llm_status != 200 or not llm:
        print(f"  HOLD  Retell response-engine read failed (status={llm_status})")
        return 2

    result = evaluate_snapshot(phone, agent, llm, _cal_duration(env))
    configured_from = re.sub(r"\D", "", env.get("RETELL_FROM_NUMBER", ""))
    expected_from = re.sub(r"\D", "", EXPECTED_PHONE_NUMBER)
    if configured_from and configured_from != expected_from:
        print("  WARN  local outbound config  RETELL_FROM_NUMBER does not match the reviewed number")
    for check in result["checks"]:
        state = "OK" if check["passed"] else check["severity"]
        print(f"  {state:<5} {check['label']:<22} {check['detail']}")
    if result["ready"]:
        print("\n  READY by machine checks. Still run the booking test, simulations, "
              "web call, and owner-approved phone test before DMs.")
        return 0
    print(f"\n  HOLD demo traffic: {result['blocker_count']} blocking check(s), "
          f"{result['warning_count']} warning(s). No live settings were changed.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
