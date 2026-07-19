"""Provider-chain resilience: the failure chain that produced
'All AI providers failed for role default. Last error: Unknown' (2026-07-19).

Live sequence from /api/logs:
1. Groq 400 'tool_use_failed' — model emitted morning_brief(client_id="OROVA")
   against an integer schema (server-side generation validation).
2. Gemini fallback died on "'ChatCompletionMessageToolCall' object has no
   attribute 'get'" — planner had appended raw SDK objects into history.
3. OpenRouter not configured -> last_error None -> "Unknown".

Fixes under test:
- planner._normalise_tool_calls: history holds only plain JSON-able dicts.
- ai_client._convert_messages_to_gemini / _find_tool_name_from_id tolerate
  dict, SDK-object, and SimpleNamespace tool calls.
- ai_client.chat records a structured failure per tier and the terminal
  message names the failing provider (never "Unknown").
- Groq 'tool_use_failed' gets exactly one retry (bad generation != outage).
- ceo_brain._coerce_client_id survives client_id="OROVA".
"""
import asyncio
import json
from types import SimpleNamespace

from app.core.ai_client import UnifiedAIClient
from app.core.planner import _normalise_tool_calls
from app.core.ceo_brain import _coerce_client_id


class _SdkToolCall:
    """Mimics openai ChatCompletionMessageToolCall: attribute access only."""
    def __init__(self, id, name, arguments):
        self.id = id
        self.type = "function"
        self.function = SimpleNamespace(name=name, arguments=arguments)


def _bare_client(groq=None, google=None, primary=None) -> UnifiedAIClient:
    c = UnifiedAIClient.__new__(UnifiedAIClient)  # no __init__ / no network
    c.groq_client, c.google_client, c.primary_client = groq, google, primary
    return c


# ── planner history normalization ────────────────────────────────────────────

def test_normalise_sdk_objects_to_dicts():
    tc = _SdkToolCall("call_1", "morning_brief", '{"client_id": 0}')
    out = _normalise_tool_calls([tc])
    assert out == [{"id": "call_1", "type": "function",
                    "function": {"name": "morning_brief",
                                 "arguments": '{"client_id": 0}'}}]
    json.dumps(out)  # history must stay JSON-serializable for Groq


def test_normalise_simplenamespace_and_dict_args():
    # Gemini path: SimpleNamespace with dict-typed arguments
    tc = SimpleNamespace(id="g1", type="function",
                         function=SimpleNamespace(name="t", arguments={"a": 1}))
    out = _normalise_tool_calls([tc, {"id": "d1", "function": {"name": "u", "arguments": "{}"}}])
    assert out[0]["function"]["arguments"] == '{"a": 1}'
    assert out[1]["id"] == "d1"
    json.dumps(out)


def test_normalise_drops_nameless_and_survives_junk():
    junk = SimpleNamespace(id="x", function=SimpleNamespace(name=None, arguments=None))
    assert _normalise_tool_calls([junk, None]) == []
    assert _normalise_tool_calls(None) == []


# ── Gemini converter must tolerate SDK objects in history ────────────────────

def test_gemini_conversion_handles_sdk_tool_call_objects():
    client = _bare_client()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hey"},
        {"role": "assistant", "content": "",
         "tool_calls": [_SdkToolCall("call_9", "check_replies", "{}")]},
        {"role": "tool", "tool_call_id": "call_9", "content": "no new replies"},
    ]
    contents = client._convert_messages_to_gemini(messages)  # must not raise
    fc_parts = [p for c in contents for p in c["parts"] if "function_call" in p]
    assert fc_parts and fc_parts[0]["function_call"]["name"] == "check_replies"
    fr_parts = [p for c in contents for p in c["parts"] if "function_response" in p]
    assert fr_parts and fr_parts[0]["function_response"]["name"] == "check_replies"


def test_gemini_conversion_still_handles_dict_tool_calls():
    client = _bare_client()
    messages = [
        {"role": "assistant", "content": "",
         "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": '{"k": "v"}'}}]},
    ]
    contents = client._convert_messages_to_gemini(messages)
    assert contents[0]["parts"][0]["function_call"]["args"] == {"k": "v"}


def test_find_tool_name_tolerates_objects():
    client = _bare_client()
    messages = [{"role": "assistant",
                 "tool_calls": [_SdkToolCall("call_2", "find_leads", "{}")]}]
    assert client._find_tool_name_from_id("call_2", messages) == "find_leads"
    assert client._find_tool_name_from_id("missing", messages) == ""


# ── terminal error must name the failing provider, never 'Unknown' ───────────

def _completions(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_all_fail_message_names_providers():
    async def groq_boom(**kw):
        raise RuntimeError("Error code: 429 - rate limit exceeded")
    client = _bare_client(groq=_completions(groq_boom))
    resp = asyncio.run(client.chat("hi"))
    assert "All AI providers failed" in resp.content
    assert "Unknown" not in resp.content
    assert "groq" in resp.content
    assert "gemini: Skipped" in resp.content or "gemini" in resp.content
    assert "req " in resp.content  # request id for log correlation


def test_no_providers_message_is_actionable():
    client = _bare_client()
    resp = asyncio.run(client.chat("hi"))
    assert "GROQ_API_KEY" in resp.content


def test_groq_tool_use_failed_retries_once_then_succeeds():
    calls = {"n": 0}
    ok_msg = SimpleNamespace(content="ok", tool_calls=None)

    async def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            e = RuntimeError("tool call validation failed")
            e.body = {"error": {"code": "tool_use_failed",
                                "failed_generation": '<function=morning_brief>{"client_id": "OROVA"}</function>'}}
            raise e
        return SimpleNamespace(choices=[SimpleNamespace(message=ok_msg)])

    client = _bare_client(groq=_completions(flaky))
    resp = asyncio.run(client.chat("hi"))
    assert calls["n"] == 2
    assert resp.content == "ok"


def test_groq_non_schema_error_does_not_retry():
    calls = {"n": 0}

    async def always_500(**kw):
        calls["n"] += 1
        e = RuntimeError("internal server error")
        e.status_code = 500
        raise e

    client = _bare_client(groq=_completions(always_500))
    resp = asyncio.run(client.chat("hi"))
    assert calls["n"] == 1
    assert "HTTP 500" in resp.content


# ── client_id coercion guard ─────────────────────────────────────────────────

def test_coerce_client_id():
    assert _coerce_client_id("OROVA") == 0
    assert _coerce_client_id(None) == 0
    assert _coerce_client_id("3") == 3
    assert _coerce_client_id(7) == 7
