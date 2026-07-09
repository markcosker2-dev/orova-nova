"""Structured JSON log formatter (O-05) + log-pipeline secret redaction.

Produces one JSON object per log line so logs are machine-parseable
by Render, Datadog, CloudWatch, or any JSON-aware log aggregator.

Redaction exists because third-party libraries log full request URLs at
INFO — live-observed 2026-07-10: httpx logged Telegram's
``POST .../bot<TOKEN>/setWebhook`` verbatim, putting the bot token (the
credential guarding the HITL approval channel) into Render's log store AND
the dashboard-readable ``/api/logs`` buffer. Every sink must scrub:
``JSONFormatter`` covers stdout; ``main._append_log`` calls
``redact_secrets`` for the buffer path.
"""

import json
import logging
import os
import re
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple

# Any env var whose NAME looks credential-ish contributes its VALUE to the
# redaction set — precise (matches the actual secret, any context) and cheap
# (env is static for the life of a Render process; cached on first use).
_SECRET_ENV_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS", re.IGNORECASE)
# Telegram bot tokens ride in the URL PATH (api.telegram.org/bot<id>:<hash>/…).
_TG_BOT_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}")
# Credential-bearing query params (api_key=…, token=…) for values that are
# not in this process's env (e.g. echoed from a webhook or DB row).
_URL_CRED_RE = re.compile(r"(?i)([?&](?:api_?key|token|secret|password|access_token)=)[^&\s\"']+")

_env_secret_values: Optional[Tuple[str, ...]] = None


def _get_env_secrets() -> Tuple[str, ...]:
    global _env_secret_values
    if _env_secret_values is None:
        values = {
            v for k, v in os.environ.items()
            if v and len(v) >= 8 and _SECRET_ENV_NAME_RE.search(k)
        }
        # Longest first so an overlapping shorter value can't leave residue.
        _env_secret_values = tuple(sorted(values, key=len, reverse=True))
    return _env_secret_values


def redact_secrets(text: str) -> str:
    """Scrub known secrets from a log line. Never raises — a redaction
    failure must not take down logging (returns the original text)."""
    if not text:
        return text
    try:
        for value in _get_env_secrets():
            if value in text:
                text = text.replace(value, "[REDACTED]")
        text = _TG_BOT_TOKEN_RE.sub("bot[REDACTED]", text)
        text = _URL_CRED_RE.sub(r"\1[REDACTED]", text)
    except Exception:
        pass
    return text


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def __init__(self, *, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_secrets(record.getMessage()),
        }

        if record.exc_info and record.exc_info[1]:
            payload["exc"] = redact_secrets(traceback.format_exception_only(
                record.exc_info[0], record.exc_info[1]
            )[0].strip())

        if self.include_extra:
            # Include any extra fields passed via `extra={...}` on the log call
            for key in ("request_id", "chat_id", "agent_id", "tool", "duration_ms", "status"):
                val = getattr(record, key, None)
                if val is not None:
                    payload[key] = val

        return json.dumps(payload, default=str)


def configure_structured_logging(*, level: int = logging.INFO) -> None:
    """Replace the root logger's handlers with JSON-formatted stdout output."""
    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)