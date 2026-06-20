"""Structured JSON log formatter (O-05).

Produces one JSON object per log line so logs are machine-parseable
by Render, Datadog, CloudWatch, or any JSON-aware log aggregator.
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone


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
            "msg": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1]:
            payload["exc"] = traceback.format_exception_only(
                record.exc_info[0], record.exc_info[1]
            )[0].strip()

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