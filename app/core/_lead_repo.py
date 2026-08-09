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
    def get_uncontacted_callable_leads(cls, limit: int = 25, client_id: int = 0) -> List[Dict[str, Any]]:
        """Leads with a phone that have NEVER been contacted on any channel.

        The counterpart to get_cold_leads. That one requires
        status IN ('Email Sent','Contacted'), i.e. it only ever sees leads that
        were ALREADY emailed — which makes the escalation lane structurally
        downstream of email. With cold email deliberately deferred (ADR-0014,
        2026-07-30) nothing could ever enter that set, so licence-sourced leads
        (status 'New', phone at 100% fill) were undialable by any scheduled lane.

        Highest ICP score first, so the best leads get the day's call budget.
        Callability itself is NOT decided here — outreach_ready() in
        lead_validator owns that (single source of truth); this only narrows the
        rows worth evaluating.
        """
        with cls.connection() as conn:
            try:
                cursor = conn.execute(
                    """SELECT * FROM leads
                       WHERE client_id = ?
                       AND COALESCE(status,'') = 'New'
                       AND COALESCE(phone,'') != ''
                       ORDER BY COALESCE(score, 0) DESC, id ASC
                       LIMIT ?""",
                    (client_id, int(limit))
                )
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Error fetching uncontacted callable leads: {e}")
                return []

    @classmethod
    async def aget_uncontacted_callable_leads(cls, limit: int = 25, client_id: int = 0) -> List[Dict[str, Any]]:
        """Async wrapper for get_uncontacted_callable_leads."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: cls.get_uncontacted_callable_leads(limit, client_id))

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
        """Save a lead with automatic deduplication and the storage gate.
        Returns lead_id, -1 if duplicate, or -2 if the gate rejected the row.
        Dedup: SELECT check inside transaction + UNIQUE index as hard backstop.

        Storage gate (Phase 0): every ingest path (hunt, CSV import, Sheets
        restore) converges here, so this is where fabricated/placeholder data
        is stopped. Unverifiable fields are stored EMPTY; the score is always
        recomputed server-side (a Sheets fixture once arrived pre-scored 85)."""
        from app.skills.lead_validator import validate_lead_for_storage
        gate = validate_lead_for_storage(lead)
        if not gate["ok"]:
            logger.warning(f"[LEAD-GATE] REJECTED lead: {'; '.join(gate['reasons'])}")
            return -2
        if gate["reasons"]:
            logger.info(f"[LEAD-GATE] cleaned lead '{gate['lead'].get('business')}': "
                        f"{'; '.join(gate['reasons'])}")
        lead = gate["lead"]
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
                        conn.rollback()   # release the read txn before pooling
                        return -1
                if domain:
                    row = conn.execute(
                        "SELECT id FROM leads WHERE lower(website) LIKE ? AND client_id = ? LIMIT 1",
                        (f"%{domain.lower()}%", cid)
                    ).fetchone()
                    if row:
                        logger.info(f"[DEDUP] Skipping duplicate lead: {domain}")
                        conn.rollback()   # release the read txn before pooling
                        return -1
                # ── Last-resort identity: business name + state ────────────
                # Only when BOTH stronger keys are absent. Licence-registry
                # rows (WA L&I / OR CCB / CA CSLB — the primary source since
                # ADR-0014) carry no email, no url and no website, so until
                # 2026-08-09 they had NO dedup key whatsoever and every hunt
                # re-inserted the same contractors. Live evidence that day:
                # 24 lead rows holding 13 distinct businesses, with
                # FOREVER QUALITY CONSTRUCT LLC stored four times.
                #
                # That inflation is also what made durability look broken for
                # weeks. The Leads sheet upserts by business name, so it held
                # the 13 while the table showed 24, and every comparison of
                # the two read as catastrophic backup loss. Fixing the count
                # at the source is the real repair; the verifier in
                # durability.py only stopped mis-reporting the symptom.
                #
                # Gated on both keys being empty on purpose: two genuinely
                # different firms can share a name, and when either has a
                # domain or an email the checks above already separated them
                # correctly. Merging on name alone there would destroy real
                # leads, which is a far worse failure than storing a duplicate.
                business_key = (lead.get("business") or "").strip().lower()
                state_key = str(lead.get("state") or "").strip().upper()
                if business_key and not email and not domain:
                    row = conn.execute(
                        "SELECT id FROM leads WHERE lower(trim(business)) = ? "
                        "AND upper(trim(COALESCE(state,''))) = ? AND client_id = ? "
                        "AND COALESCE(email,'') = '' AND COALESCE(website,'') = '' LIMIT 1",
                        (business_key, state_key, cid)
                    ).fetchone()
                    if row:
                        logger.info(f"[DEDUP] Skipping duplicate lead: "
                                    f"{business_key!r} ({state_key or 'no state'})")
                        conn.rollback()   # release the read txn before pooling
                        return -1
                # Insert — same transaction, no race window
                vertical = lead.get("vertical") or default_vertical or ""
                cursor = conn.execute(
                    """INSERT INTO leads (business, owner, url, website, email, phone, vertical, status, notes, icebreaker, score, client_id, email_status, owner_title, linkedin_url, owner_source, email_source, phone_source, phone_verified, owner_confidence, evidence_json, ad_signals, state, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, CURRENT_TIMESTAMP)""",
                    (lead.get("business",""), lead.get("owner",""), lead.get("url",""),
                     lead.get("website",""), email, lead.get("phone",""),
                     vertical, lead.get("status","New"), lead.get("notes",""),
                     lead.get("icebreaker",""), lead.get("score",0), cid,
                     lead.get("email_status",""), lead.get("owner_title",""),
                     lead.get("linkedin_url",""), lead.get("owner_source",""),
                     lead.get("email_source",""), lead.get("phone_source",""),
                     1 if lead.get("phone_verified") else 0,
                     int(lead.get("owner_confidence") or 0), lead.get("evidence_json",""),
                     lead.get("ad_signals",""),
                     # Stored upper-cased: owner_finder._registry_lookup routes on
                     # an exact "CA"/"WA"/"OR" match, and ungated ingest (CSV,
                     # Sheets) supplies "ca" / " CA " freely. Normalizing on write
                     # keeps the stored fact canonical instead of relying on every
                     # reader to re-normalize.
                     str(lead.get("state") or "").strip().upper())
                )
                lead_id = cursor.lastrowid
                conn.commit()
                return lead_id
            except Exception as e:
                # ROLLBACK FIRST (2026-08-02). This handler used to `return -1`
                # with the failed INSERT's transaction still open, so the
                # connection went back to the pool holding SQLite's write lock.
                # Every subsequent save then blocked for busy_timeout and died
                # `database is locked` — which re-entered this same handler and
                # poisoned another connection. Five leads found, one saved.
                try:
                    conn.rollback()
                except Exception as rb_err:
                    logger.error(f"Rollback after failed lead save also failed: {rb_err}")
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
