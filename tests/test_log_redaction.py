"""Regression tests for log-pipeline secret redaction.

Live-observed 2026-07-10: httpx logged Telegram's full
``POST .../bot<TOKEN>/setWebhook`` URL at INFO, and the root-logger
BufferHandler copied it verbatim into the dashboard-readable /api/logs
buffer + the agent_logs state row. The token guards the HITL approval
channel. These tests pin the scrub at every sink.
"""
import logging

from app.core import json_logger


def _reset_env_cache():
    json_logger._env_secret_values = None


def test_telegram_bot_token_path_is_redacted():
    line = 'HTTP Request: POST https://api.telegram.org/bot8980108861:AAFHE1qbZ5K5CMTszMTyhqbxbkx2RpjSgOs/setWebhook "200 OK"'
    out = json_logger.redact_secrets(line)
    assert "AAFHE1qbZ5K5CMTszMTyhqbxbkx2RpjSgOs" not in out
    assert "bot[REDACTED]/setWebhook" in out


def test_credential_query_params_are_redacted():
    line = "GET https://serpapi.com/search?q=acme&api_key=abc123secretvalue&engine=google"
    out = json_logger.redact_secrets(line)
    assert "abc123secretvalue" not in out
    assert "api_key=[REDACTED]" in out
    assert "q=acme" in out  # non-credential params untouched


def test_env_secret_values_are_redacted(monkeypatch):
    monkeypatch.setenv("SOME_VENDOR_API_KEY", "gsk_IdJExampleValue123")
    _reset_env_cache()
    try:
        out = json_logger.redact_secrets("calling vendor with gsk_IdJExampleValue123 now")
        assert "gsk_IdJExampleValue123" not in out
        assert "[REDACTED]" in out
    finally:
        _reset_env_cache()


def test_short_or_noncredential_env_values_are_not_collected(monkeypatch):
    monkeypatch.setenv("MAX_CALLS_PER_DAY", "5")          # name doesn't match
    monkeypatch.setenv("TINY_TOKEN", "abc")               # value too short
    _reset_env_cache()
    try:
        secrets = json_logger._get_env_secrets()
        assert "5" not in secrets
        assert "abc" not in secrets
    finally:
        _reset_env_cache()


def test_clean_text_passes_through_unchanged():
    line = "[LANE 2] Found 3 leads for exotic car dealer california"
    assert json_logger.redact_secrets(line) == line


def test_json_formatter_redacts_message():
    record = logging.LogRecord(
        name="httpx", level=logging.INFO, pathname="", lineno=0,
        msg="POST https://api.telegram.org/bot123456:AAAAAAAAAABBBBBBBBBBCCCCCCCCC/sendMessage",
        args=(), exc_info=None,
    )
    out = json_logger.JSONFormatter().format(record)
    assert "AAAAAAAAAABBBBBBBBBBCCCCCCCCC" not in out
    assert "bot[REDACTED]" in out


def test_append_log_buffer_is_scrubbed():
    from app import main as app_main
    app_main._append_log("token leak https://api.telegram.org/bot99:AAAAAAAAAABBBBBBBBBBCCCCCCCCC/x")
    entry = app_main.LOG_BUFFER[-1]["msg"]
    assert "AAAAAAAAAABBBBBBBBBBCCCCCCCCC" not in entry
    assert "bot[REDACTED]" in entry


def test_redaction_failure_fails_open(monkeypatch):
    monkeypatch.setattr(json_logger, "_get_env_secrets",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    line = "some log line"
    assert json_logger.redact_secrets(line) == line  # original text survives
