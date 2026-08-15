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
import asyncio
import logging

logger = logging.getLogger(__name__)

# Seconds between per-lead Sheets syncs.
#
# `sync_lead_to_sheets` costs a READ (find the row) plus a WRITE, and Google's
# default Sheets quota is 60 read requests per minute per user. A hunt syncs 5
# leads and never noticed. The full resync added in #174 syncs every lead, and
# at 40 leads it burst straight through the read quota:
#
#   [SheetsSync] APIError: [429]: Quota exceeded for quota metric 'Read requests'
#   [DURABILITY:resync] 📋 Sheets: 33/40 leads synced
#   [DURABILITY:resync] ⚠️ could not verify the Sheets backup
#
# Two consecutive passes each stalled around 33-34 of 40, so the operation
# could never finish and the rows it dropped were the ones still missing the
# new column — the exact rows it existed to repair.
#
# The write path already retries 429s with exponential backoff
# (`_append_with_backoff`), but backoff cannot help a burst that is over quota
# from the first second, and the READ side has no backoff at all. Pacing does.
# ~1.1s keeps a run under ~55 reads/minute with headroom for the verify call.
SHEETS_SYNC_PACING_S = 1.1

# Below this, pacing is pure latency for no benefit — a hunt's handful of leads
# was never near the quota.
SHEETS_PACING_THRESHOLD = 10


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
        # Pace only a bulk run. A hunt's five leads pay nothing.
        pace = SHEETS_SYNC_PACING_S if len(rows) >= SHEETS_PACING_THRESHOLD else 0
        if pace:
            logger.info(f"[DURABILITY:{source}] pacing {len(rows)} leads at "
                        f"{pace}s to stay inside the Sheets read quota "
                        f"(~{int(len(rows) * pace)}s)")
        for i, row in enumerate(rows):
            if pace and i:
                await asyncio.sleep(pace)
            try:
                res = await sync_lead_to_sheets(dict(row))
                if res.get("ok"):
                    result["sheets_synced"] += 1
            except Exception as row_err:
                logger.warning(f"[DURABILITY:{source}] sheet sync of one lead failed: {row_err}")
        logger.info(f"[DURABILITY:{source}] 📋 Sheets: "
                    f"{result['sheets_synced']}/{len(rows)} leads synced")

        # ── VERIFY THE WRITE LANDED ─────────────────────────────────────────
        # "N/N synced" only means N API calls returned ok. It does NOT mean N
        # rows are readable afterwards, and that gap hid a total backup failure
        # for weeks: on 2026-08-07 production logged "Sheets: 5/5 leads synced"
        # and the very next boot restored 4 rows — 3 of them 'Acme' test
        # fixtures. 15 leads became 1, twice in one day, and no log line ever
        # said anything was wrong.
        #
        # So the durable tier now reads itself back and compares against what
        # the database actually holds. A backup that cannot be read is not a
        # backup, and the only thing worse than not having one is believing you
        # do. This costs one extra API call per run.
        try:
            from app.skills.sheets_sync import count_lead_rows
            sheet_rows = await count_lead_rows()
            result["sheet_rows"] = sheet_rows

            # Compare LIKE WITH LIKE (fixed 2026-08-09, first run of this check
            # in production). Two defects were hiding here, and the first one
            # meant this block had never executed even once:
            #
            # 1. `(db_row or {}).get("c")` — fetchone returns a sqlite3.Row
            #    (the pool sets row_factory=sqlite3.Row) and Row has no .get().
            #    Every run logged "backup verification failed ('sqlite3.Row'
            #    object has no attribute 'get') — durability UNKNOWN", so #153
            #    shipped an instrument that could never take a reading. The
            #    unit tests passed because they mocked fetchone with a dict,
            #    a shape production never produces.
            #
            # 2. Raw row counts are not comparable. sync_lead_to_sheets UPSERTS,
            #    matching on URL and falling back to business name, so the sheet
            #    is a DEDUPLICATED projection. The leads table is not: save_lead
            #    only dedups on email or website domain, and licence-registry
            #    rows (WA L&I / OR CCB / CA CSLB — now the main source) carry
            #    neither, so the same contractor is re-inserted on every hunt.
            #    Live proof, 2026-08-09: 24 lead rows, 13 distinct businesses.
            #    Comparing 13 sheet rows against 24 DB rows would have screamed
            #    BACKUP INCOMPLETE while nothing whatsoever was missing — and a
            #    monitor that cries wolf gets ignored exactly when it is right.
            #
            # So the question the check must answer is "does every distinct
            # business have a row?", not "do the two totals match?".
            db_row = await DatabaseManager.fetchone(
                "SELECT COUNT(*) AS total, "
                "COUNT(DISTINCT COALESCE(NULLIF(TRIM(url),''), LOWER(TRIM(business)))) AS distinct_ids "
                "FROM leads WHERE COALESCE(status,'') != 'Invalid'")
            db_row = dict(db_row) if db_row else {}
            db_total = db_row.get("total") or 0
            db_distinct = db_row.get("distinct_ids") or 0
            result["db_total"] = db_total
            result["db_distinct"] = db_distinct

            if sheet_rows is None:
                logger.warning(f"[DURABILITY:{source}] ⚠️ could not verify the Sheets "
                               f"backup — treat durability as UNKNOWN this run.")
            elif sheet_rows < db_distinct:
                result["verified"] = False
                logger.error(
                    f"[DURABILITY:{source}] 🚨 BACKUP INCOMPLETE — the database holds "
                    f"{db_distinct} distinct businesses ({db_total} rows) but the Leads "
                    f"sheet has only {sheet_rows} rows. {db_distinct - sheet_rows} "
                    f"business(es) are lost on the next restart. Sheets is the durable "
                    f"tier; Drive is optional and currently dead.")
            else:
                result["verified"] = True
                logger.info(f"[DURABILITY:{source}] ✅ verified: sheet holds {sheet_rows} "
                            f"rows covering {db_distinct} distinct businesses "
                            f"({db_total} lead rows)")
        except Exception as verify_err:
            logger.warning(f"[DURABILITY:{source}] backup verification failed "
                           f"({verify_err}) — durability UNKNOWN this run.")
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
