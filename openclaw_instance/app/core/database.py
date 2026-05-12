import sqlite3
import os
import logging
import threading
import queue
import atexit

logger = logging.getLogger(__name__)

# Data directory — respects DATA_DIR env var for persistent Linux deployment
DEFAULT_DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "orova.db")

class DatabaseManager:
    """Manages SQLite storage for OROVA Mission Control."""
    
    # SQLite connection pool
    _pool = queue.Queue(maxsize=10)
    _pool_lock = threading.Lock()
    _max_connections = 10
    _active_connections = 0
    _db_initialized = False

    @classmethod
    def _get_conn(cls):
        """Get a connection from the pool, or create new if pool is empty."""
        try:
            return cls._pool.get(block=False)
        except queue.Empty:
            with cls._pool_lock:
                if cls._active_connections < cls._max_connections:
                    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=-20000")
                    conn.execute("PRAGMA busy_timeout=5000")
                    conn.execute("PRAGMA foreign_keys=ON")
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

    @staticmethod
    def init_db():
        # First, try to restore from Google Drive if local DB is missing/wiped
        try:
            from app.skills.drive_backup import restore_database
            restore_database(DB_PATH)
        except Exception as e:
            logger.error(f"[DB] Cloud Restore skipped: {e}")

        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        cursor = conn.cursor()
        
        # Phase 10: Clients Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT,
                niche TEXT,
                target_location TEXT,
                meta_ads_token TEXT,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Metrics Table (Single row per client)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                client_id INTEGER PRIMARY KEY DEFAULT 0,
                leads_found INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                replies_received INTEGER DEFAULT 0,
                meetings_booked INTEGER DEFAULT 0,
                calls_made INTEGER DEFAULT 0,
                proposals_sent INTEGER DEFAULT 0
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")
        
        # Leads Table — with url and created_at
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business TEXT,
                url TEXT,
                contact TEXT,
                phone TEXT,
                email TEXT,
                vertical TEXT,
                score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'New',
                notes TEXT,
                client_id INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Migration: add url column if missing (existing DBs)
        try:
            cursor.execute("SELECT url FROM leads LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE leads ADD COLUMN url TEXT")
            logger.info("[DB] Migrated: added 'url' column to leads table")

        # Migration: add created_at column if missing
        try:
            cursor.execute("SELECT created_at FROM leads LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE leads ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            logger.info("[DB] Migrated: added 'created_at' column to leads table")

        # Tasks Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                assignee TEXT,
                priority TEXT,
                status TEXT,
                client_id INTEGER DEFAULT 0,
                due TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Content Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content (
                id TEXT PRIMARY KEY,
                title TEXT,
                type TEXT,
                stage TEXT,
                idea TEXT,
                script TEXT,
                client_id INTEGER DEFAULT 0,
                image TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Memories Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                category TEXT,
                content TEXT,
                client_id INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Chat History Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                client_id INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Email Tracking Table — tracks when emails were sent to each lead
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                subject TEXT,
                status TEXT DEFAULT 'sent',
                opened_at DATETIME,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            )
        ''')

        # ── MSI Phase 2: DNC Table ──────────────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dnc (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                phone TEXT,
                reason TEXT,
                source TEXT DEFAULT 'auto',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── MSI Phase 2: Activity Log (touchpoint tracking for Iris) ──
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                signal TEXT,
                context TEXT,
                old_score INTEGER,
                new_score INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lead_id) REFERENCES leads(id)
            )
        ''')

        # ── MSI Phase 3: Email Rate Tracking ──────────────────────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_rate_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sent_date DATE DEFAULT (date('now')),
                email_to TEXT,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── MSI Phase 3: System Config (warmup week tracking) ─────────
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ── Migrations: Add MSI columns to leads ─────────────────────
        for col, col_type, default in [
            ("sequence_position", "INTEGER", "0"),
            ("last_contacted_at", "DATETIME", "NULL"),
        ]:
            try:
                cursor.execute(f"SELECT {col} FROM leads LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    cursor.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_type} DEFAULT {default}")
                    logger.info(f"[DB] Migrated: added '{col}' column to leads table")
                except Exception as e:
                    logger.warning(f"[DB] Failed adding {col} to leads: {e}")

        # [SEED DATA]
        cursor.execute("SELECT COUNT(*) FROM tasks")
        if cursor.fetchone()[0] == 0:
            sample_tasks = [
                ('t1', 'Source 10 qualified HVAC leads', 'Target operators in Dallas metro running $500k+ annual revenue', 'HAWK', 'high', 'in-progress', '2026-03-28'),
                ('t2', 'Configure 17-Day Revenue Sequence', 'Set up automated outreach cadence for new pipeline', 'Nova', 'high', 'backlog', '2026-03-30')
            ]
            cursor.executemany("INSERT INTO tasks (id, title, description, assignee, priority, status, due) VALUES (?,?,?,?,?,?,?)", sample_tasks)

        # Migration: safely add client_id to tables if missing (AFTER all tables are created)
        for table in ["leads", "metrics", "tasks", "content"]:
            try:
                cursor.execute(f"SELECT client_id FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN client_id INTEGER DEFAULT 0")
                    logger.info(f"[DB] Migrated: added 'client_id' column to {table}")
                except Exception as e:
                    logger.warning(f"[DB] Failed adding client_id to {table}: {e}")

        conn.commit()
        conn.close()
        
        # Register cleanup hook
        atexit.register(DatabaseManager._close_all_connections)

    @staticmethod
    def query(sql, params=(), fetchone=False, fetchall=False):
        """Query using connection pool with proper release/cleanup."""
        conn = None
        try:
            conn = DatabaseManager._get_conn()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            res = None
            if fetchone: res = cursor.fetchone()
            elif fetchall: res = cursor.fetchall()
            conn.commit()
            return res
        except sqlite3.Error as e:
            logger.error(f"[DB] Query error: {e} | SQL: {sql[:100]}")
            if conn:
                # Force close broken connection
                try:
                    conn.close()
                    with DatabaseManager._pool_lock:
                        DatabaseManager._active_connections -= 1
                except:
                    pass
            raise
        finally:
            if conn:
                DatabaseManager._release_conn(conn)

    @staticmethod
    def get_clients():
        rows = DatabaseManager.query("SELECT * FROM clients WHERE is_active=1", fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    def get_client_config(client_id=0):
        """Get the niche and location for a specific client."""
        if client_id == 0:
            return {"niche": os.getenv("VERTICAL_NAME", "Automotive"), "location": "California"}
        row = DatabaseManager.query("SELECT niche, target_location FROM clients WHERE id = ?", (int(client_id),), fetchone=True)
        if row:
            return {"niche": row["niche"], "location": row["target_location"]}
        return {"niche": "Automotive", "location": "California"}

    @staticmethod
    def add_client(business_name, niche, target_location):
        DatabaseManager.query(
            "INSERT INTO clients (business_name, niche, target_location) VALUES (?, ?, ?)",
            (business_name, niche, target_location)
        )

    @staticmethod
    def save_lead(lead_data, default_vertical="Automotive", client_id=0):
        """Save a lead to the SQLite lead pipeline with deduplication."""
        business = lead_data.get("business") or lead_data.get("company") or lead_data.get("title")
        url = lead_data.get("url") or ""

        # --- DEDUPLICATION ---
        # Check if a lead with the same URL or business name already exists
        if url:
            existing = DatabaseManager.query(
                "SELECT id FROM leads WHERE url = ? LIMIT 1", (url,), fetchone=True
            )
            if existing:
                logger.info(f"[DB] Duplicate lead skipped (URL match): {url}")
                return  # Skip duplicate
        if business:
            existing = DatabaseManager.query(
                "SELECT id FROM leads WHERE LOWER(business) = LOWER(?) LIMIT 1", (business,), fetchone=True
            )
            if existing:
                logger.info(f"[DB] Duplicate lead skipped (name match): {business}")
                return  # Skip duplicate

        sql = '''
            INSERT INTO leads (business, url, contact, phone, email, vertical, score, status, notes, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            business,
            url,
            lead_data.get("contact") or lead_data.get("owner"),
            lead_data.get("phone"),
            lead_data.get("email"),
            lead_data.get("vertical") or default_vertical,
            lead_data.get("score") or lead_data.get("lead_score", 0),
            lead_data.get("status", "New"),
            lead_data.get("why") or lead_data.get("notes") or lead_data.get("snippet", ""),
            int(client_id)
        )
        DatabaseManager.query(sql, params)

    @staticmethod
    def get_leads(client_id=0):
        """Retrieve all leads from the SQLite pipeline for a specific client."""
        rows = DatabaseManager.query("SELECT * FROM leads WHERE client_id = ? ORDER BY updated_at DESC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows]

    @staticmethod
    def get_metrics(client_id=0):
        """Retrieve the current metrics row for a specific client."""
        row = DatabaseManager.query("SELECT * FROM metrics WHERE client_id = ?", (int(client_id),), fetchone=True)
        if row: return dict(row)
        return {"leads_found": 0, "emails_sent": 0, "replies_received": 0, "meetings_booked": 0, "calls_made": 0, "proposals_sent": 0}

    @staticmethod
    def get_tasks(client_id=0):
        rows = DatabaseManager.query("SELECT * FROM tasks WHERE client_id = ?", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    def get_content(client_id=0):
        rows = DatabaseManager.query("SELECT * FROM content WHERE client_id = ?", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    def get_memories(client_id=0):
        rows = DatabaseManager.query("SELECT * FROM memories WHERE client_id = ?", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    def get_chat_history(client_id=0):
        rows = DatabaseManager.query("SELECT * FROM chat_history WHERE client_id = ? ORDER BY timestamp ASC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []
    @staticmethod
    def update_metrics(data, client_id=0):
        """Update only the provided metric fields (merge, not overwrite)."""
        if not data:
            return
        valid_keys = ["leads_found", "emails_sent", "replies_received", "meetings_booked", "calls_made", "proposals_sent"]
        keys = [k for k in data.keys() if k in valid_keys]
        if not keys:
            return
            
        DatabaseManager.query("INSERT OR IGNORE INTO metrics (client_id) VALUES (?)", (int(client_id),))
        
        set_clause = ", ".join([f"{k} = ?" for k in keys])
        vals = [data[k] for k in keys]
        vals.append(int(client_id))
        DatabaseManager.query(f"UPDATE metrics SET {set_clause} WHERE client_id = ?", tuple(vals))

    @staticmethod
    def log_email_sent(lead_id, subject):
        """Log an email send for cold-lead timing."""
        DatabaseManager.query(
            "INSERT INTO email_tracking (lead_id, subject) VALUES (?, ?)",
            (lead_id, subject)
        )

    @staticmethod
    def get_cold_leads(days_threshold=5, client_id=0):
        """Get leads that were emailed but haven't replied within X days."""
        rows = DatabaseManager.query('''
            SELECT l.* FROM leads l
            JOIN email_tracking et ON l.id = et.lead_id
            WHERE l.status IN ('Email Sent', 'Contacted')
            AND l.client_id = ?
            AND et.sent_at <= datetime('now', ? || ' days')
            AND l.id NOT IN (
                SELECT lead_id FROM email_tracking WHERE status = 'replied'
            )
            GROUP BY l.id
            ORDER BY et.sent_at ASC
        ''', (int(client_id), f"-{days_threshold}"), fetchall=True)
        return [dict(r) for r in rows] if rows else []
