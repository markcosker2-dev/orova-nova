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
            # noqa-safe: `where` is built only from literal "col = ?" clauses
            # above; every value is bound in `params`. Nothing here is caller text.
            f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?",  # noqa: S608
            (*params, int(limit)), fetchall=True,
        )
        return [dict(r) for r in (rows or [])]
    except Exception as e:
        logger.warning(f"[EVENTS] fetch failed (non-fatal): {e}")
        return []


# ── Outcome capture (The Desk) ──────────────────────────────────────────────
# Only Mark knows whether a booked meeting was held, no-showed, or closed —
# without capturing that, the learning loop can never connect variants to what
# actually books and closes. One-tap Telegram command, deterministic (never
# routed through the brain).

_OUTCOME_MAP = {
    "booked": ("meeting_booked", "Meeting Booked"),
    "held": ("meeting_held", "Meeting Held"),
    "noshow": ("meeting_noshow", "No-Show"),
    "no-show": ("meeting_noshow", "No-Show"),
    "closed": ("deal_closed", "Closed Won"),
    "lost": ("deal_lost", "Closed Lost"),
}

_OUTCOME_USAGE = ("Usage: /outcome <lead_id> <booked|held|noshow|closed|lost> [notes]\n"
                  "e.g. /outcome 12 held great call, wants P2 pricing")


async def handle_outcome_command(text: str) -> str | None:
    """Parse '/outcome <lead_id> <outcome> [notes]' from Telegram.

    Returns a reply string when `text` is an outcome command (including usage
    errors, so the user always gets feedback), or None when it isn't one —
    the caller then routes the message onward to the brain."""
    t = (text or "").strip()
    if not t.lower().startswith("/outcome"):
        return None
    parts = t.split(maxsplit=3)
    if len(parts) < 3:
        return _OUTCOME_USAGE
    try:
        lead_id = int(parts[1])
    except ValueError:
        return f"Lead id must be a number, got '{parts[1]}'.\n{_OUTCOME_USAGE}"
    key = parts[2].lower()
    if key not in _OUTCOME_MAP:
        return f"Unknown outcome '{parts[2]}'.\n{_OUTCOME_USAGE}"
    notes = parts[3].strip() if len(parts) > 3 else ""
    event_type, status = _OUTCOME_MAP[key]
    await alog_event(lead_id, event_type, "desk", payload={"notes": notes})
    try:
        await DatabaseManager.query("UPDATE leads SET status = ? WHERE id = ?",
                                    (status, lead_id))
    except Exception as e:
        logger.warning(f"[EVENTS] lead status update failed (event still logged): {e}")
    return f"Logged '{event_type}' for lead {lead_id} → status '{status}'."
