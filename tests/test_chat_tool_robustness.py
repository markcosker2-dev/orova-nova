"""Chat-path robustness: the two bugs that produced
'All AI providers failed for role default' on a Telegram message (2026-07-15).

1. A no-arg tool call arrives with arguments='null' -> args=None -> the
   semantic firewall crashed on params.items().
2. Groq 400s on a tool call, the Gemini fallback is then killed for the WHOLE
   request by 'Unknown field for Schema: additionalProperties' — because our
   OpenAI strict-mode tool schemas carry fields Gemini's Schema proto rejects.
"""
from app.core.semantic_firewall import validate_against_schema, ParameterSchema
from app.core.ai_client import UnifiedAIClient


# ── Bug 1: None params must not crash validation ─────────────────────────────

def test_validate_against_schema_tolerates_none_params():
    schema = ParameterSchema(properties={}, required=[])
    # Must not raise 'NoneType' object has no attribute 'items'
    assert validate_against_schema(None, schema) == []


def test_validate_against_schema_none_flags_missing_required():
    schema = ParameterSchema(properties={}, required=["client_id"])
    errors = validate_against_schema(None, schema)
    assert any("client_id" in e for e in errors)


# ── Bug 2: Gemini tool schema must be scrubbed of OpenAI-only fields ──────────

def _find_key(node, target):
    """True if `target` appears as a key anywhere in the nested structure."""
    if isinstance(node, dict):
        if target in node:
            return True
        return any(_find_key(v, target) for v in node.values())
    if isinstance(node, list):
        return any(_find_key(v, target) for v in node)
    return False


def test_gemini_tool_conversion_strips_banned_fields():
    client = UnifiedAIClient.__new__(UnifiedAIClient)  # no __init__ / no network
    tools = [{
        "type": "function",
        "function": {
            "name": "browse_agent",
            "description": "d",
            "parameters": {
                "type": "object",
                "additionalProperties": False,               # the killer field
                "properties": {
                    "url": {"type": "string", "pattern": "^https?://", "minLength": 5},
                    "objective": {"type": "string", "default": "Extract main text"},
                },
                "required": ["url"],
            },
            "strict": True,
        },
    }]
    out = client._convert_tools_to_gemini(tools)
    decls = out[0]["function_declarations"]
    assert decls[0]["name"] == "browse_agent"
    for banned in ("additionalProperties", "strict", "pattern", "minLength", "default"):
        assert not _find_key(out, banned), f"{banned} leaked into Gemini schema"
    # real structure survives
    assert decls[0]["parameters"]["properties"]["url"]["type"] == "string"
    assert decls[0]["parameters"]["required"] == ["url"]


def test_gemini_conversion_does_not_mutate_source():
    client = UnifiedAIClient.__new__(UnifiedAIClient)
    params = {"type": "object", "additionalProperties": False, "properties": {}}
    tools = [{"type": "function", "function": {"name": "t", "parameters": params}}]
    client._convert_tools_to_gemini(tools)
    assert "additionalProperties" in params  # original untouched
