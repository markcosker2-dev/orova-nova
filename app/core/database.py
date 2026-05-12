"""
Fixed:
  - Removed duplicate get_state / set_state / get_clients method definitions
    (Python uses last definition; the ambiguity caused unpredictable behaviour)
  - Added blacklist table to init_db (save_lead queries it but table was never created)
  - Added get_cold_leads() used by worker.py
"""
# pyrefly: ignore [missing-import]
import aiosqlite
import os
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "app", "data",
)
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = (
    os.environ.get("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/orova_v5.db")
    .replace("sqlite+aiosqlite:///", "")
)

USAGE_LOGS_DDL = \"\"\"
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
\"\"\"

MODEL_COSTS = {
    "google/gemini-2.0-flash-lite-preview-02-05:free": (0.0, 0.0),
    "openai/gpt-4o": (5.0, 15.0),
    "openai/gpt-4o-mini": (0.15, 0.60),
    "anthropic/claude-3-5-sonnet": (3.0, 15.0),
    "__default__": (1.0, 3.0),
}


def estimate_cost(model: str, t_in: int, t_out: int) -> float:
    rates = MODEL_COSTS.get(model, MODEL_COSTS["__default__"])
    return round((t_in / 1e6) * rates[0] + (t_out / 1e6) * rates[1], 8)


