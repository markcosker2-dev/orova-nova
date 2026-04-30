import aiosqlite
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Data directory mounted from Docker Volume
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/orova_v5.db").replace("sqlite+aiosqlite:///", "")

class DatabaseManager:
    """Async SQLite storage for OROVA Mission Control."""
    
    @staticmethod
    async def init_db():
        async with aiosqlite.connect(DB_PATH) as db:
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
            await db.commit()
            logger.info("[DB] Async SQLite initialized successfully.")

    @staticmethod
    @asynccontextmanager
    async def get_connection():
        db = await aiosqlite.connect(DB_PATH)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    @staticmethod
    async def query(sql, params=(), fetchone=False, fetchall=False):
        async with DatabaseManager.get_connection() as db:
            async with db.execute(sql, params) as cursor:
                res = None
                if fetchone: res = await cursor.fetchone()
                elif fetchall: res = await cursor.fetchall()
                await db.commit()
                return res

    @staticmethod
    async def save_lead(lead_data, default_vertical="Automotive", client_id=0):
        business = lead_data.get("business") or lead_data.get("company") or lead_data.get("title")
        url = lead_data.get("url") or ""

        if url:
            existing = await DatabaseManager.query("SELECT id FROM leads WHERE url = ? LIMIT 1", (url,), fetchone=True)
            if existing: return
        if business:
            existing = await DatabaseManager.query("SELECT id FROM leads WHERE LOWER(business) = LOWER(?) LIMIT 1", (business,), fetchone=True)
            if existing: return

        sql = '''
            INSERT INTO leads (business, url, contact, phone, email, vertical, score, status, notes, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            business, url,
            lead_data.get("contact") or lead_data.get("owner"),
            lead_data.get("phone"), lead_data.get("email"),
            lead_data.get("vertical") or default_vertical,
            lead_data.get("score") or lead_data.get("lead_score", 0),
            lead_data.get("status", "New"),
            lead_data.get("why") or lead_data.get("notes") or lead_data.get("snippet", ""),
            int(client_id)
        )
        await DatabaseManager.query(sql, params)

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
