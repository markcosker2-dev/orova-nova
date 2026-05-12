#!/usr/bin/env python3
"""
SQLite State Store for OROVA.

Provides persistent session storage with FTS5 full-text search, storing session
metadata, full message history, and model configuration.

Key design decisions:
- WAL mode for concurrent readers + one writer
- FTS5 virtual table for fast text search across all session messages
- Session source tagging ('cli', 'telegram', 'discord', etc.) for filtering
"""

import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_hermes_home() -> Path:
    """Return the OROVA state store directory."""
    return Path.home() / ".hermes"


DEFAULT_DB_PATH = get_hermes_home() / "state.db"

SCHEMA_VERSION = 6

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    user_id TEXT,
    model TEXT,
    model_config TEXT,
    system_prompt TEXT,
    parent_session_id TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    reasoning_tokens INTEGER DEFAULT 0,
    billing_provider TEXT,
    billing_base_url TEXT,
    billing_mode TEXT,
    estimated_cost_usd REAL,
    actual_cost_usd REAL,
    cost_status TEXT,
    cost_source TEXT,
    pricing_version TEXT,
    title TEXT,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT,
    reasoning TEXT,
    reasoning_details TEXT,
    codex_reasoning_items TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content=messages,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


class SessionDB:
    """
    SQLite-backed session storage with FTS5 search.

    Thread-safe for the common gateway pattern (multiple reader threads,
    single writer via WAL mode). Each method opens its own cursor.
    """

    _WRITE_MAX_RETRIES = 15
    _WRITE_RETRY_MIN_S = 0.020
    _WRITE_RETRY_MAX_S = 0.150
    _CHECKPOINT_EVERY_N_WRITES = 50

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._write_count = 0
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=1.0,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self._init_schema()

    def _execute_write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Execute a write transaction with BEGIN IMMEDIATE and jitter retry."""
        last_err: Optional[Exception] = None
        for attempt in range(self._WRITE_MAX_RETRIES):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                    except BaseException:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise
                self._write_count += 1
                if self._write_count % self._CHECKPOINT_EVERY_N_WRITES == 0:
                    self._try_wal_checkpoint()
                return result
            except sqlite3.OperationalError as exc:
                err_msg = str(exc).lower()
                if "locked" in err_msg or "busy" in err_msg:
                    last_err = exc
                    if attempt < self._WRITE_MAX_RETRIES - 1:
                        jitter = random.uniform(
                            self._WRITE_RETRY_MIN_S,
                            self._WRITE_RETRY_MAX_S,
                        )
                        time.sleep(jitter)
                        continue
                raise
        raise last_err or sqlite3.OperationalError(
            "database is locked after max retries"
        )

    def _try_wal_checkpoint(self) -> None:
        """Best-effort PASSIVE WAL checkpoint."""
        try:
            with self._lock:
                result = self._conn.execute(
                    "PRAGMA wal_checkpoint(PASSIVE)"
                ).fetchone()
                if result and result[1] > 0:
                    logger.debug(
                        "WAL checkpoint: %d/%d pages checkpointed",
                        result[2], result[1],
                    )
        except Exception:
            pass

    def close(self):
        """Close the database connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception:
                    pass
                self._conn.close()
                self._conn = None

    def _init_schema(self):
        """Create tables and FTS if they don't exist, run migrations."""
        cursor = self._conn.cursor()

        cursor.executescript(SCHEMA_SQL)

        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            current_version = row["version"] if isinstance(row, sqlite3.Row) else row[0]
            if current_version < 2:
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN finish_reason TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 2")
            if current_version < 3:
                try:
                    cursor.execute("ALTER TABLE sessions ADD COLUMN title TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 3")
            if current_version < 4:
                try:
                    cursor.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_title_unique "
                        "ON sessions(title) WHERE title IS NOT NULL"
                    )
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 4")
            if current_version < 5:
                new_columns = [
                    ("cache_read_tokens", "INTEGER DEFAULT 0"),
                    ("cache_write_tokens", "INTEGER DEFAULT 0"),
                    ("reasoning_tokens", "INTEGER DEFAULT 0"),
                    ("billing_provider", "TEXT"),
                    ("billing_base_url", "TEXT"),
                    ("billing_mode", "TEXT"),
                    ("estimated_cost_usd", "REAL"),
                    ("actual_cost_usd", "REAL"),
                    ("cost_status", "TEXT"),
                    ("cost_source", "TEXT"),
                    ("pricing_version", "TEXT"),
                ]
                for name, column_type in new_columns:
                    try:
                        safe_name = name.replace('"', '""')
                        cursor.execute(f'ALTER TABLE sessions ADD COLUMN "{safe_name}" {column_type}')
                    except sqlite3.OperationalError:
                        pass
                cursor.execute("UPDATE schema_version SET version = 5")
            if current_version < 6:
                for col_name, col_type in [
                    ("reasoning", "TEXT"),
                    ("reasoning_details", "TEXT"),
                    ("codex_reasoning_items", "TEXT"),
                ]:
                    try:
                        safe = col_name.replace('"', '""')
                        cursor.execute(
                            f'ALTER TABLE messages ADD COLUMN "{safe}" {col_type}'
                        )
                    except sqlite3.OperationalError:
                        pass
                cursor.execute("UPDATE schema_version SET version = 6")

        try:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_title_unique "
                "ON sessions(title) WHERE title IS NOT NULL"
            )
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("SELECT * FROM messages_fts LIMIT 0")
        except sqlite3.OperationalError:
            cursor.executescript(FTS_SQL)

        self._conn.commit()

    def create_session(
        self,
        session_id: str,
        source: str,
        model: str = None,
        model_config: Dict[str, Any] = None,
        system_prompt: str = None,
        user_id: str = None,
        parent_session_id: str = None,
    ) -> str:
        """Create a new session record. Returns the session_id."""
        def _do(conn):
            conn.execute(
                """INSERT OR IGNORE INTO sessions (id, source, user_id, model, model_config,
                   system_prompt, parent_session_id, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    source,
                    user_id,
                    model,
                    json.dumps(model_config) if model_config else None,
                    system_prompt,
                    parent_session_id,
                    time.time(),
                ),
            )
        self._execute_write(_do)
        return session_id

    def end_session(self, session_id: str, end_reason: str) -> None:
        """Mark a session as ended."""
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ?",
                (time.time(), end_reason, session_id),
            )
        self._execute_write(_do)

    def reopen_session(self, session_id: str) -> None:
        """Clear ended_at/end_reason so a session can be resumed."""
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET ended_at = NULL, end_reason = NULL WHERE id = ?",
                (session_id,),
            )
        self._execute_write(_do)

    def update_system_prompt(self, session_id: str, system_prompt: str) -> None:
        """Store the full assembled system prompt snapshot."""
        def _do(conn):
            conn.execute(
                "UPDATE sessions SET system_prompt = ? WHERE id = ?",
                (system_prompt, session_id),
            )
        self._execute_write(_do)

    def update_token_counts(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        estimated_cost_usd: Optional[float] = None,
        actual_cost_usd: Optional[float] = None,
        cost_status: Optional[str] = None,
        cost_source: Optional[str] = None,
        pricing_version: Optional[str] = None,
        billing_provider: Optional[str] = None,
        billing_base_url: Optional[str] = None,
        billing_mode: Optional[str] = None,
        absolute: bool = False,
    ) -> None:
        """Update token counters and backfill model if not already set."""
        if absolute:
            sql = """UPDATE sessions SET
                   input_tokens = ?,
                   output_tokens = ?,
                   cache_read_tokens = ?,
                   cache_write_tokens = ?,
                   reasoning_tokens = ?,
                   estimated_cost_usd = COALESCE(?, 0),
                   actual_cost_usd = CASE
                       WHEN ? IS NULL THEN actual_cost_usd
                       ELSE ?
                   END,
                   cost_status = COALESCE(?, cost_status),
                   cost_source = COALESCE(?, cost_source),
                   pricing_version = COALESCE(?, pricing_version),
                   billing_provider = COALESCE(billing_provider, ?),
                   billing_base_url = COALESCE(billing_base_url, ?),
                   billing_mode = COALESCE(billing_mode, ?),
                   model = COALESCE(model, ?)
                   WHERE id = ?"""
        else:
            sql = """UPDATE sessions SET
                   input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?,
                   cache_read_tokens = cache_read_tokens + ?,
                   cache_write_tokens = cache_write_tokens + ?,
                   reasoning_tokens = reasoning_tokens + ?,
                   estimated_cost_usd = COALESCE(estimated_cost_usd, 0) + COALESCE(?, 0),
                   actual_cost_usd = CASE
                       WHEN ? IS NULL THEN actual_cost_usd
                       ELSE COALESCE(actual_cost_usd, 0) + ?
                   END,
                   cost_status = COALESCE(?, cost_status),
                   cost_source = COALESCE(?, cost_source),
                   pricing_version = COALESCE(?, pricing_version),
                   billing_provider = COALESCE(billing_provider, ?),
                   billing_base_url = COALESCE(billing_base_url, ?),
                   billing_mode = COALESCE(billing_mode, ?),
                   model = COALESCE(model, ?)
                   WHERE id = ?"""
        params = (
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
            reasoning_tokens,
            estimated_cost_usd,
            actual_cost_usd,
            actual_cost_usd,
            cost_status,
            cost_source,
            pricing_version,
            billing_provider,
            billing_base_url,
            billing_mode,
            model,
            session_id,
        )
        def _do(conn):
            conn.execute(sql, params)
        self._execute_write(_do)

    def ensure_session(
        self,
        session_id: str,
        source: str = "unknown",
        model: str = None,
    ) -> None:
        """Ensure a session row exists, creating it with minimal metadata if absent."""
        def _do(conn):
            conn.execute(
                """INSERT OR IGNORE INTO sessions
                   (id, source, model, started_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, source, model, time.time()),
            )
        self._execute_write(_do)

    def set_token_counts(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = None,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        reasoning_tokens: int = 0,
        estimated_cost_usd: Optional[float] = None,
        actual_cost_usd: Optional[float] = None,
        cost_status: Optional[str] = None,
        cost_source: Optional[str] = None,
        pricing_version: Optional[str] = None,
        billing_provider: Optional[str] = None,
        billing_base_url: Optional[str] = None,
        billing_mode: Optional[str] = None,
    ) -> None:
        """Set token counters to absolute values (not increment)."""
        def _do(conn):
            conn.execute(
                """UPDATE sessions SET
                   input_tokens = ?,
                   output_tokens = ?,
                   cache_read_tokens = ?,
                   cache_write_tokens = ?,
                   reasoning_tokens = ?,
                   estimated_cost_usd = ?,
                   actual_cost_usd = CASE
                       WHEN ? IS NULL THEN actual_cost_usd
                       ELSE ?
                   END,
                   cost_status = COALESCE(?, cost_status),
                   cost_source = COALESCE(?, cost_source),
                   pricing_version = COALESCE(?, pricing_version),
                   billing_provider = COALESCE(billing_provider, ?),
                   billing_base_url = COALESCE(billing_base_url, ?),
                   billing_mode = COALESCE(billing_mode, ?),
                   model = COALESCE(model, ?)
                   WHERE id = ?""",
                (
                    input_tokens,
                    output_tokens,
                    cache_read_tokens,
                    cache_write_tokens,
                    reasoning_tokens,
                    estimated_cost_usd,
                    actual_cost_usd,
                    actual_cost_usd,
                    cost_status,
                    cost_source,
                    pricing_version,
                    billing_provider,
                    billing_base_url,
                    billing_mode,
                    model,
                    session_id,
                ),
            )
        self._execute_write(_do)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def resolve_session_id(self, session_id_or_prefix: str) -> Optional[str]:
        """Resolve an exact or uniquely prefixed session ID to the full ID."""
        exact = self.get_session(session_id_or_prefix)
        if exact:
            return exact["id"]

        escaped = (
            session_id_or_prefix
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id FROM sessions WHERE id LIKE ? ESCAPE '\\' ORDER BY started_at DESC LIMIT 2",
                (f"{escaped}%",),
            )
            matches = [row["id"] for row in cursor.fetchall()]
        if len(matches) == 1:
            return matches[0]
        return None

    MAX_TITLE_LENGTH = 100

    @staticmethod
    def sanitize_title(title: Optional[str]) -> Optional[str]:
        """Validate and sanitize a session title."""
        if not title:
            return None

        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', title)
        cleaned = re.sub(
            r'[\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff\ufffc\ufff9-\ufffb]',
            '', cleaned,
        )
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        if not cleaned:
            return None

        if len(cleaned) > SessionDB.MAX_TITLE_LENGTH:
            raise ValueError(
                f"Title too long ({len(cleaned)} chars, max {SessionDB.MAX_TITLE_LENGTH})"
            )

        return cleaned

    def set_session_title(self, session_id: str, title: str) -> bool:
        """Set or update a session's title."""
        title = self.sanitize_title(title)
        def _do(conn):
            if title:
                cursor = conn.execute(
                    "SELECT id FROM sessions WHERE title = ? AND id != ?",
                    (title, session_id),
                )
                conflict = cursor.fetchone()
                if conflict:
                    raise ValueError(
                        f"Title '{title}' is already in use by session {conflict['id']}"
                    )
            cursor = conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            return cursor.rowcount
        rowcount = self._execute_write(_do)
        return rowcount > 0

    def get_session_title(self, session_id: str) -> Optional[str]:
        """Get the title for a session, or None."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return row["title"] if row else None

    def get_session_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Look up a session by exact title."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE title = ?", (title,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def resolve_session_by_title(self, title: str) -> Optional[str]:
        """Resolve a title to a session ID."""
        exact = self.get_session_by_title(title)

        escaped = title.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, title, started_at FROM sessions "
                "WHERE title LIKE ? ESCAPE '\\' ORDER BY started_at DESC",
                (f"{escaped} #%",),
            )
            numbered = cursor.fetchall()

        if numbered:
            return numbered[0]["id"]
        elif exact:
            return exact["id"]
        return None

    def get_next_title_in_lineage(self, base_title: str) -> str:
        """Generate the next title in a lineage."""
        match = re.match(r'^(.*?) #(\d+)$', base_title)
        if match:
            base = match.group(1)
        else:
            base = base_title

        escaped = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            cursor = self._conn.execute(
                "SELECT title FROM sessions WHERE title = ? OR title LIKE ? ESCAPE '\\'",
                (base, f"{escaped} #%"),
            )
            existing = [row["title"] for row in cursor.fetchall()]

        if not existing:
            return base

        max_num = 1
        for t in existing:
            m = re.match(r'^.* #(\d+)$', t)
            if m:
                max_num = max(max_num, int(m.group(1)))

        return f"{base} #{max_num + 1}"

    def list_sessions_rich(
        self,
        source: str = None,
        exclude_sources: List[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List sessions with preview (first user message) and last active timestamp."""
        where_clauses = []
        params = []

        if source:
            where_clauses.append("s.source = ?")
            params.append(source)
        if exclude_sources:
            placeholders = ",".join("?" for _ in exclude_sources)
            where_clauses.append(f"s.source NOT IN ({placeholders})")
            params.extend(exclude_sources)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            SELECT s.*,
                COALESCE(
                    (SELECT SUBSTR(REPLACE(REPLACE(m.content, X'0A', ' '), X'0D', ' '), 1, 63)
                     FROM messages m
                     WHERE m.session_id = s.id AND m.role = 'user' AND m.content IS NOT NULL
                     ORDER BY m.timestamp, m.id LIMIT 1),
                    ''
                ) AS _preview_raw,
                COALESCE(
                    (SELECT MAX(m2.timestamp) FROM messages m2 WHERE m2.session_id = s.id),
                    s.started_at
                ) AS last_active
            FROM sessions s
            {where_sql}
            ORDER BY s.started_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
        sessions = []
        for row in rows:
            s = dict(row)
            raw = s.pop("_preview_raw", "").strip()
            if raw:
                text = raw[:60]
                s["preview"] = text + ("..." if len(raw) > 60 else "")
            else:
                s["preview"] = ""
            sessions.append(s)

        return sessions

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str = None,
        tool_name: str = None,
        tool_calls: Any = None,
        tool_call_id: str = None,
        token_count: int = None,
        finish_reason: str = None,
        reasoning: str = None,
        reasoning_details: Any = None,
        codex_reasoning_items: Any = None,
    ) -> int:
        """Append a message to a session. Returns the message row ID."""
        reasoning_details_json = (
            json.dumps(reasoning_details)
            if reasoning_details else None
        )
        codex_items_json = (
            json.dumps(codex_reasoning_items)
            if codex_reasoning_items else None
        )
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None

        num_tool_calls = 0
        if tool_calls is not None:
            num_tool_calls = len(tool_calls) if isinstance(tool_calls, list) else 1

        def _do(conn):
            cursor = conn.execute(
                """INSERT INTO messages (session_id, role, content, tool_call_id,
                   tool_calls, tool_name, timestamp, token_count, finish_reason,
                   reasoning, reasoning_details, codex_reasoning_items)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    role,
                    content,
                    tool_call_id,
                    tool_calls_json,
                    tool_name,
                    time.time(),
                    token_count,
                    finish_reason,
                    reasoning,
                    reasoning_details_json,
                    codex_items_json,
                ),
            )
            msg_id = cursor.lastrowid

            if num_tool_calls > 0:
                conn.execute(
                    """UPDATE sessions SET message_count = message_count + 1,
                       tool_call_count = tool_call_count + ? WHERE id = ?""",
                    (num_tool_calls, session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                    (session_id,),
                )
            return msg_id

        return self._execute_write(_do)

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Load all messages for a session, ordered by timestamp."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp, id",
                (session_id,),
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            msg = dict(row)
            if msg.get("tool_calls"):
                try:
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(msg)
        return result

    def get_messages_as_conversation(self, session_id: str) -> List[Dict[str, Any]]:
        """Load messages in the OpenAI conversation format."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT role, content, tool_call_id, tool_calls, tool_name, "
                "reasoning, reasoning_details, codex_reasoning_items "
                "FROM messages WHERE session_id = ? ORDER BY timestamp, id",
                (session_id,),
            )
            rows = cursor.fetchall()
        messages = []
        for row in rows:
            msg = {"role": row["role"], "content": row["content"]}
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            if row["tool_name"]:
                msg["tool_name"] = row["tool_name"]
            if row["tool_calls"]:
                try:
                    msg["tool_calls"] = json.loads(row["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if row["role"] == "assistant":
                if row["reasoning"]:
                    msg["reasoning"] = row["reasoning"]
                if row["reasoning_details"]:
                    try:
                        msg["reasoning_details"] = json.loads(row["reasoning_details"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                if row["codex_reasoning_items"]:
                    try:
                        msg["codex_reasoning_items"] = json.loads(row["codex_reasoning_items"])
                    except (json.JSONDecodeError, TypeError):
                        pass
            messages.append(msg)
        return messages

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Sanitize user input for safe use in FTS5 MATCH queries."""
        _quoted_parts: list = []

        def _preserve_quoted(m: re.Match) -> str:
            _quoted_parts.append(m.group(0))
            return f"\x00Q{len(_quoted_parts) - 1}\x00"

        sanitized = re.sub(r'"[^"]*"', _preserve_quoted, query)
        sanitized = re.sub(r'[+{}()\"^]', " ", sanitized)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())
        sanitized = re.sub(r"\b(\w+(?:[.-]\w+)+)\b", r'"\1"', sanitized)

        for i, quoted in enumerate(_quoted_parts):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", quoted)

        return sanitized.strip()

    def search_messages(
        self,
        query: str,
        source_filter: List[str] = None,
        exclude_sources: List[str] = None,
        role_filter: List[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Full-text search across session messages using FTS5."""
        if not query or not query.strip():
            return []

        query = self._sanitize_fts5_query(query)
        if not query:
            return []

        where_clauses = ["messages_fts MATCH ?"]
        params: list = [query]

        if source_filter is not None:
            source_placeholders = ",".join("?" for _ in source_filter)
            where_clauses.append(f"s.source IN ({source_placeholders})")
            params.extend(source_filter)

        if exclude_sources is not None:
            exclude_placeholders = ",".join("?" for _ in exclude_sources)
            where_clauses.append(f"s.source NOT IN ({exclude_placeholders})")
            params.extend(exclude_sources)

        if role_filter:
            role_placeholders = ",".join("?" for _ in role_filter)
            where_clauses.append(f"m.role IN ({role_placeholders})")
            params.extend(role_filter)

        where_sql = " AND ".join(where_clauses)
        params.extend([limit, offset])

        sql = f"""
            SELECT
                m.id,
                m.session_id,
                m.role,
                snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet,
                m.content,
                m.timestamp,
                m.tool_name,
                s.source,
                s.model,
                s.started_at AS session_started
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE {where_sql}
            ORDER BY rank
            LIMIT ? OFFSET ?
        """

        with self._lock:
            try:
                cursor = self._conn.execute(sql, params)
            except sqlite3.OperationalError:
                return []
            matches = [dict(row) for row in cursor.fetchall()]

        for match in matches:
            try:
                with self._lock:
                    ctx_cursor = self._conn.execute(
                        """SELECT role, content FROM messages
                           WHERE session_id = ? AND id >= ? - 1 AND id <= ? + 1
                           ORDER BY id""",
                        (match["session_id"], match["id"], match["id"]),
                    )
                    context_msgs = [
                        {"role": r["role"], "content": (r["content"] or "")[:200]}
                        for r in ctx_cursor.fetchall()
                    ]
                match["context"] = context_msgs
            except Exception:
                match["context"] = []

        for match in matches:
            match.pop("content", None)

        return matches

    def search_sessions(
        self,
        source: str = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List sessions, optionally filtered by source."""
        with self._lock:
            if source:
                cursor = self._conn.execute(
                    "SELECT * FROM sessions WHERE source = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
                    (source, limit, offset),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            return [dict(row) for row in cursor.fetchall()]

    def session_count(self, source: str = None) -> int:
        """Count sessions, optionally filtered by source."""
        with self._lock:
            if source:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE source = ?", (source,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]

    def message_count(self, session_id: str = None) -> int:
        """Count messages, optionally for a specific session."""
        with self._lock:
            if session_id:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM messages")
            return cursor.fetchone()[0]

    def export_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Export a single session with all its messages as a dict."""
        session = self.get_session(session_id)
        if not session:
            return None
        messages = self.get_messages(session_id)
        return {**session, "messages": messages}

    def export_all(self, source: str = None) -> List[Dict[str, Any]]:
        """Export all sessions (with messages) as a list of dicts."""
        sessions = self.search_sessions(source=source, limit=100000)
        results = []
        for session in sessions:
            messages = self.get_messages(session["id"])
            results.append({**session, "messages": messages})
        return results

    def clear_messages(self, session_id: str) -> None:
        """Delete all messages for a session and reset its counters."""
        def _do(conn):
            conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            conn.execute(
                "UPDATE sessions SET message_count = 0, tool_call_count = 0 WHERE id = ?",
                (session_id,),
            )
        self._execute_write(_do)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages. Returns True if found."""
        def _do(conn):
            cursor = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,)
            )
            if cursor.fetchone()[0] == 0:
                return False
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return True
        return self._execute_write(_do)

    def prune_sessions(self, older_than_days: int = 90, source: str = None) -> int:
        """Delete sessions older than N days. Returns count of deleted sessions."""
        cutoff = time.time() - (older_than_days * 86400)

        def _do(conn):
            if source:
                cursor = conn.execute(
                    """SELECT id FROM sessions
                       WHERE started_at < ? AND ended_at IS NOT NULL AND source = ?""",
                    (cutoff, source),
                )
            else:
                cursor = conn.execute(
                    "SELECT id FROM sessions WHERE started_at < ? AND ended_at IS NOT NULL",
                    (cutoff,),
                )
            session_ids = [row["id"] for row in cursor.fetchall()]

            for sid in session_ids:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            return len(session_ids)

        return self._execute_write(_do)