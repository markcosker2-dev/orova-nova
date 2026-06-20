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
                pattern_type TEXT,
                content TEXT,
                decay_score REAL DEFAULT 1.0,
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
        cls._migrate_columns(conn)

    @classmethod
    def _migrate_columns(cls, conn):
        """Add missing columns to existing tables (safe, idempotent)."""
        migrations = [
            ("leads", "updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("metrics", "metric_value", "REAL DEFAULT 0"),
        ]
        for table, column, col_def in migrations:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
                conn.commit()
                logger.info(f"[DB MIGRATION] Added {table}.{column}")
            except Exception:
                pass  # Column already exists, ignore

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
        logger.info(f"Database connections closed (drained {closed} from pool)")

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
                for col in ["owner", "website", "email", "phone", "vertical", "icebreaker", "score"]:
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
