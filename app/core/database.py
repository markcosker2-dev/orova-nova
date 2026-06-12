import os
import json
import logging
import time
import signal
import threading
import queue
import atexit
import asyncio
import re
from typing import Dict, List, Optional, Any

# Canonical data/DB paths (importable by other modules)
DEFAULT_DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "orova.db")

logger = logging.getLogger(__name__)

class DatabaseManager:
    _redis_manager = None
    _sqlite_fallback = None
    _use_redis = True
    _ready = False
    _ready_event = threading.Event()

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
        cls._ready = True
        cls._ready_event.set()
        logger.info(f"✅ SQLite ready: {cls._db_path}")

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
                action TEXT,           -- 'email_sent', 'call_made', 'follow_up'
                strategy TEXT,         -- 'pas', 'bab', 'aida', 'social_proof'
                niche TEXT,
                recipient TEXT,
                lead_id INTEGER,
                result TEXT,           -- 'sent', 'opened', 'replied', 'bounced', 'meeting'
                quality_score REAL,    -- from proofreader (0-100)
                send_hour INTEGER,     -- hour of day (0-23) for timing analysis
                send_day INTEGER,      -- day of week (0-6)
                metadata TEXT,         -- JSON blob for extra data
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS learned_strategies (
                id TEXT PRIMARY KEY,
                strategy_type TEXT,    -- 'email_framework', 'niche', 'send_timing'
                strategy_value TEXT,   -- 'pas', 'exotic car dealer california', '10:00'
                win_rate REAL,
                sample_size INTEGER,
                confidence TEXT,       -- 'high', 'medium', 'low'
                active INTEGER DEFAULT 1,
                client_id INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS drip_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER UNIQUE, -- one active drip campaign per lead
                sequence_type TEXT,
                status TEXT DEFAULT 'active', -- 'active', 'completed', 'stopped_by_reply', 'paused'
                current_step INTEGER DEFAULT 0,
                last_sent_at TIMESTAMP,
                next_send_at TIMESTAMP,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

    @classmethod
    def get_connection(cls):
        import sqlite3
        conn = sqlite3.connect(cls._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    @classmethod
    def get_clients(cls) -> List[Dict[str, Any]]:
        conn = cls.get_connection()
        try:
            cursor = conn.execute("SELECT * FROM clients WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching clients: {e}")
            return []
        finally:
            conn.close()

    @classmethod
    def get_cold_leads(cls, days_threshold: int, client_id: int = 0) -> List[Dict[str, Any]]:
        conn = cls.get_connection()
        try:
            # Select leads where status is 'Email Sent' or 'Contacted' and updated_at is older than days_threshold
            cursor = conn.execute(
                """SELECT * FROM leads 
                   WHERE client_id = ? 
                   AND status IN ('Email Sent', 'Contacted') 
                   AND datetime(updated_at) < datetime('now', ?)""",
                (client_id, f"-{days_threshold} days")
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching cold leads: {e}")
            return []
        finally:
            conn.close()

    @classmethod
    def update_metrics(cls, metrics_dict: dict, client_id: int = 0):
        conn = cls.get_connection()
        try:
            for key, value in metrics_dict.items():
                conn.execute(
                    "INSERT INTO metrics (client_id, metric_key, metric_value) VALUES (?, ?, ?)",
                    (client_id, key, float(value))
                )
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")
        finally:
            conn.close()

    @classmethod
    async def query(cls, sql: str, params: tuple = None, fetchone: bool = False, fetchall: bool = False):
        loop = asyncio.get_running_loop()
        def _run():
            conn = cls.get_connection()
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
            finally:
                conn.close()
        return await loop.run_in_executor(None, _run)

    @classmethod
    async def fetchone(cls, sql: str, params: tuple = None):
        return await cls.query(sql, params, fetchone=True)

    @classmethod
    async def fetchall(cls, sql: str, params: tuple = None):
        return await cls.query(sql, params, fetchall=True)

    @classmethod
    async def get_state(cls, key: str, default=None):
        row = await cls.fetchone("SELECT value FROM state_store WHERE key = ?", (key,))
        if row:
            try:
                return json.loads(row["value"])
            except: return row["value"]
        return default

    @classmethod
    async def set_state(cls, key: str, value):
        import json
        if not isinstance(value, str):
            value = json.dumps(value)
        await cls.query("INSERT OR REPLACE INTO state_store (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))

    @classmethod
    def get_metrics(cls, client_id: int = 0) -> dict:
        conn = cls.get_connection()
        try:
            # Aggregate counts from leads table
            total = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ?", (client_id,)).fetchone()[0]
            contacted = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status IN ('Contacted','Email Sent')", (client_id,)).fetchone()[0]
            replied = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status = 'Replied'", (client_id,)).fetchone()[0]
            meetings = conn.execute("SELECT COUNT(*) FROM leads WHERE client_id = ? AND status = 'Meeting Booked'", (client_id,)).fetchone()[0]
            
            # Fetch latest specific metrics
            calls_made_row = conn.execute(
                "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'calls_made' ORDER BY recorded_at DESC LIMIT 1",
                (client_id,)
            ).fetchone()
            calls_made = int(calls_made_row[0]) if calls_made_row else 0

            proposals_sent_row = conn.execute(
                "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'proposals_sent' ORDER BY recorded_at DESC LIMIT 1",
                (client_id,)
            ).fetchone()
            proposals_sent = int(proposals_sent_row[0]) if proposals_sent_row else 0

            cost_row = conn.execute(
                "SELECT metric_value FROM metrics WHERE client_id = ? AND metric_key = 'cost' ORDER BY recorded_at DESC LIMIT 1",
                (client_id,)
            ).fetchone()
            cost = float(cost_row[0]) if cost_row else 0.0

            return {
                "leads_found": total, "emails_sent": contacted,
                "replies_received": replied, "meetings_booked": meetings,
                "calls_made": calls_made, "proposals_sent": proposals_sent,
                "cost": cost
            }
        finally:
            conn.close()

    @classmethod
    async def get_performance_stats(cls, client_id: int = 0) -> dict:
        return {
            "avg_leads_per_day": 0,
            "conversion_rate": 0,
            "response_time_avg": 0,
        }

    @classmethod
    def _is_duplicate_lead(cls, email: str, domain: str = "", client_id: int = 0) -> bool:
        """Check if a lead with the same email or domain already exists in the DB."""
        conn = cls.get_connection()
        try:
            if email:
                row = conn.execute(
                    "SELECT id FROM leads WHERE lower(email) = lower(?) AND client_id = ? LIMIT 1",
                    (email.strip(), client_id)
                ).fetchone()
                if row:
                    return True
            if domain:
                row = conn.execute(
                    "SELECT id FROM leads WHERE lower(website) LIKE ? AND client_id = ? LIMIT 1",
                    (f"%{domain.lower()}%", client_id)
                ).fetchone()
                if row:
                    return True
            return False
        except Exception as e:
            logger.error(f"Duplicate check failed: {e}")
            return False
        finally:
            conn.close()

    @classmethod
    def save_lead(cls, lead: dict, sync_to_sheets: bool = True, default_vertical: str = None, client_id: int = 0) -> int:
        """Save a lead with automatic deduplication. Returns lead_id or -1 if duplicate.
        If sync_to_sheets=True, automatically syncs to Google Sheets CRM."""
        email = lead.get("email", "").strip()
        url = lead.get("url") or lead.get("website", "")
        domain = ""
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
            except: pass
        cid = lead.get("client_id") or client_id or 0
        if cls._is_duplicate_lead(email, domain, client_id=cid):
            logger.info(f"[DEDUP] Skipping duplicate lead: {email or domain}")
            return -1
        conn = cls.get_connection()
        try:
            vertical = lead.get("vertical") or default_vertical or ""
            cursor = conn.execute(
                """INSERT INTO leads (business, owner, url, website, email, phone, vertical, status, notes, icebreaker, score, client_id, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?, ?, CURRENT_TIMESTAMP)""",
                (lead.get("business",""), lead.get("owner",""), lead.get("url",""),
                 lead.get("website",""), email, lead.get("phone",""),
                 vertical, lead.get("status","New"), lead.get("notes",""),
                 lead.get("icebreaker",""), lead.get("score",0), cid)
            )
            lead_id = cursor.lastrowid
            conn.commit()
            return lead_id
        finally:
            conn.close()


    @classmethod
    def _close_all_connections(cls):
        logger.info("Database connections closed")

    @classmethod
    def register_sigterm_handler(cls, loop):
        try:
            loop.add_signal_handler(signal.SIGTERM, cls._close_all_connections)
        except: pass

    @classmethod
    async def run_phase5_migrations(cls):
        conn = cls.get_connection()
        try:
            # Add columns if missing
            for col in ["owner", "website", "email", "phone", "vertical", "icebreaker", "score"]:
                try:
                    conn.execute(f"ALTER TABLE leads ADD COLUMN {col} TEXT")
                except: pass
            try:
                conn.execute("ALTER TABLE leads ADD COLUMN score REAL DEFAULT 0")
            except: pass
            conn.commit()
        finally:
            conn.close()

    @classmethod
    async def is_empty(cls) -> bool:
        row = await cls.fetchone("SELECT COUNT(*) as cnt FROM leads")
        return row is None or row["cnt"] == 0