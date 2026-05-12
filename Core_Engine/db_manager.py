# Core_Engine/db_manager.py
# Handles local lead tracking (Qualified vs Dead) for "Architect" phase.

import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import List

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Manager")

# Path relative to project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "Client_Data", "leads.db")

def init_db():
    """Initialize the SQLite database and tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Leads Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            website TEXT,
            vertical TEXT,
            status TEXT DEFAULT 'New',  -- New, Qualified, Contacted, Called, Emailed, Follow-up 1, Follow-up 2, Booked, Dead
            clv_score INTEGER DEFAULT 0,
            call_id TEXT,  -- Retell call ID (added per audit fix)
            notes TEXT,
            metadata TEXT,  -- JSON string for extra fields
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Activity Log Table (for audit trail per audit fixes)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            action TEXT NOT NULL,  -- 'call', 'email', 'call_skipped', etc.
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lead_id) REFERENCES leads (id)
        )
    ''')

    # Send Log Table (for email inbox rotation per audit fixes)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT NOT NULL,  -- email__domain_label format
            action TEXT NOT NULL,  -- 'email', 'follow_up_1', etc.
            sent_date DATE DEFAULT CURRENT_DATE,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Database initialized at {DB_PATH}")

def add_lead(lead_data: dict):
    """
    Add a new lead to the database.
    Required keys: business_name, vertical
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO leads (business_name, phone, email, website, vertical, status, clv_score, call_id, notes, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            lead_data.get("business_name"),
            lead_data.get("phone"),
            lead_data.get("email"),
            lead_data.get("website"),
            lead_data.get("vertical", "Unknown"),
            lead_data.get("status", "New"),
            lead_data.get("clv_score", 0),
            lead_data.get("call_id", ""),
            lead_data.get("notes", ""),
            json.dumps(lead_data.get("metadata", {}))
        ))
        conn.commit()
        lead_id = cursor.lastrowid
        logger.info(f"✅ Added Lead: {lead_data.get('business_name')} (ID: {lead_id})")
        return lead_id
    except Exception as e:
        logger.error(f"❌ Failed to add lead: {e}")
        return None
    finally:
        conn.close()

def update_lead_status(lead_id: int, new_status: str, notes: str = None):
    """Update status and optionally append notes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        if notes:
            cursor.execute('''
                UPDATE leads 
                SET status = ?, notes = notes || ? || '\n', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, f" [{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}", lead_id))
        else:
            cursor.execute('''
                UPDATE leads 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_status, lead_id))
            
        conn.commit()
        logger.info(f"Updated Lead {lead_id} -> {new_status}")
    except Exception as e:
        logger.error(f"❌ Failed to update lead {lead_id}: {e}")
    finally:
        conn.close()

def get_leads_by_status(status: str, vertical: str = None):
    """Retrieve leads by status, optionally filtered by vertical."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM leads WHERE status = ?"
    params = [status]
    
    if vertical:
        query += " AND vertical = ?"
        params.append(vertical)
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_lead(lead_id: int) -> dict:
    """Get a single lead by ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None

def get_all_leads(client_id: int = 0) -> List[dict]:
    """Get all leads (client_id parameter for future multi-client support)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]

def update_lead_call_id(lead_id: int, call_id: str):
    """Update lead's call ID (for Retell integration per audit fix)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE leads
            SET call_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (call_id, lead_id))
        conn.commit()
        logger.info(f"Updated Lead {lead_id} call_id to {call_id}")
    except Exception as e:
        logger.error(f"❌ Failed to update call_id for lead {lead_id}: {e}")
    finally:
        conn.close()

def log_activity(lead_id: int, action: str, details: str = ""):
    """Log activity for a lead (per audit fixes)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO activity_log (lead_id, action, details)
            VALUES (?, ?, ?)
        ''', (lead_id, action, details))
        conn.commit()
        logger.debug(f"Logged activity: {action} for lead {lead_id}")
    except Exception as e:
        logger.error(f"❌ Failed to log activity for lead {lead_id}: {e}")
    finally:
        conn.close()

def record_send(recipient: str, action: str = "email"):
    """Record an email send (per inbox rotation audit fix)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO send_log (recipient, action)
            VALUES (?, ?)
        ''', (recipient, action))
        conn.commit()
        logger.debug(f"Recorded send: {action} to {recipient}")
    except Exception as e:
        logger.error(f"❌ Failed to record send: {e}")
    finally:
        conn.close()

def is_dnc(email: str) -> bool:
    """Check if email is on Do Not Contact list (placeholder per audit fixes)."""
    # TODO: Implement DNC list check
    # For now, return False (allow all)
    return False

if __name__ == "__main__":
    init_db()
    # Test
    # add_lead({"business_name": "Test Corp", "vertical": "Automotive", "phone": "+15550000"})
