"""[A-01] Database base — connection pool, init, and query primitives.

Shared infrastructure used by all repository mixins.
"""
import os
import json
import logging
import signal
import threading
import queue
import atexit
import asyncio
from contextlib import contextmanager
from typing import Dict, List, Optional, Any

# Canonical data/DB paths (importable by other modules)
DEFAULT_DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "orova.db")

logger = logging.getLogger(__name__)


class _DBBase:
    """Base class providing connection pool management and query primitives."""

    _redis_manager = None
    _sqlite_fallback = None
    _use_redis = True
    _ready = False
    _ready_event = threading.Event()

    # ── Initialization ──────────────────────────────────────────────
    @classmethod
    def init_db(cls):
        try:
            from app.core.redis_manager import redis_manager
            cls._redis_manager = redis_manager
            cls._use_redis = True
            cls.mark_ready()
            logger.info("✅ FREE Database: Upstash Redis initialized")
        except ImportError:
            logger.info("ℹ️ Redis manager unavailable; using SQLite fallback.")
            cls._use_redis = False
        except Exception as e:
            logger.warning(f"⚠️  Redis init failed: {e}")
            cls._use_redis = False

        if not cls._use_redis:
            try:
                import sqlite3
                cls._db_path = DB_PATH
                cls._pool = queue.Queue(maxsize=10)
                cls._pool_lock = threading.Lock()
                cls._max_connections = 10
                cls._active_connections = 0
                cls._sqlite_fallback = True
                atexit.register(cls._close_all_connections)
                cls._init_sqlite_fallback()
            except Exception as e:
                logger.critical(f"❌ Database init failed: {e}")
                raise

    @classmethod
    def wait_for_ready(cls, timeout: float = 30.0) -> bool:
        """Wait until the database is fully initialized.
        Returns True if ready, False if timeout."""
        if cls._ready:
            return True
        ready = cls._ready_event.wait(timeout=timeout)
        cls._ready = ready
        return ready

    @classmethod
    def mark_ready(cls):
        cls._ready = True
        cls._ready_event.set()

    @classmethod
    def is_ready(cls) -> bool:
        return cls._ready

    # ── SQLite Fallback Init ──────────────────────────────────────────────
    @classmethod
    def _init_sqlite_fallback(cls):
        import sqlite3
        # Set WAL pragmas on a temporary connection, then populate the pool
        conn = sqlite3.connect(cls._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.commit()
        cls._init_tables(conn)
        conn.close()
        # Populate the connection pool
        for _ in range(cls._max_connections):
            pool_conn = sqlite3.connect(cls._db_path, check_same_thread=False)
            pool_conn.row_factory = sqlite3.Row
            pool_conn.execute("PRAGMA journal_mode=WAL")
            pool_conn.execute("PRAGMA busy_timeout=5000")
            pool_conn.execute("PRAGMA synchronous=NORMAL")
            pool_conn.execute("PRAGMA cache_size=-8000")
            pool_conn.execute("PRAGMA temp_store=MEMORY")
            cls._pool.put(pool_conn)
        cls._ready = True
        cls._ready_event.set()
        logger.info(f"✅ SQLite ready: {cls._db_path} (pool size: {cls._max_connections})")

    @classmethod
    def reset_sqlite_fresh(cls):
        """Discard the current SQLite file (and its WAL sidecars) and re-init an
        empty DB.

        Recovery path when a restored snapshot cannot be opened: a fresh empty
        DB keeps the service up (Sheets can repopulate leads) instead of
        crashing startup with exit 3. Best-effort — never raises."""
        try:
            cls._close_all_connections()
        except Exception:
            pass
        # Remove the main DB and its -wal/-shm sidecars: leaving stale sidecars
        # behind is what corrupts a swapped-in file ("database disk image is
        # malformed"), so a clean reset must clear all three.
        for path in (cls._db_path, cls._db_path + "-wal", cls._db_path + "-shm"):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"[DB] Could not remove {path} during reset: {e}")
        cls._init_sqlite_fallback()
        logger.warning("[DB] Re-initialized a fresh empty SQLite DB after an unusable restore.")

    @classmethod
    def _init_tables(cls, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business TEXT,
                owner TEXT,
                url TEXT,
                website TEXT,
                email TEXT,
                phone TEXT,
                vertical TEXT,
                status TEXT DEFAULT 'New',
                notes TEXT,
                icebreaker TEXT,
                score REAL DEFAULT 0,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT,
                niche TEXT,
                target_location TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                category TEXT,
                content TEXT,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER DEFAULT 0,
                metric_key TEXT,
                metric_value REAL DEFAULT 0,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS state_store (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL DEFAULT '',
                winning_approach TEXT NOT NULL DEFAULT '',
                client_id INTEGER NOT NULL DEFAULT 0,
                pattern_type TEXT,
                content TEXT,
                decay_score REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS client_quotas (
                client_id INTEGER PRIMARY KEY,
                apollo_credits_used INTEGER DEFAULT 0,
                apollo_credits_limit INTEGER DEFAULT 10000,
                emails_sent_today INTEGER DEFAULT 0,
                emails_daily_limit INTEGER DEFAULT 50,
                reset_date TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS outreach_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT,
                strategy TEXT,
                niche TEXT,
                recipient TEXT,
                lead_id INTEGER,
                result TEXT,
                quality_score REAL,
                send_hour INTEGER,
                send_day INTEGER,
                metadata TEXT,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS learned_strategies (
                id TEXT PRIMARY KEY,
                strategy_type TEXT,
                strategy_value TEXT,
                win_rate REAL,
                sample_size INTEGER,
                confidence TEXT,
                active INTEGER DEFAULT 1,
                client_id INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS skill_versions (
                id TEXT PRIMARY KEY,
                skill_name TEXT NOT NULL,
                version_label TEXT NOT NULL,
                code_hash TEXT,
                source TEXT NOT NULL DEFAULT 'builtin',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS skill_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                version_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                latency_ms REAL,
                client_id INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_skill_outcomes_name ON skill_outcomes(skill_name, version_id);
            CREATE TABLE IF NOT EXISTS improvement_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_type TEXT NOT NULL,
                subject_name TEXT NOT NULL,
                action TEXT NOT NULL,
                rationale TEXT,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS drip_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER UNIQUE,
                sequence_type TEXT,
                status TEXT DEFAULT 'active',
                current_step INTEGER DEFAULT 0,
                last_sent_at TIMESTAMP,
                next_send_at TIMESTAMP,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cls._ensure_leads_unique_index(conn)
        cls._migrate_columns(conn)

    @classmethod
    def _ensure_leads_unique_index(cls, conn):
        """Create the leads dedup index, self-healing pre-existing duplicates.

        Databases created before the UNIQUE index was introduced may already
        contain duplicate (lower(email), client_id) rows, which makes the
        CREATE UNIQUE INDEX fail and aborts the whole init. Dedupe first
        (keeping the oldest row), then create the index. Rows with NULL
        email/client_id are left alone — SQLite UNIQUE treats NULLs as
        distinct, so they never conflict with the index.
        """
        import sqlite3
        create_sql = (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email_client "
            "ON leads(lower(email), client_id)"
        )
        try:
            conn.execute(create_sql)
        except sqlite3.IntegrityError:
            removed = conn.execute(
                """
                DELETE FROM leads
                WHERE email IS NOT NULL AND client_id IS NOT NULL
                  AND id NOT IN (
                    SELECT MIN(id) FROM leads
                    WHERE email IS NOT NULL AND client_id IS NOT NULL
                    GROUP BY lower(email), client_id
                  )
                """
            ).rowcount
            logger.warning(
                f"⚠️ Removed {removed} duplicate lead(s) blocking idx_leads_email_client; keeping oldest row per (email, client)"
            )
            conn.execute(create_sql)
        conn.commit()

    @classmethod
    def _migrate_columns(cls, conn):
        """Add missing columns to existing tables (safe, idempotent)."""
        migrations = [
            ("leads", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("leads", "email_status", "TEXT DEFAULT ''"),
            ("leads", "owner_title", "TEXT DEFAULT ''"),
            ("leads", "linkedin_url", "TEXT DEFAULT ''"),
            ("memories", "embedding", "TEXT"),
            ("metrics", "metric_value", "REAL DEFAULT 0"),
            ("learned_strategies", "wilson_score", "REAL DEFAULT 0"),
            ("learned_patterns", "task_type", "TEXT"),
            ("learned_patterns", "winning_approach", "TEXT"),
            ("learned_patterns", "client_id", "INTEGER DEFAULT 0"),
            ("learned_patterns", "created_at", "TIMESTAMP"),
        ]
        for table, column, col_def in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                conn.commit()
                logger.info(f"[DB MIGRATION] Added {table}.{column}")
            except Exception:
                pass  # Column already exists, ignore

        # Backfill NULL key columns in learned_patterns so the unique index
        # won't fail on legacy rows with NULL task_type/winning_approach/client_id.
        # First, deduplicate: if multiple rows would collapse to the same key
        # after backfill, keep only the one with the highest decay_score (or
        # most recent last_used_at as tiebreaker) and delete the rest.
        try:
            conn.execute("""
                DELETE FROM learned_patterns
                WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY
                                       COALESCE(task_type, ''),
                                       COALESCE(winning_approach, ''),
                                       COALESCE(client_id, 0)
                                   ORDER BY decay_score DESC, last_used_at DESC
                               ) AS rn
                        FROM learned_patterns
                    ) WHERE rn = 1
                )
            """)
            conn.commit()
        except Exception:
            pass  # Table empty or columns missing — safe to ignore

        try:
            conn.execute(
                "UPDATE learned_patterns SET task_type = '' WHERE task_type IS NULL"
            )
            conn.execute(
                "UPDATE learned_patterns SET winning_approach = '' WHERE winning_approach IS NULL"
            )
            conn.execute(
                "UPDATE learned_patterns SET client_id = 0 WHERE client_id IS NULL"
            )
            conn.commit()
        except Exception:
            pass  # Table empty or columns missing — safe to ignore

        # Backfill created_at for existing learned_patterns rows that have NULL
        try:
            conn.execute(
                "UPDATE learned_patterns SET created_at = CURRENT_TIMESTAMP"
                " WHERE created_at IS NULL"
            )
            conn.commit()
        except Exception:
            pass  # Table empty or column missing — safe to ignore

        # Ensure created_at is auto-populated for new rows even on migrated DBs
        # where ALTER TABLE couldn't add a DEFAULT. The trigger fires on INSERT
        # only when created_at is NULL, matching the fresh-table DEFAULT behavior.
        try:
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_learned_patterns_created_at
                AFTER INSERT ON learned_patterns
                FOR EACH ROW
                WHEN NEW.created_at IS NULL
                BEGIN
                    UPDATE learned_patterns SET created_at = CURRENT_TIMESTAMP
                    WHERE id = NEW.id;
                END
            """)
            conn.commit()
        except Exception:
            pass  # Trigger creation failure is non-fatal

        # Ensure unique index exists for learned_patterns upsert conflict target
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_patterns_unique"
                " ON learned_patterns(task_type, winning_approach, client_id)"
            )
            conn.commit()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create unique index idx_learned_patterns_unique: {exc}"
            ) from exc

    # ── Connection Pool ──────────────────────────────────────────────
    @classmethod
    def get_connection(cls):
        """Acquire a connection from the pool (blocking, with timeout).
        Always use `return_connection()` or the `connection()` context manager
        to release the connection back to the pool."""
        try:
            conn = cls._pool.get(timeout=5.0)
            with cls._pool_lock:
                cls._active_connections += 1
            return conn
        except queue.Empty:
            # Pool exhausted — create a temporary overflow connection
            import sqlite3
            logger.warning("[DB] Pool exhausted, creating overflow connection")
            conn = sqlite3.connect(cls._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            with cls._pool_lock:
                cls._active_connections += 1
            return conn

    @classmethod
    def return_connection(cls, conn):
        """Return a connection to the pool. If pool is full, close it."""
        try:
            with cls._pool_lock:
                cls._active_connections -= 1
            cls._pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:
                pass

    @classmethod
    @contextmanager
    def connection(cls):
        """Context manager for auto-releasing pooled connections."""
        conn = cls.get_connection()
        try:
            yield conn
        finally:
            cls.return_connection(conn)

    # ── Query Primitives ──────────────────────────────────────────────
    @classmethod
    async def query(cls, sql: str, params: tuple = None, fetchone: bool = False, fetchall: bool = False):
        loop = asyncio.get_running_loop()
        def _run():
            with cls.connection() as conn:
                try:
                    cursor = conn.cursor()
                    if params:
                        cursor.execute(sql, params)
                    else:
                        cursor.execute(sql)
                    if fetchone:
                        return cursor.fetchone()
                    if fetchall:
                        return cursor.fetchall()
                    conn.commit()
                    return {"status": "ok", "rows_affected": cursor.rowcount}
                except Exception:
                    conn.rollback()
                    raise
        return await loop.run_in_executor(None, _run)

    @classmethod
    async def fetchone(cls, sql: str, params: tuple = None):
        return await cls.query(sql, params, fetchone=True)

    @classmethod
    async def fetchall(cls, sql: str, params: tuple = None):
        return await cls.query(sql, params, fetchall=True)

    # ── Shutdown ──────────────────────────────────────────────────────
    @classmethod
    def _close_all_connections(cls):
        """Drain and close all pooled connections on shutdown."""
        closed = 0
        while not cls._pool.empty():
            try:
                conn = cls._pool.get_nowait()
                conn.close()
                closed += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error closing pooled connection: {e}")
        # This also runs from an atexit hook, when the log stream may already
        # be closed (pytest capture teardown, interpreter shutdown) — logging
        # then prints a spurious "--- Logging error ---" traceback. Suppress
        # handler errors for this one farewell line only.
        prev_raise = logging.raiseExceptions
        logging.raiseExceptions = False
        try:
            logger.info(f"Database connections closed (drained {closed} from pool)")
        finally:
            logging.raiseExceptions = prev_raise

    @classmethod
    def register_sigterm_handler(cls, loop):
        try:
            loop.add_signal_handler(signal.SIGTERM, cls._close_all_connections)
        except Exception:
            pass  # SIGTERM handler registration failed (e.g., on Windows)

    @classmethod
    async def run_phase5_migrations(cls):
        with cls.connection() as conn:
            try:
                for col in ["owner", "website", "email", "phone", "vertical", "icebreaker"]:
                    try:
                        conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
                    except Exception:
                        pass  # Column already exists or unsupported
                try:
                    conn.execute("ALTER TABLE leads ADD COLUMN score REAL DEFAULT 0")
                except Exception:
                    pass  # Column already exists or unsupported
                conn.commit()
            except Exception as e:
                logger.error(f"Phase 5 migration error: {e}")

    @classmethod
    async def is_empty(cls) -> bool:
        row = await cls.fetchone("SELECT COUNT(*) as cnt FROM leads")
        return row is None or row["cnt"] == 0