class DatabaseManager:
    \"\"\"Async SQLite storage for OROVA Mission Control.\"\"\"

    @staticmethod
    async def init_db():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA cache_size=-32000")

            await db.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT,
                    niche TEXT,
                    target_location TEXT,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    client_id INTEGER PRIMARY KEY DEFAULT 0,
                    leads_found INTEGER DEFAULT 0,
                    emails_sent INTEGER DEFAULT 0,
                    replies_received INTEGER DEFAULT 0,
                    meetings_booked INTEGER DEFAULT 0,
                    calls_made INTEGER DEFAULT 0,
                    proposals_sent INTEGER DEFAULT 0,
                    deals_closed INTEGER DEFAULT 0,
                    content_created INTEGER DEFAULT 0,
                    ad_spend REAL DEFAULT 0.0,
                    monthly_recurring_revenue REAL DEFAULT 0.0,
                    errors INTEGER DEFAULT 0
                )
            ''')
            await db.execute("INSERT OR IGNORE INTO metrics (client_id) VALUES (0)")

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

            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_leads_client ON leads(client_id)")

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

            await db.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    client_id INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

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
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_campaigns_email_status ON campaigns(prospect_email, status)"
            )

            # ── BLACKLIST (was defined as a string constant but never created) ──
            await db.execute('''
                CREATE TABLE IF NOT EXISTS blacklist (
                    email TEXT PRIMARY KEY,
                    blacklisted_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute(USAGE_LOGS_DDL)

            await db.commit()
            logger.info("[DB] SQLite initialised (WAL, indexes, blacklist table).")

    # ── Connection helpers ────────────────────────────────────────────────

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

    # ── State ─────────────────────────────────────────────────────────────

    @staticmethod
    async def set_state(key: str, value: str):
        await DatabaseManager.query(
            "INSERT INTO system_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value),
        )

    @staticmethod
    async def get_state(key: str, default=None):
        res = await DatabaseManager.fetchone(
            "SELECT value FROM system_state WHERE key = ?", (key,)
        )
        return res["value"] if res else default

    # ── Clients ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_clients():
        return await DatabaseManager.fetchall("SELECT * FROM clients")

    # ── Leads ─────────────────────────────────────────────────────────────

    @staticmethod
    async def save_lead(lead_data: dict):
        \"\"\"Sanitise, normalise and persist a lead. Silently skips blacklisted emails.\"\"\"
        email = lead_data.get("email")

        # Blacklist guard
        if email:
            is_bl = await DatabaseManager.fetchone(
                "SELECT 1 FROM blacklist WHERE email = ?", (email,)
            )
            if is_bl:
                logger.warning(f"[DB] Blocked blacklisted lead: {email}")
                return {"status": "blocked", "reason": "blacklisted"}

        # E.164 phone normalisation (best-effort)
        raw_p = lead_data.get("phone", "")
        clean_p = None
        if raw_p:
            try:
                import phonenumbers
                parsed = phonenumbers.parse(raw_p, "US")
                if phonenumbers.is_valid_number(parsed):
                    clean_p = phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164
                    )
            except Exception:
                clean_p = raw_p  # keep as-is if phonenumbers not available

        await DatabaseManager.query(
            '''INSERT INTO leads
               (business, url, contact, phone, email, vertical, score, status, notes, client_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                lead_data.get("business") or lead_data.get("company") or lead_data.get("title"),
                lead_data.get("url"),
                lead_data.get("contact") or lead_data.get("owner"),
                clean_p,
                email,
                lead_data.get("vertical", "Premium Services"),
                lead_data.get("score", 0),
                lead_data.get("status", "New"),
                lead_data.get("notes") or lead_data.get("reasoning", ""),
                int(lead_data.get("client_id", 0)),
            ),
        )
        logger.info(f"[DB] Lead saved: {email or lead_data.get('business')}")

    @staticmethod
    async def get_leads(client_id=0):
        rows = await DatabaseManager.query(
            "SELECT * FROM leads WHERE client_id = ? ORDER BY created_at DESC",
            (int(client_id),),
            fetchall=True,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_cold_leads(days_threshold: int = 5, client_id: int = 0) -> list:
        \"\"\"Leads that were emailed/contacted but haven't been updated in X days.\"\"\"
        return await DatabaseManager.fetchall(
            \"\"\"SELECT * FROM leads
               WHERE client_id = ?
               AND status IN ('Email Sent', 'Contacted', 'Called', 'Emailed')
               AND updated_at < datetime('now', '-' || ? || ' days')\"\"\",
            (int(client_id), days_threshold),
        )

    @staticmethod
    async def blacklist_lead(email: str):
        \"\"\"Atomically wipe a lead and add its email to the blacklist.\"\"\"
        async with DatabaseManager.transaction() as conn:
            await conn.execute("DELETE FROM leads WHERE email = ?", (email,))
            await conn.execute(
                "INSERT OR IGNORE INTO blacklist (email) VALUES (?)", (email,)
            )
            logger.info(f"[Privacy] Lead {email} blacklisted and forgotten.")

    # ── Metrics ───────────────────────────────────────────────────────────

    @staticmethod
    async def get_metrics(client_id=0):
        row = await DatabaseManager.query(
            "SELECT * FROM metrics WHERE client_id = ?",
            (int(client_id),),
            fetchone=True,
        )
        return dict(row) if row else {}

    @staticmethod
    async def update_metrics(updates: dict, client_id: int = 0):
        if not updates:
            return
        columns = list(updates.keys())
        placeholders = ", ".join(["?"] * len(columns))
        set_clause = ", ".join(col + "=excluded." + col for col in columns)
        sql = (
            "INSERT INTO metrics (client_id, "
            + ", ".join(columns)
            + ") VALUES (?, "
            + placeholders
            + ") ON CONFLICT(client_id) DO UPDATE SET "
            + set_clause
        )
        params = [client_id] + [updates[col] for col in columns]
        await DatabaseManager.query(sql, params)

    # ── Tasks / Content / Memories / Chat ────────────────────────────────

    @staticmethod
    async def get_tasks(client_id=0):
        rows = await DatabaseManager.query(
            "SELECT * FROM tasks WHERE client_id = ? ORDER BY created_at DESC",
            (int(client_id),),
            fetchall=True,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_content(client_id=0):
        rows = await DatabaseManager.query(
            "SELECT * FROM content WHERE client_id = ? ORDER BY created_at DESC",
            (int(client_id),),
            fetchall=True,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_memories(client_id=0):
        rows = await DatabaseManager.query(
            "SELECT * FROM memories WHERE client_id = ? ORDER BY created_at DESC",
            (int(client_id),),
            fetchall=True,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_chat_history(client_id=0):
        rows = await DatabaseManager.query(
            "SELECT * FROM chat_history WHERE client_id = ? ORDER BY created_at ASC",
            (int(client_id),),
            fetchall=True,
        )
        return [dict(r) for r in rows] if rows else []

    @staticmethod
    async def get_client_config(client_id=0):
        row = await DatabaseManager.query(
            "SELECT * FROM clients WHERE id = ?", (int(client_id),), fetchone=True
        )
        if row:
            return dict(row)
        return {
            "business_name": "OROVA Internal",
            "niche": os.getenv("VERTICAL_NAME", "Automotive, Luxury Remodeling, Real Estate"),
            "target_location": "California",
        }

    # ── Transactions ──────────────────────────────────────────────────────

    @staticmethod
    @asynccontextmanager
    async def transaction():
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


# ── Phase 5 migrations (covering indexes for learned_patterns) ───────────

PHASE_5_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_lp_client_task_decay_metric "
    "ON learned_patterns (client_id, task_type, decay_score, success_metric DESC);",
    "CREATE INDEX IF NOT EXISTS idx_lp_created_at ON learned_patterns (created_at);",
    "CREATE INDEX IF NOT EXISTS idx_lp_task_approach ON learned_patterns (task_type, winning_approach);",
]


async def run_phase5_migrations():
    try:
        for ddl in PHASE_5_INDEXES:
            await DatabaseManager.query(ddl)
        logger.info("[DB] Phase 5 covering indexes applied.")
    except Exception as e:
        logger.error(f"[DB] Phase 5 migrations failed: {e}")


# ── Telemetry helpers ─────────────────────────────────────────────────────

async def log_usage(
    client_id: int, agent_id: str, model: str, t_in: int, t_out: int, cost: float
):
    await DatabaseManager.query(
        "INSERT INTO usage_logs (client_id, agent_id, model, tokens_in, tokens_out, cost_est) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (client_id, agent_id, model, t_in, t_out, cost),
    )


async def get_usage_stats():
    res = await DatabaseManager.fetchone(
        "SELECT COUNT(*) as reqs, SUM(tokens_in) as t_in, "
        "SUM(tokens_out) as t_out, SUM(cost_est) as cost FROM usage_logs"
    )
    return {"totals": res or {"reqs": 0, "t_in": 0, "t_out": 0, "cost": 0.0}}


def register_sigterm_handler(loop):
    import signal
    def handle_sigterm():
        logger.info("[DB] SIGTERM received — flushing WAL.")
    try:
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
    except Exception:
        pass  # Windows compatibility
