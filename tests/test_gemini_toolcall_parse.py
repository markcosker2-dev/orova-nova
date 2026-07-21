"""Gemini tool-call response parsing (2026-07-21 Telegram outage).

Symptom: Nova replied to "hi"/"hey" but ANY question returned
"[!!] All AI providers failed … gemini: AttributeError — whichOneof".

Root cause: the Gemini path did `text = response.text` unconditionally.
In google-generativeai 0.8.3, response.text RAISES when a part is a
function_call (no text part). "hi" -> pure-text response (survives); a
question -> tools passed -> Gemini returns a function_call part ->
response.text raises -> the whole Gemini fallback dies. With Groq's
breaker open (quota) and no OpenRouter, every question failed.

Fix: _parse_gemini_response walks parts directly and never touches
response.text. These tests simulate a response whose .text property
RAISES, exactly like the library does.
"""
from types import SimpleNamespace

from app.core.ai_client import UnifiedAIClient


class _RaisingText:
    """Mimics google-generativeai: .text raises on a function_call response."""
    def __init__(self, parts):
        self.candidates = [SimpleNamespace(content=SimpleNamespace(parts=parts))]

    @property
    def text(self):
        raise AttributeError("whichOneof")  # the exact production error


def _fc_part(name, args):
    return SimpleNamespace(function_call=SimpleNamespace(name=name, args=args), text="")


def _text_part(t):
    # a real text part has an empty/falsy function_call
    return SimpleNamespace(function_call=None, text=t)


def test_parses_function_call_without_touching_response_text():
    resp = _RaisingText([_fc_part("morning_brief", {"client_id": 0})])
    text, calls = UnifiedAIClient._parse_gemini_response(resp)
    assert text == ""
    assert calls and calls[0].function.name == "morning_brief"
    assert calls[0].function.arguments == '{"client_id": 0}'


def test_parses_plain_text_response():
    resp = _RaisingText([_text_part("Hello Mark, 5 leads in the pipeline.")])
    text, calls = UnifiedAIClient._parse_gemini_response(resp)
    assert text == "Hello Mark, 5 leads in the pipeline."
    assert calls is None


def test_parses_mixed_text_and_function_call():
    resp = _RaisingText([_text_part("Checking now. "),
                         _fc_part("check_replies", {})])
    text, calls = UnifiedAIClient._parse_gemini_response(resp)
    assert text == "Checking now. "
    assert calls and calls[0].function.name == "check_replies"


def test_empty_or_malformed_response_is_safe():
    assert UnifiedAIClient._parse_gemini_response(SimpleNamespace(candidates=[])) == ("", None)
    assert UnifiedAIClient._parse_gemini_response(SimpleNamespace(candidates=None)) == ("", None)
