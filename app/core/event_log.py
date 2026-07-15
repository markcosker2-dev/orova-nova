"""Unified SDR event log (ADR-0007) — the pipeline's ground truth.

Append-only record of everything that happens to a prospect: discovered,
scored, outreach sent, reply received, meeting booked/held. The Coach
(learning loop) reads THIS, not scattered per-feature tables; stage-conversion
metrics (sent→reply→booked) are queries over it.

M1 scope (additive only — deliberately breaks nothing):
  - the `events` table + fail-open loggers
  - wired at: lead creation (hunt + CSV), every send_outreach success
  - existing tables (outreach_outcomes etc.) keep working unchanged; they
    migrate onto this spine in a later, separate change.

Logging must NEVER break the pipeline: every public function here swallows
its own errors after logging a warning (fail-open, same posture as the rest
of app/).
"""
import json
import logging

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prospect_id INTEGER,
    campaign_id INTEGER DEFAULT 0,
    agent TEXT,
    event_type TEXT,
    variant_id TEXT DEFAULT '',
    payload TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_prospect ON events(prospect_id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts);
"""


async def ensure_events_table() -> bool:
    """Create the events table + indexes (idempotent). Returns True on success."""
    try:
        for stmt in _TABLE_SQL.strip().split(";"):
            if stmt.strip():
                await DatabaseManager.query(stmt, ())
        return True
    except Exception as e:
        logger.warning(f"[EVENTS] table init failed (non-fatal): {e}")
        return False


async def alog_event(prospect_id: int, event_type: str, agent: str,
                     payload: dict | None = None, campaign_id: int = 0,
                     variant_id: str = "") -> None:
    """Append one event. Fail-open: never raises into the caller."""
    try:
        await DatabaseManager.query(
            "INSERT INTO events (prospect_id, campaign_id, agent, event_type, variant_id, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (int(prospect_id or 0), int(campaign_id), agent, event_type,
             variant_id, json.dumps(payload or {}, ensure_ascii=False)[:2000]),
        )
    except Exception as e:
        logger.warning(f"[EVENTS] log '{event_type}' failed (non-fatal): {e}")


async def aget_events(prospect_id: int | None = None, event_type: str | None = None,
                      limit: int = 200) -> list:
    """Fetch events, newest first. For the Coach / reporting / debugging."""
    try:
        clauses, params = [], []
        if prospect_id is not None:
            clauses.append("prospect_id = ?"); params.append(int(prospect_id))
        if event_type:
            clauses.append("event_type = ?"); params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await DatabaseManager.query(
            f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?",
            (*params, int(limit)), fetchall=True,
        )
        return [dict(r) for r in (rows or [])]
    except Exception as e:
        logger.warning(f"[EVENTS] fetch failed (non-fatal): {e}")
        return []
