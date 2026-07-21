"""Durability ladder — the single entry point for persisting lead work
(2026-07-21, extracted per ADR-0010/SSoT after the OOM-restart loss).

Render's disk is ephemeral: deploys create a fresh disk and crash-restarts
reset the container's writable layer. Twice now, lead work that only lived
in SQLite was destroyed (the first real hunt by a deploy on 2026-07-20;
the CSV re-import by an OOM restart on 2026-07-21). Every path that WRITES
valuable lead state must call persist_leads_durably() afterwards:

    Tier 1  Google Drive snapshot  (full fidelity: leads + learning data)
    Tier 2  Leads sheet sync       (leads only; separate working creds —
                                    the boot-restore fallback source)

Fail-open by contract: persistence failure logs and never breaks the
calling operation. This module is the canonical owner of the ladder —
callers (hunt lane, CSV import, reenrich) must not reimplement it.
"""
import logging

logger = logging.getLogger(__name__)


async def persist_leads_durably(recent_count: int = 25, source: str = "?") -> dict:
    """Snapshot to Drive; on failure, sync the most recent `recent_count`
    leads to the Sheets tier. Returns {"drive": bool, "sheets_synced": int}."""
    result = {"drive": False, "sheets_synced": 0}

    try:
        from app.skills.vault_skill import backup_database
        bk = await backup_database()
        result["drive"] = bool(bk.get("ok"))
        if result["drive"]:
            logger.info(f"[DURABILITY:{source}] 💾 Drive snapshot uploaded: {bk.get('filename')}")
        else:
            logger.warning(f"[DURABILITY:{source}] ⚠️ Drive snapshot failed: {bk.get('error')}")
    except Exception as e:
        logger.warning(f"[DURABILITY:{source}] ⚠️ Drive snapshot error (non-fatal): {e}")

    if not result["drive"]:
        try:
            from app.core.database import DatabaseManager
            from app.skills.sheets_sync import sync_lead_to_sheets
            rows = await DatabaseManager.query(
                "SELECT * FROM leads WHERE COALESCE(status,'') != 'Invalid' "
                "ORDER BY id DESC LIMIT ?", (recent_count,), fetchall=True)
            for row in rows or []:
                try:
                    res = await sync_lead_to_sheets(dict(row))
                    if res.get("ok"):
                        result["sheets_synced"] += 1
                except Exception as row_err:
                    logger.warning(f"[DURABILITY:{source}] sheet sync of one lead failed: {row_err}")
            logger.info(f"[DURABILITY:{source}] 📋 Sheets fallback: "
                        f"{result['sheets_synced']}/{len(rows or [])} leads synced")
        except Exception as e:
            logger.warning(f"[DURABILITY:{source}] ⚠️ Sheets fallback failed (non-fatal): {e}")

    return result
