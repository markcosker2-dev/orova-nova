import os
import logging
import time
import threading
import queue
import atexit
from typing import Dict, List, Optional, Any

# Canonical data/DB paths (importable by other modules)
# NOTE: keep DB on the DATA_DIR so Render disk mounts (or any persistent volume) can target one directory.
DEFAULT_DATA_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../app
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "orova.db")

logger = logging.getLogger(__name__)

# FREE Database Manager - Redis Primary, SQLite Fallback
class DatabaseManager:
    """FREE Database Manager — Upstash Redis Primary, SQLite Fallback."""

    _redis_manager = None
    _sqlite_fallback = None
    _use_redis = True

    @classmethod
    def init_db(cls):
        """Initialize FREE database system."""
        # Try Redis first (FREE Upstash)
        try:
            from app.core.redis_manager import redis_manager
            cls._redis_manager = redis_manager
            cls._use_redis = True
            logger.info("✅ FREE Database: Upstash Redis initialized")
        except Exception as e:
            logger.warning(f"⚠️  Redis init failed: {e}")
            cls._use_redis = False

        # Fallback to SQLite if Redis fails
        if not cls._use_redis:
            try:
                import sqlite3
                import threading

                # SQLite connection pool
                cls._db_path = DB_PATH
                cls._pool = queue.Queue(maxsize=10)
                cls._pool_lock = threading.Lock()
                cls._max_connections = 10
                cls._active_connections = 0
                cls._sqlite_fallback = True
                
                # Register cleanup hook
                atexit.register(cls._close_all_connections)

                # Initialize SQLite schema (legacy)
                cls._init_sqlite_fallback()
                logger.info("📁 Database: SQLite fallback initialized")
            except Exception as e:
                logger.error(f"❌ All database systems failed: {e}")
                cls._sqlite_fallback = False

    @classmethod
    def _init_sqlite_fallback(cls):
        """Initialize SQLite as fallback."""
        import sqlite3

        conn = sqlite3.connect(cls._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-20000")
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        # Minimal schema for fallback
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business TEXT,
                url TEXT,
                email TEXT,
                phone TEXT,
                vertical TEXT,
                status TEXT DEFAULT 'New',
                notes TEXT,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                client_id INTEGER PRIMARY KEY DEFAULT 0,
                leads_found INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                replies_received INTEGER DEFAULT 0
            )
        ''')

        cursor.execute("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")
        conn.commit()
        conn.close()

    @classmethod
    def _get_conn(cls):
        """Get a connection from the pool, or create new if pool is empty."""
        import sqlite3
        try:
            return cls._pool.get(block=False)
        except queue.Empty:
            with cls._pool_lock:
                if cls._active_connections < cls._max_connections:
                    conn = sqlite3.connect(cls._db_path, timeout=30, check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=-20000")
                    cls._active_connections += 1
                    return conn
                # Wait up to 5 seconds for an available connection
                return cls._pool.get(block=True, timeout=5)

    @classmethod
    def _release_conn(cls, conn):
        """Return connection to pool or close if pool is full."""
        try:
            cls._pool.put(conn, block=False)
        except queue.Full:
            conn.close()
            with cls._pool_lock:
                cls._active_connections -= 1

    @classmethod
    def _close_all_connections(cls):
        """Close all connections in the pool on exit."""
        while not cls._pool.empty():
            try:
                conn = cls._pool.get(block=False)
                conn.close()
            except (queue.Empty, Exception):
                pass
        with cls._pool_lock:
            cls._active_connections = 0
        logger.info("SQLite connection pool cleaned up")

    @classmethod
    def _sqlite_query(cls, sql, params=(), fetchone=False, fetchall=False):
        """SQLite fallback query method with proper connection pooling."""
        import sqlite3
        conn = None
        try:
            conn = cls._get_conn()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            res: Any = None
            if fetchone:
                res = cursor.fetchone()
            elif fetchall:
                res = cursor.fetchall()
            conn.commit()
            return res
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] Query error: {e} | SQL: {sql[:100]}")
            if conn:
                # Force close broken connection
                try:
                    conn.close()
                    with cls._pool_lock:
                        cls._active_connections -= 1
                except:
                    pass
            raise
        finally:
            if conn:
                cls._release_conn(conn)

    @classmethod
    def get_clients(cls):
        """Get all active clients."""
        if cls._use_redis and cls._redis_manager:
            # Redis stores clients as hash
            clients_data = cls._redis_manager._redis_op("hgetall", "clients") or {}
            clients = []
            for client_id, client_json in clients_data.items():
                try:
                    client = cls._redis_manager._decompress_data(client_json)
                    if client.get("is_active", True):
                        clients.append(client)
                except:
                    continue
            return clients
        elif cls._sqlite_fallback:
            rows = cls._sqlite_query("SELECT * FROM clients WHERE is_active=1", fetchall=True)
            return [dict(r) for r in rows] if rows else []
        return []

    @classmethod
    def get_client_config(cls, client_id=0):
        """Get the niche and location for a specific client."""
        if client_id == 0:
            return {"niche": os.getenv("VERTICAL_NAME", "Automotive"), "location": "California"}

        if cls._use_redis and cls._redis_manager:
            client_json = cls._redis_manager._redis_op("hget", "clients", str(client_id))
            if client_json:
                try:
                    client = cls._redis_manager._decompress_data(client_json)
                    return {"niche": client.get("niche"), "location": client.get("target_location")}
                except:
                    pass

        elif cls._sqlite_fallback:
            row = cls._sqlite_query("SELECT niche, target_location FROM clients WHERE id = ?", (int(client_id),), fetchone=True)
            if row:
                return {"niche": row["niche"], "location": row["target_location"]}

        return {"niche": "Automotive", "location": "California"}

    @classmethod
    def add_client(cls, business_name, niche, target_location):
        """Add a new client."""
        client_id = int(time.time())  # Simple ID generation
        client_data = {
            "id": client_id,
            "business_name": business_name,
            "niche": niche,
            "target_location": target_location,
            "is_active": True,
            "created_at": time.time()
        }

        if cls._use_redis and cls._redis_manager:
            client_json = cls._redis_manager._compress_data(client_data)
            cls._redis_manager._redis_op("hset", "clients", str(client_id), client_json)
            cls._redis_manager._redis_op("expire", "clients", cls._redis_manager.memory_limits["ttl_seconds"])
        elif cls._sqlite_fallback:
            cls._sqlite_query(
                "INSERT INTO clients (business_name, niche, target_location) VALUES (?, ?, ?)",
                (business_name, niche, target_location)
            )

    @classmethod
    def save_lead(cls, lead_data, default_vertical="Automotive", client_id=0):
        """Save a lead with FREE Redis deduplication."""
        if cls._use_redis and cls._redis_manager:
            cls._redis_manager.save_lead(lead_data, client_id)
        elif cls._sqlite_fallback:
            # Legacy SQLite fallback
            business = lead_data.get("business") or lead_data.get("company") or lead_data.get("title")
            url = lead_data.get("url") or ""

            # Deduplication
            if url:
                existing = cls._sqlite_query(
                    "SELECT id FROM leads WHERE url = ? LIMIT 1", (url,), fetchone=True
                )
                if existing:
                    logger.info(f"[SQLITE] Duplicate lead skipped (URL match): {url}")
                    return

            if business:
                existing = cls._sqlite_query(
                    "SELECT id FROM leads WHERE LOWER(business) = LOWER(?) LIMIT 1", (business,), fetchone=True
                )
                if existing:
                    logger.info(f"[SQLITE] Duplicate lead skipped (name match): {business}")
                    return

            sql = '''
                INSERT INTO leads (business, url, email, phone, vertical, status, notes, client_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            '''
            params = (
                business,
                url,
                lead_data.get("email"),
                lead_data.get("phone"),
                lead_data.get("vertical") or default_vertical,
                lead_data.get("status", "New"),
                lead_data.get("notes") or lead_data.get("snippet", ""),
                int(client_id)
            )
            cls._sqlite_query(sql, params)

    @classmethod
    def get_leads(cls, client_id=0):
        """Get all leads for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_leads(client_id)
        elif cls._sqlite_fallback:
            rows = cls._sqlite_query("SELECT * FROM leads WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
            return [dict(r) for r in rows] if rows else []
        return []

    @classmethod
    def get_metrics(cls, client_id=0):
        """Get metrics for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_metrics(client_id)
        elif cls._sqlite_fallback:
            row = cls._sqlite_query("SELECT * FROM metrics WHERE client_id = ?", (int(client_id),), fetchone=True)
            if row:
                return dict(row)
        return {"leads_found": 0, "emails_sent": 0, "replies_received": 0, "meetings_booked": 0, "calls_made": 0, "proposals_sent": 0}

    @classmethod
    def get_tasks(cls, client_id=0):
        """Get all tasks for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_tasks(client_id)
        return []

    @classmethod
    def get_content(cls, client_id=0):
        """Get all content for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_content(client_id)
        return []

    @classmethod
    def get_memories(cls, client_id=0):
        """Get all memories for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_memories(client_id)
        return []

    @classmethod
    def get_chat_history(cls, client_id=0):
        """Get chat history for a client."""
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_chat_history(client_id, "default")
        return []
    @classmethod
    def update_metrics(cls, data, client_id=0):
        """Update metrics (merge, not overwrite)."""
        if cls._use_redis and cls._redis_manager:
            cls._redis_manager.update_metrics(data, client_id)
        elif cls._sqlite_fallback:
            if not data:
                return
            valid_keys = ["leads_found", "emails_sent", "replies_received", "meetings_booked", "calls_made", "proposals_sent"]
            keys = [k for k in data.keys() if k in valid_keys]
            if not keys:
                return

            cls._sqlite_query("INSERT OR IGNORE INTO metrics (client_id) VALUES (?)", (int(client_id),))

            set_clause = ", ".join([f"{k} = ?" for k in keys])
            vals = [data[k] for k in keys]
            vals.append(int(client_id))
            cls._sqlite_query(f"UPDATE metrics SET {set_clause} WHERE client_id = ?", tuple(vals))

    @classmethod
    def log_email_sent(cls, lead_id, subject):
        """Log an email send for cold-lead timing."""
        # Simplified for Redis - just track in metrics
        if cls._use_redis and cls._redis_manager:
            # Could be extended to track per-lead email history in Redis
            pass
        elif cls._sqlite_fallback:
            cls._sqlite_query(
                "INSERT INTO email_tracking (lead_id, subject) VALUES (?, ?)",
                (lead_id, subject)
            )

    @classmethod
    def get_cold_leads(cls, days_threshold=5, client_id=0):
        """Get leads that were emailed but haven't replied within X days."""
        # Simplified for free tier - return leads marked as contacted but not replied
        leads = cls.get_leads(client_id)
        cold_leads = []

        for lead in leads:
            if lead.get("status") in ("Email Sent", "Contacted"):
                # Check if it was contacted more than threshold days ago
                last_contacted = lead.get("last_contacted_at")
                if last_contacted:
                    days_since = (time.time() - last_contacted) / 86400
                    if days_since > days_threshold:
                        cold_leads.append(lead)
                else:
                    # If no timestamp, assume it's old enough
                    cold_leads.append(lead)

        return cold_leads
