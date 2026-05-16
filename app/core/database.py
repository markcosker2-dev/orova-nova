import os
import json
import logging
import time
import signal
import threading
import queue
import atexit
import asyncio
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
                logger.info("📁 Database: SQLite fallback initialized")
            except Exception as e:
                logger.error(f"❌ All database systems failed: {e}")
                cls._sqlite_fallback = False

    @classmethod
    def _init_sqlite_fallback(cls):
        import sqlite3
        conn = sqlite3.connect(cls._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-20000")
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

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
                icebreaker TEXT,
                score INTEGER DEFAULT 0,
                client_id INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                phone TEXT UNIQUE,
                business TEXT,
                reason TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                subject TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lead_id) REFERENCES leads (id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                client_id INTEGER PRIMARY KEY DEFAULT 0,
                leads_found INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                replies_received INTEGER DEFAULT 0,
                meetings_booked INTEGER DEFAULT 0,
                calls_made INTEGER DEFAULT 0,
                proposals_sent INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                t_in INTEGER DEFAULT 0,
                t_out INTEGER DEFAULT 0,
                reqs INTEGER DEFAULT 0,
                content_created INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT,
                niche TEXT,
                target_location TEXT,
                workbook_name TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER DEFAULT 0,
                task_type TEXT,
                winning_approach TEXT,
                success_metric REAL DEFAULT 0.0,
                decay_score REAL DEFAULT 1.0,
                last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER DEFAULT 0,
                operation TEXT,
                latency REAL,
                cost REAL DEFAULT 0.0,
                status TEXT,
                error_msg TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")
        conn.commit()
        conn.close()

    @classmethod
    def _get_conn(cls):
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
                return cls._pool.get(block=True, timeout=5)

    @classmethod
    def _release_conn(cls, conn):
        try:
            cls._pool.put(conn, block=False)
        except queue.Full:
            conn.close()
            with cls._pool_lock:
                cls._active_connections -= 1

    @classmethod
    def _close_all_connections(cls):
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
    def _schedule_async_task(cls, coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        task = loop.create_task(coro)

        def _on_done(task):
            try:
                exc = task.exception()
                if exc:
                    logger.error(f"[AsyncTask] {exc}")
            except asyncio.CancelledError:
                pass

        task.add_done_callback(_on_done)
        return task

    @classmethod
    def _sqlite_query(cls, sql, params=(), fetchone=False, fetchall=False, return_lastrowid=False):
        import sqlite3
        conn = None
        try:
            conn = cls._get_conn()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            res = None
            if fetchone:
                res = cursor.fetchone()
            elif fetchall:
                res = cursor.fetchall()
            elif return_lastrowid:
                res = cursor.lastrowid
            conn.commit()
            return res
        except sqlite3.Error as e:
            logger.error(f"[SQLITE] Query error: {e} | SQL: {sql[:100]}")
            if conn:
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
    async def query(cls, sql, params=(), fetchone=False, fetchall=False, return_lastrowid=False):
        if cls._use_redis and cls._redis_manager:
            raise RuntimeError("Redis query is not implemented in this fallback")
        elif cls._sqlite_fallback:
            return await asyncio.to_thread(cls._sqlite_query, sql, params, fetchone, fetchall, return_lastrowid)
        raise RuntimeError("No database backend available")

    @classmethod
    async def fetchone(cls, sql, params=()):
        return await cls.query(sql, params, fetchone=True)

    @classmethod
    async def fetchall(cls, sql, params=()):
        return await cls.query(sql, params, fetchall=True)

    @classmethod
    async def is_empty(cls):
        if cls._use_redis and cls._redis_manager:
            return len(cls._redis_manager.get_leads(0)) == 0
        elif cls._sqlite_fallback:
            row = await cls.fetchone("SELECT COUNT(*) as cnt FROM leads")
            return not row or int(row["cnt"]) == 0
        return True

    @classmethod
    async def get_state(cls, key, default=None):
        if cls._use_redis and cls._redis_manager:
            try:
                value = cls._redis_manager._redis_op("hget", "state", key)
                if value is None:
                    return default
                return json.loads(value)
            except Exception:
                return default
        elif cls._sqlite_fallback:
            row = cls._sqlite_query("SELECT value FROM state WHERE key = ?", (key,), fetchone=True)
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
        return default

    @classmethod
    async def set_state(cls, key, value):
        stored = json.dumps(value)
        if cls._use_redis and cls._redis_manager:
            cls._redis_manager._redis_op("hset", "state", key, stored)
        elif cls._sqlite_fallback:
            cls._sqlite_query(
                "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                (key, stored)
            )

    @classmethod
    async def run_phase5_migrations(cls):
        if cls._sqlite_fallback:
            await cls.query('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT,
                    niche TEXT,
                    target_location TEXT,
                    workbook_name TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await cls.query('''
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            await cls.query('''
                CREATE TABLE IF NOT EXISTS email_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER,
                    subject TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await cls.query('''
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER DEFAULT 0,
                    task_type TEXT,
                    winning_approach TEXT,
                    success_metric REAL DEFAULT 0.0,
                    decay_score REAL DEFAULT 1.0,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await cls.query('''
                CREATE TABLE IF NOT EXISTS performance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER DEFAULT 0,
                    operation TEXT,
                    latency REAL,
                    cost REAL DEFAULT 0.0,
                    status TEXT,
                    error_msg TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await cls.query("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")
        elif cls._use_redis and cls._redis_manager:
            pass

    @classmethod
    def register_sigterm_handler(cls, loop):
        def _signal_handler(signum, frame):
            logger.info(f"[SIGTERM] Received signal {signum}. Initiating graceful shutdown.")
            try:
                loop.stop()
            except Exception:
                pass

        try:
            signal.signal(signal.SIGINT, _signal_handler)
        except Exception:
            pass
        if hasattr(signal, "SIGTERM"):
            try:
                signal.signal(signal.SIGTERM, _signal_handler)
            except Exception:
                pass

    @classmethod
    async def get_usage_stats(cls):
        metrics = cls.get_metrics(0)
        if not metrics:
            metrics = {}
        totals = {
            "cost": float(metrics.get("cost", 0.0)),
            "t_in": int(metrics.get("t_in", 0)),
            "t_out": int(metrics.get("t_out", 0)),
            "reqs": int(metrics.get("reqs", 0))
        }
        return {"totals": totals, "metrics": metrics}

    @classmethod
    def get_clients(cls):
        if cls._use_redis and cls._redis_manager:
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
            row = cls._sqlite_query("SELECT niche, target_location, workbook_name FROM clients WHERE id = ?", (int(client_id),), fetchone=True)
            if row:
                return {
                    "niche": row["niche"], 
                    "location": row["target_location"],
                    "workbook": row["workbook_name"] or os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")
                }
        return {"niche": "Automotive", "location": "California", "workbook": os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")}

    @classmethod
    def add_client(cls, business_name, niche, target_location):
        client_id = int(time.time())
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
    def save_lead(cls, lead_data, default_vertical="Automotive", client_id=0, sync_to_sheets=True):
        url = (lead_data.get("url") or "").lower()
        # [NUCLEAR SHIELD] Block junk domains at the database entry point
        banned = ["wordreference.com", "dictionary.com", "wikipedia.org", "thesaurus.com", "merriam-webster", "britannica", "quora", "reddit", "glosbe.com", "linguee.com", "definition"]
        if any(b in url for b in banned):
            logger.warning(f"[NUCLEAR SHIELD] Refused to save junk lead: {url}")
            return None

        if cls._use_redis and cls._redis_manager:
            cls._redis_manager.save_lead(lead_data, client_id)
        elif cls._sqlite_fallback:
            business = lead_data.get("business") or lead_data.get("company") or lead_data.get("title")
            url = lead_data.get("url") or ""
            if url:
                existing = cls._sqlite_query("SELECT id FROM leads WHERE url = ? LIMIT 1", (url,), fetchone=True)
                if existing:
                    logger.info(f"[SQLITE] Duplicate lead skipped (URL match): {url}")
                    return
            if business:
                existing = cls._sqlite_query("SELECT id FROM leads WHERE LOWER(business) = LOWER(?) LIMIT 1", (business,), fetchone=True)
                if existing:
                    logger.info(f"[SQLITE] Duplicate lead skipped (name match): {business}")
                    return
            sql = '''INSERT INTO leads (business, url, email, phone, vertical, status, notes, icebreaker, score, client_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'''
            params = (
                business, url, lead_data.get("email"), lead_data.get("phone"),
                lead_data.get("vertical") or default_vertical,
                lead_data.get("status", "New"),
                lead_data.get("notes") or lead_data.get("snippet", ""),
                lead_data.get("icebreaker", ""),
                lead_data.get("score", 0),
                int(client_id)
            )
            lead_id = cls._sqlite_query(sql, params, return_lastrowid=True)
            if lead_id and sync_to_sheets:
                lead_data["id"] = lead_id
                try:
                    config = cls.get_client_config(client_id)
                    workbook = config.get("workbook")
                    from app.skills.sheets_sync import sync_lead_to_sheets
                    cls._schedule_async_task(sync_lead_to_sheets(lead_data, workbook_name=workbook))
                except Exception as exc:
                    logger.warning(f"[SQLITE] Sheet sync could not be scheduled: {exc}")

    @classmethod
    def get_leads(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_leads(client_id)
        elif cls._sqlite_fallback:
            rows = cls._sqlite_query("SELECT * FROM leads WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
            return [dict(r) for r in rows] if rows else []
        return []

    @classmethod
    def get_lead_by_id(cls, lead_id):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_lead(lead_id)
        elif cls._sqlite_fallback:
            row = cls._sqlite_query("SELECT * FROM leads WHERE id = ?", (int(lead_id),), fetchone=True)
            return dict(row) if row else None
        return None

    @classmethod
    def update_lead_status(cls, lead_id, new_status):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.update_lead_status(lead_id, new_status)
        elif cls._sqlite_fallback:
            cls._sqlite_query("UPDATE leads SET status = ? WHERE id = ?", (new_status, int(lead_id)))
            try:
                lead = cls.get_lead_by_id(lead_id)
                client_id = lead.get("client_id", 0) if lead else 0
                config = cls.get_client_config(client_id)
                workbook = config.get("workbook")
                from app.skills.sheets_sync import update_lead_status_sheets
                cls._schedule_async_task(update_lead_status_sheets(int(lead_id), new_status, workbook_name=workbook))
            except Exception as exc:
                logger.warning(f"[SQLITE] Sheet status sync could not be scheduled: {exc}")

    @classmethod
    def get_metrics(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_metrics(client_id)
        elif cls._sqlite_fallback:
            row = cls._sqlite_query("SELECT * FROM metrics WHERE client_id = ?", (int(client_id),), fetchone=True)
            if row:
                return dict(row)
        return {"leads_found": 0, "emails_sent": 0, "replies_received": 0, "meetings_booked": 0, "calls_made": 0, "proposals_sent": 0, "content_created": 0, "cost": 0.0, "t_in": 0, "t_out": 0, "reqs": 0}

    @classmethod
    def get_tasks(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_tasks(client_id)
        return []

    @classmethod
    def get_content(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_content(client_id)
        return []

    @classmethod
    def get_memories(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_memories(client_id)
        return []

    @classmethod
    def get_chat_history(cls, client_id=0):
        if cls._use_redis and cls._redis_manager:
            return cls._redis_manager.get_chat_history(client_id, "default")
        return []

    @classmethod
    def update_metrics(cls, data, client_id=0):
        if cls._use_redis and cls._redis_manager:
            cls._redis_manager.update_metrics(data, client_id)
        elif cls._sqlite_fallback:
            if not data:
                return
            valid_keys = ["leads_found", "emails_sent", "replies_received", "meetings_booked", "calls_made", "proposals_sent", "content_created", "cost", "t_in", "t_out", "reqs"]
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
        if cls._use_redis and cls._redis_manager:
            pass
        elif cls._sqlite_fallback:
            cls._sqlite_query("INSERT INTO email_tracking (lead_id, subject) VALUES (?, ?)", (lead_id, subject))

    @classmethod
    def get_cold_leads(cls, days_threshold=5, client_id=0):
        leads = cls.get_leads(client_id)
        cold_leads = []
        for lead in leads:
            if lead.get("status") in ("Email Sent", "Contacted"):
                last_contacted = lead.get("last_contacted_at")
                if last_contacted:
                    days_since = (time.time() - last_contacted) / 86400
                    if days_since > days_threshold:
                        cold_leads.append(lead)
                else:
                    cold_leads.append(lead)
        return cold_leads

    @classmethod
    def blacklist_lead(cls, email=None, phone=None, business=None, reason=""):
        if cls._use_redis and cls._redis_manager:
            blacklist_key = f"blacklist:{email or phone}"
            data = {"email": email, "phone": phone, "business": business, "reason": reason}
            cls._redis_manager._redis_op("set", blacklist_key, cls._redis_manager._compress_data(data))
            cls._redis_manager._redis_op("expire", blacklist_key, cls._redis_manager.memory_limits["ttl_seconds"])
        elif cls._sqlite_fallback:
            cls._sqlite_query("INSERT OR IGNORE INTO blacklist (email, phone, business, reason) VALUES (?, ?, ?, ?)", (email, phone, business, reason))


    @classmethod
    def log_performance(cls, client_id, operation, latency, cost=0.0, status="success", error_msg=None):
        if cls._sqlite_fallback:
            cls._sqlite_query(
                "INSERT INTO performance_logs (client_id, operation, latency, cost, status, error_msg) VALUES (?, ?, ?, ?, ?, ?)",
                (int(client_id), operation, float(latency), float(cost), status, error_msg)
            )

    @classmethod
    async def get_performance_stats(cls, client_id=0, limit=100):
        if cls._sqlite_fallback:
            rows = await cls.fetchall(
                "SELECT * FROM performance_logs WHERE client_id = ? ORDER BY created_at DESC LIMIT ?",
                (int(client_id), limit)
            )
            return [dict(r) for r in rows] if rows else []
        return []

# Backward compatibility aliases for module-level imports
run_phase5_migrations = DatabaseManager.run_phase5_migrations
register_sigterm_handler = DatabaseManager.register_sigterm_handler
get_usage_stats = DatabaseManager.get_usage_stats
