"""Durability ladder — the single entry point for persisting lead work
(2026-07-21, extracted per ADR-0010/SSoT after the OOM-restart loss).

Render's disk is ephemeral: deploys create a fresh disk and crash-restarts
reset the container's writable layer. Twice now, lead work that only lived
in SQLite was destroyed (the first real hunt by a deploy on 2026-07-20;
the CSV re-import by an OOM restart on 2026-07-21). Every path that WRITES
valuable lead state must call persist_leads_durably() afterwards:

    Tier 1  Leads sheet sync      ALWAYS runs. Service-account credential
                                  (GOOGLE_CREDENTIALS_JSON), which does not
                                  expire. This is the boot-restore source.
    Tier 2  Google Drive snapshot Optional extra. Higher fidelity (leads +
                                  learning data), but its credential is
                                  fragile — see below. Never gates Tier 1.

Fail-open by contract: persistence failure logs and never breaks the
calling operation. This module is the canonical owner of the ladder —
callers (hunt lane, CSV import, reenrich) must not reimplement it.

── Why Sheets is Tier 1 as of 2026-08-02 ───────────────────────────────────
Drive used to be Tier 1 and Sheets ran ONLY `if not drive`. Two problems,
one of them silent for weeks:

1. The Drive credential keeps dying. Owner report: "do i alway have to get
   the refresh token? ive changed it 3 times already." The OAuth consent
   screen is External + Testing, and Google expires refresh tokens from
   Testing-status apps after exactly 7 days by design. Three re-issues,
   three 7-day deaths, and each death left production restoring 0 leads.

2. The worse one: a SUCCESSFUL Drive backup skipped the Sheets copy
   entirely. So Drive was a single point of failure — the moment its token
   expired there was nothing in Sheets to fall back TO, because the
   fallback had been suppressed on every run where Drive still worked.

Note the fix is NOT "use the service account for Drive". Service accounts
have no Drive storage quota and cannot own files; that upload fails with
403 storageQuotaExceeded outside a Workspace shared drive. The same
credential works fine for Sheets because a Sheet is owned by a real user
and merely shared with the service account. That asymmetry is the whole
reason Sheets is the durable tier and Drive is the bonus.

Verified in production 2026-08-02: `[DURABILITY:hunt] Sheets fallback: 1/1
leads synced` while Drive was returning invalid_grant.
"""
import logging

logger = logging.getLogger(__name__)


async def persist_leads_durably(recent_count: int = 25, source: str = "?") -> dict:
    """Sync the most recent `recent_count` leads to Sheets, then attempt an
    optional full-fidelity Drive snapshot.

    Returns {"sheets_synced": int, "sheets_total": int, "drive": bool}.
    `drive` False is NOT a failure — it is the expected steady state until
    the OAuth consent screen is published. Lead data is safe either way.
    """
    result = {"sheets_synced": 0, "sheets_total": 0, "drive": False}

    # ── Tier 1: Sheets. Unconditional. This is the one that must not be
    # skipped, because it is the source the boot restore actually reads.
    try:
        from app.core.database import DatabaseManager
        from app.skills.sheets_sync import sync_lead_to_sheets
        rows = await DatabaseManager.query(
            "SELECT * FROM leads WHERE COALESCE(status,'') != 'Invalid' "
            "ORDER BY id DESC LIMIT ?", (recent_count,), fetchall=True)
        rows = rows or []
        result["sheets_total"] = len(rows)
        for row in rows:
            try:
                res = await sync_lead_to_sheets(dict(row))
                if res.get("ok"):
                    result["sheets_synced"] += 1
            except Exception as row_err:
                logger.warning(f"[DURABILITY:{source}] sheet sync of one lead failed: {row_err}")
        logger.info(f"[DURABILITY:{source}] 📋 Sheets: "
                    f"{result['sheets_synced']}/{len(rows)} leads synced")
    except Exception as e:
        logger.error(f"[DURABILITY:{source}] ⚠️ Sheets sync failed (non-fatal, but this "
                     f"is the durable tier — lead data is now at risk): {e}")

    # ── Tier 2: Drive. Optional. Adds learning data that Sheets cannot hold,
    # but must never gate or suppress Tier 1, and must never look like an
    # incident when it is simply unconfigured.
    try:
        from app.skills.vault_skill import backup_database
        bk = await backup_database()
        result["drive"] = bool(bk.get("ok"))
        if result["drive"]:
            logger.info(f"[DURABILITY:{source}] 💾 Drive snapshot uploaded: {bk.get('filename')}")
        else:
            logger.info(f"[DURABILITY:{source}] Drive snapshot unavailable "
                        f"({bk.get('error')}) — optional tier, leads are in Sheets.")
    except Exception as e:
        logger.info(f"[DURABILITY:{source}] Drive snapshot skipped ({e}) — "
                    f"optional tier, leads are in Sheets.")

    return result
