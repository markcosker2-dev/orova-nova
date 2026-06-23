"""[A-01] Lead repository — lead CRUD, dedup, and cold-lead queries."""
import asyncio
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class _LeadRepo:
    """Mixin: lead-related database operations."""

    @classmethod
    def get_clients(cls) -> List[Dict[str, Any]]:
        with cls.connection() as conn:
            try:
                cursor = conn.execute("SELECT * FROM clients WHERE is_active = 1")
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Error fetching clients: {e}")
                return []

    @classmethod
    async def aget_clients(cls) -> List[Dict[str, Any]]:
        """Async wrapper for get_clients (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, cls.get_clients)

    @classmethod
    def get_cold_leads(cls, days_threshold: int, client_id: int = 0) -> List[Dict[str, Any]]:
        with cls.connection() as conn:
            try:
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

    @classmethod
    async def aget_cold_leads(cls, days_threshold: int, client_id: int = 0) -> List[Dict[str, Any]]:
        """Async wrapper for get_cold_leads (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cls.get_cold_leads(days_threshold, client_id))

    @classmethod
    def _is_duplicate_lead(cls, email: str, domain: str = "", client_id: int = 0) -> bool:
        """Check if a lead with the same email or domain already exists in the DB."""
        with cls.connection() as conn:
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

    @classmethod
    async def _ais_duplicate_lead(cls, email: str, domain: str = "", client_id: int = 0) -> bool:
        """Async wrapper for _is_duplicate_lead (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cls._is_duplicate_lead(email, domain, client_id))

    @classmethod
    def save_lead(cls, lead: dict, default_vertical: str = None, client_id: int = 0) -> int:
        """Save a lead with automatic deduplication. Returns lead_id or -1 if duplicate.
        Dedup: SELECT check inside transaction + UNIQUE index as hard backstop."""
        email = lead.get("email", "").strip()
        url = lead.get("url") or lead.get("website", "")
        domain = ""
        if url:
            try:
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
            except Exception:
                pass
        cid = lead.get("client_id") or client_id or 0
        # ── Single transaction: dedup check + insert ──
        with cls.connection() as conn:
            try:
                # Dedup check inside the transaction
                if email:
                    row = conn.execute(
                        "SELECT id FROM leads WHERE lower(email) = lower(?) AND client_id = ? LIMIT 1",
                        (email.strip(), cid)
                    ).fetchone()
                    if row:
                        logger.info(f"[DEDUP] Skipping duplicate lead: {email}")
                        return -1
                if domain:
                    row = conn.execute(
                        "SELECT id FROM leads WHERE lower(website) LIKE ? AND client_id = ? LIMIT 1",
                        (f"%{domain.lower()}%", cid)
                    ).fetchone()
                    if row:
                        logger.info(f"[DEDUP] Skipping duplicate lead: {domain}")
                        return -1
                # Insert — same transaction, no race window
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
            except Exception as e:
                # Hard dedup backstop: UNIQUE index on (lower(email), client_id)
                # catches any TOCTOU race that slipped past the SELECT check
                import sqlite3
                if isinstance(e, sqlite3.IntegrityError) and "idx_leads_email_client" in str(e):
                    logger.info(f"[DEDUP-UNIQUE] Race caught by UNIQUE index: {email}")
                    return -1
                logger.error(f"Error saving lead: {e}")
                return -1

    @classmethod
    async def asave_lead(cls, lead: dict, default_vertical: str = None, client_id: int = 0) -> int:
        """Async wrapper for save_lead (CQ-07)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cls.save_lead(lead, default_vertical, client_id))
