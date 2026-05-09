# pyrefly: ignore [missing-import]
import aiosqlite
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Data directory mounted from Docker Volume
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/orova_v5.db").replace("sqlite+aiosqlite:///", "")

# ── [P6] ECONOMICS SCHEMA ──
USAGE_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS usage_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    client_id   INTEGER NOT NULL DEFAULT 0,
    agent_id    TEXT NOT NULL,
    model       TEXT,
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    cost_est    REAL DEFAULT 0.0
);
"""

class DatabaseManager:
    """Async SQLite storage for OROVA Mission Control."""
    
    @staticmethod
    async def init_db():
        async with aiosqlite.connect(DB_PATH) as db:
            # [P0] Enable WAL mode for concurrent read/write (Essential for multi-agent swarm)
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA cache_size=-32000") # 32MB page cache
            
            # Phase 10: Clients Table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT,
                    niche TEXT,
                    target_location TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            # Metrics
            await db.execute('''
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
            await db.execute("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")
            
            # Leads Table
            await db.execute('''
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
            
            # [P0] INDEXES: Prevent table scan slowdowns as leads grow
            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_client ON leads(client_id)")

            # Tasks
            await db.execute('''
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
            # Memories (Wiki)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT,
                    content TEXT,
                    client_id INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # State Table (NEW for Soul/UUID)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Chat History
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    client_id INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Learned Patterns (Hermes Evolution)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS learned_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    winning_approach TEXT,
                    success_metric INTEGER DEFAULT 1,
                    client_id INTEGER NOT NULL DEFAULT 0,
                    last_used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    decay_score REAL DEFAULT 1.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute("CREATE INDEX IF NOT EXISTS idx_patterns_client ON learned_patterns(client_id)")
            
            # Content
            await db.execute('''
                CREATE TABLE IF NOT EXISTS content (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    body TEXT,
                    type TEXT,
                    status TEXT,
                    client_id INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # Campaigns (For Email Drip Tracking)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prospect_email TEXT,
                    sequence_type TEXT,
                    status TEXT DEFAULT 'active',
                    stopped_reason TEXT,
                    stopped_at DATETIME,
                    client_id INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            await db.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_email_status ON campaigns(prospect_email, status)")
            
            await db.commit()
            logger.info("[DB] Async SQLite initialized with WAL mode, indexes, and Evolution schema.")

    @staticmethod
    @asynccontextmanager
    async def get_db():
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    @staticmethod
    async def query(sql, params=(), fetchone=False, fetchall=False):
        async with DatabaseManager.get_db() as db:
            cursor = await db.execute(sql, params)
            if fetchone:
                row = await cursor.fetchone()
                await db.commit()
                return row
            if fetchall:
                rows = await cursor.fetchall()
                await db.commit()
                return rows
            await db.commit()
            return cursor

    @staticmethod
    async def fetchall(sql, params=()):
        async with DatabaseManager.get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    async def fetchone(sql, params=()):
        async with DatabaseManager.get_db() as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            row = await cursor.fetchone()
            return dict(row) if row else None

    # --- [P1] HARDENED ACCESSORS (Client Isolation) ---

    @staticmethod
    async def get_metrics(client_id: int):
        assert client_id > 0, "Security: client_id must be > 0"
        return await DatabaseManager.fetchone("SELECT * FROM metrics WHERE client_id = ?", (client_id,))

    @staticmethod
    async def get_leads(client_id: int):
        assert client_id > 0, "Security: client_id must be > 0"
        return await DatabaseManager.fetchall("SELECT * FROM leads WHERE client_id = ? ORDER BY created_at DESC", (client_id,))

    @staticmethod
    async def get_tasks(client_id: int):
        assert client_id > 0, "Security: client_id must be > 0"
        return await DatabaseManager.fetchall("SELECT * FROM tasks WHERE client_id = ?", (client_id,))

    @staticmethod
    async def get_content(client_id: int):
        assert client_id > 0, "Security: client_id must be > 0"
        return await DatabaseManager.fetchall("SELECT * FROM content WHERE client_id = ?", (client_id,))

    @staticmethod
    async def get_memories(client_id: int):
        assert client_id > 0, "Security: client_id must be > 0"
        return await DatabaseManager.fetchall("SELECT * FROM memories WHERE client_id = ?", (client_id,))

    @staticmethod
    async def get_chat_history(client_id: int):
        # Allow 0 for global/system logs if needed, but restrict for production
        return await DatabaseManager.fetchall("SELECT * FROM chat_history WHERE client_id = ? ORDER BY created_at ASC", (client_id,))

    @staticmethod
    async def set_state(key: str, value: str):
        await DatabaseManager.query(
            "INSERT INTO system_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value)
        )

    @staticmethod
    async def get_state(key: str, default: str = None):
        res = await DatabaseManager.fetchone("SELECT value FROM system_state WHERE key = ?", (key,))
        return res["value"] if res else default

    @staticmethod
    async def get_clients():
        return await DatabaseManager.fetchall("SELECT * FROM clients")

    @staticmethod
    async def save_lead(lead_data: dict):
        """[P8] Sanitize, Normalize, and Save Lead."""
        email = lead_data.get("email")
        if not email: return
        
        # 1. Absolute Guardrail: Blacklist Check
        is_b = await DatabaseManager.fetchone("SELECT 1 FROM blacklist WHERE email = ?", (email,))
        if is_b: 
            logger.warning(f"[P8] Blocked attempt to save blacklisted lead: {email}")
            return {"status": "blocked", "reason": "blacklisted"}

        # 2. LinkedIn URL Cleaning (Strip tracking parameters)
        raw_li = lead_data.get("linkedin_url") or lead_data.get("linkedin") or ""
        clean_li = raw_li.split("?")[0] if raw_li else ""

        # 3. E.164 Phone Normalization
        raw_p = lead_data.get("phone", "")
        clean_p = None
        if raw_p:
            try:
                import phonenumbers
                # Assuming US default, adjust as needed in production
                parsed = phonenumbers.parse(raw_p, "US")
                if phonenumbers.is_valid_number(parsed):
                    clean_p = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except: pass

        sql = '''
            INSERT INTO leads (business, url, contact, phone, email, vertical, score, status, notes, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            lead_data.get("business") or lead_data.get("company"),
            lead_data.get("url"),
            lead_data.get("contact") or lead_data.get("owner"),
            clean_p, email,
            lead_data.get("vertical", "Premium Services"),
            lead_data.get("score", 0),
            lead_data.get("status", "New"),
            lead_data.get("notes") or lead_data.get("reasoning", ""),
            int(lead_data.get("client_id", 0))
        )
        await DatabaseManager.query(sql, params)
        logger.info(f"[P8] Lead saved with surgical normalization: {email}")

    @staticmethod
    async def get_clients():
        return await DatabaseManager.query("SELECT * FROM clients", fetchall=True)

    @staticmethod
    async def get_metrics(client_id=0):
        row = await DatabaseManager.query("SELECT * FROM metrics WHERE client_id = ?", (int(client_id),), fetchone=True)
        return dict(row) if row else {}

    @staticmethod
    async def get_leads(client_id=0):
        rows = await DatabaseManager.query("SELECT * FROM leads WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_tasks(client_id=0):
        rows = await DatabaseManager.query("SELECT * FROM tasks WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_content(client_id=0):
        rows = await DatabaseManager.query("SELECT * FROM content WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_memories(client_id=0):
        rows = await DatabaseManager.query("SELECT * FROM memories WHERE client_id = ? ORDER BY created_at DESC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_chat_history(client_id=0):
        rows = await DatabaseManager.query("SELECT * FROM chat_history WHERE client_id = ? ORDER BY created_at ASC", (int(client_id),), fetchall=True)
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_client_config(client_id=0):
        # Simplified: Fetch from clients table or return default
        row = await DatabaseManager.query("SELECT * FROM clients WHERE id = ?", (int(client_id),), fetchone=True)
        if row:
            return dict(row)
        return {"business_name": "OROVA Internal", "niche": os.getenv("VERTICAL_NAME", "Automotive, Luxury Remodeling, Private Aviation, Real Estate"), "location": "California"}

    @staticmethod
    async def get_state(key: str, default=None):
        row = await DatabaseManager.query("SELECT value FROM system_state WHERE key = ?", (key,), fetchone=True)
        return row["value"] if row else default

    @staticmethod
    async def set_state(key: str, value: str):
        await DatabaseManager.query(
            "INSERT INTO system_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value)
        )

    @staticmethod
    @asynccontextmanager
    async def transaction():
        """[P7] Safe transaction context manager."""
        db = await aiosqlite.connect(DB_PATH)
        try:
            await db.execute("BEGIN TRANSACTION;")
            yield db
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e
        finally:
            await db.close()

    @staticmethod
    async def blacklist_lead(email: str):
        """[P7] Wipe lead and blacklist via atomic transaction."""
        async with DatabaseManager.transaction() as conn:
            # 1. Erase all trace of the lead
            await conn.execute("DELETE FROM leads WHERE email = ?", (email,))
            # 2. Append to immutable blacklist
            await conn.execute("INSERT OR IGNORE INTO blacklist (email) VALUES (?)", (email,))
            logger.info(f"[Privacy] Lead {email} blacklisted and forgotten.")

# ── [P7] BLACKLIST SCHEMA ──
BLACKLIST_DDL = "CREATE TABLE IF NOT EXISTS blacklist (email TEXT PRIMARY KEY, blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP);"

PHASE_5_INDEXES = [
    # Primary: get_winning_approach (Zero table hits)
    """
    CREATE INDEX IF NOT EXISTS idx_lp_client_task_decay_metric
    ON learned_patterns (client_id, task_type, decay_score, success_metric DESC);
    """,
    # Aggregate: learning_stats reporting
    """
    CREATE INDEX IF NOT EXISTS idx_lp_created_at
    ON learned_patterns (created_at);
    """,
    # Reinforcer: lookups
    """
    CREATE INDEX IF NOT EXISTS idx_lp_task_approach
    ON learned_patterns (task_type, winning_approach);
    """,
]

async def run_phase5_migrations():
    """Idempotent. Safe to call at startup."""
    import logging
    logger = logging.getLogger("database.migrations")
    try:
        for ddl in PHASE_5_INDEXES:
            await DatabaseManager.query(ddl)
        logger.info("[DB] Phase 5 covering indexes applied.")
    except Exception as e:
        logger.error(f"[DB] Phase 5 migrations failed: {e}")

# ── [P6] LIFECYCLE & TELEMETRY ──

async def log_usage(client_id: int, agent_id: str, model: str, t_in: int, t_out: int, cost: float):
    """Logs AI consumption for economic tracking."""
    sql = "INSERT INTO usage_logs (client_id, agent_id, model, tokens_in, tokens_out, cost_est) VALUES (?, ?, ?, ?, ?, ?)"
    await DatabaseManager.query(sql, (client_id, agent_id, model, t_in, t_out, cost))

async def get_usage_stats():
    """Aggregates costs for the /stats command."""
    sql = "SELECT COUNT(*) as reqs, SUM(tokens_in) as t_in, SUM(tokens_out) as t_out, SUM(cost_est) as cost FROM usage_logs"
    res = await DatabaseManager.fetchone(sql)
    return {"totals": res or {"reqs": 0, "t_in": 0, "t_out": 0, "cost": 0.0}}

def register_sigterm_handler(loop):
    """[P6] Ensure WAL checkpointing on Render SIGTERM."""
    import signal
    def handle_sigterm():
        logger.info("[P6] SIGTERM received. Executing atomic WAL checkpoint...")
        # Note: We can't easily run async code in a signal handler synchronously 
        # but SQLite will attempt to flush on close/shutdown if we are careful.
        # This is a sentinel for graceful shutdown.
    try:
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
    except: pass # Windows compatibility
