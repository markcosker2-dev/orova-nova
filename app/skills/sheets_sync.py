import asyncio
import base64
import json
import logging
import os
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

logger = logging.getLogger(__name__)

# Global lock placeholder to prevent Google Sheets 429 Rate Limit errors when syncing multiple leads
_sheets_lock: Optional[asyncio.Lock] = None
_workbook_cache: dict = {"wb": None, "ts": 0.0, "key": None}

WORKBOOK_CACHE_TTL = 300.0  # re-open every 5 minutes
SHEETS_READ_TIMEOUT_S = 45.0  # read timeout

async def _get_sheets_lock_async() -> asyncio.Lock:
    """Guaranteed to create the lock on the currently running event loop."""
    global _sheets_lock
    if _sheets_lock is None:
        _sheets_lock = asyncio.Lock()
    return _sheets_lock

def _principals_cell(lead: dict) -> str:
    """Named principals on the licence, or '' when we never looked.

    0 is stored for "not looked up", so it must never render as a number —
    showing 0 principals would read as a fact we do not have.
    """
    try:
        n = int(lead.get("principal_count") or 0)
    except (TypeError, ValueError):
        return ""
    return str(n) if n > 0 else ""


# A lead that has reached any of these has had outreach sent. Kept as one
# tuple so the sheet's EmailSent column and the cold-lead query cannot drift
# apart about what "contacted" means.
_CONTACTED_STATUSES = ("email sent", "contacted", "replied", "responded",
                       "meeting booked", "booked", "won", "lost")


def _email_sent_cell(lead: dict) -> str:
    """'Yes' / 'No' — has outreach actually gone out to this lead?

    Derived from the stored status, never from the sheet. This column is a
    READ-OUT: editing it in Sheets does nothing, because the database is the
    canonical owner of pipeline state (CLAUDE.md SSoT) and a projection that
    could write back arbitrary state would stop being a projection.
    """
    status = str(lead.get("status") or "").strip().lower()
    if status in _CONTACTED_STATUSES:
        return "Yes"
    if str(lead.get("email_status") or "").strip().lower() in ("sent", "delivered"):
        return "Yes"
    return "No"


def _called_cell(lead: dict) -> str:
    """'Yes' / 'No' — has a call actually been placed?

    Counts real placed calls, so a lead the consent or DNC gate BLOCKED reads
    as No. That distinction matters: a blocked lead has not been worked and
    must not look like it has.
    """
    try:
        return "Yes" if int(lead.get("call_count") or 0) > 0 else "No"
    except (TypeError, ValueError):
        return "No"


_SOLE_OWNER_LABELS = {"solo": "Yes", "has_crew": "No", "unknown": "Unknown"}


def _sole_owner_cell(lead: dict) -> str:
    """'Yes' / 'No' / 'Unknown' — is this a one-person outfit?

    Rendered from lead_validator.crew_status, the SAME function the dialer uses
    to pick which pain the Retell script opens on. That shared derivation is
    the point: this column is how the owner predicts what the call will do, so
    a sheet saying "No" while the dialer sends "solo" would be worse than no
    column — it would be trusted.

    "Unknown" is spelled out rather than left blank. A blank cell reads as
    missing data; the distinction that matters here is that we genuinely do not
    know, and the script will ask on the call instead of assuming.
    """
    from app.skills.lead_validator import crew_status
    return _SOLE_OWNER_LABELS.get(crew_status(lead), "Unknown")


def _col_letter(n: int) -> str:
    """1 -> 'A', 12 -> 'L', 16 -> 'P', 27 -> 'AA'."""
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out or "A"


async def _append_with_backoff(worksheet, row, retries=4):
    """Appends a row to a worksheet with exponential backoff for Google API 429 errors.

    RAW input option: without it Sheets parses "+14047334400" as the NUMBER
    14047334400, which round-trips back as an int and crashed the boot
    restore (2026-07-21). RAW stores exactly the strings we send."""
    for attempt in range(retries):
        try:
            # Capture the API response instead of discarding it (2026-08-09).
            # Sheets returns updates.updatedRange — the exact cells written,
            # tab name included. Production repeatedly logged "4/4 leads
            # synced" against the CONFIRMED-correct spreadsheet (id pinned and
            # matching the owner's URL) while the Leads tab stayed at 1 row.
            # An append that raises nothing and appears nowhere is only
            # explicable by knowing where the API says it put the data, and
            # this call was throwing that away.
            resp = await asyncio.to_thread(
                worksheet.append_row, row, value_input_option="RAW")
            updated_range = ""
            try:
                updated_range = ((resp or {}).get("updates") or {}).get("updatedRange", "")
            except Exception:
                updated_range = f"<unparseable: {type(resp).__name__}>"
            logger.info(f"[SheetsSync] append -> updatedRange={updated_range!r} "
                        f"business={row[1]!r}")
            return {"ok": True, "updated": False, "updated_range": updated_range}
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429 and attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"[SheetsSync] 429 rate limit hit, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
            else:
                raise
        except Exception:
            raise

async def _update_with_backoff(worksheet, target_row, row, retries=4):
    """Updates a row with exponential backoff for Google API 429 errors."""
    for attempt in range(retries):
        try:
            # Range width computed from the row, not hardcoded to ':L'. The
            # literal L pinned the sheet at 12 columns, so adding any column
            # would have written the new fields outside the updated range and
            # silently dropped them.
            _rng = f"A{target_row}:{_col_letter(len(row))}{target_row}"
            try:
                await asyncio.to_thread(worksheet.update, values=[row], range_name=_rng)
            except TypeError:
                await asyncio.to_thread(worksheet.update, _rng, [row])
            return {"ok": True, "updated": True, "row": target_row}
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 429 and attempt < retries - 1:
                wait = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"[SheetsSync] 429 rate limit hit, retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
            else:
                raise
        except Exception:
            raise

SHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")

# Pin the workbook by ID (2026-08-09). Until today the ONLY way this module
# identified the CRM was `client.open("OROVA CRM")` — a lookup by TITLE, which
# asks Drive for a file with that name and takes the first hit. Google allows
# duplicate titles, so if the service account can see two, which one it gets is
# non-deterministic and can change between restarts. `CRM_SHEET_ID` was already
# declared in .env for exactly this and was empty and referenced by NO code.
#
# The symptom that led here: the owner's sheet showed 1 row while production
# read 4 and, in the same process, reported "5/5 leads synced" and then counted
# 4 again. Three irreconcilable numbers is what reading an ambiguous title
# looks like. Setting this makes the target deterministic.
SHEET_ID = (os.getenv("CRM_SHEET_ID") or "").strip()
WORKSHEET_HEADERS = {
    # Columns added 2026-08-09 at the owner's request: Niche, State, Principals
    # and SoleOwner. State is not cosmetic — its absence caused a real bug: the
    # storage gate dedups licence-registry leads on business+state, the sheet
    # did not round-trip state, so a restored lead came back with state='' and
    # then failed to match the same business found by a hunt (state='WA').
    # ACCRETE CONSTRUCTION LLC was stored twice that way. Carrying State fixes
    # the round trip at the source.
    # EmailSent / Called added 2026-08-09 so the owner can see at a glance who
    # has actually been worked, without cross-referencing the CallLog tab.
    # Both are DERIVED from the database on every sync — they are a read-out,
    # not an input. Editing them in the sheet does nothing; only the Email
    # column is read back (see pull_manual_edits_from_sheets).
    "Leads": ["ID", "Business", "Owner", "Email", "Phone", "Website", "URL", "Status",
              "Score", "Source", "Date", "Notes", "Niche", "State", "Principals",
              "SoleOwner", "EmailSent", "Called"],
    "Metrics": ["ClientID", "LeadsFound", "EmailsSent", "CallsMade", "Replies", "Meetings", "LastUpdated"],
    "CallLog": ["CallID", "LeadID", "Business", "Phone", "Outcome", "Duration", "Date"],
    "Meetings": ["MeetingID", "LeadID", "Business", "DateTime", "CalLink", "Status"]
}

async def get_sheets_client() -> Optional[gspread.Client]:
    def _sync():
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
        try:
            if creds_b64:
                creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            else:
                creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(f"Google Sheets credentials not found at {creds_path}")
                creds = Credentials.from_service_account_file(creds_path, scopes=scope)
            return gspread.authorize(creds)
        except Exception as exc:
            logger.error(f"[SheetsSync] Authentication failed: {exc}")
            return None

    return await asyncio.to_thread(_sync)

async def _open_workbook(workbook_name: Optional[str] = None) -> Optional[gspread.Spreadsheet]:
    global _workbook_cache
    now = time.monotonic()
    cache_key = workbook_name or SHEET_NAME

    if (
        _workbook_cache.get("wb") is not None
        and _workbook_cache.get("key") == cache_key
        and now - _workbook_cache["ts"] < WORKBOOK_CACHE_TTL
    ):
        return _workbook_cache["wb"]

    client = await get_sheets_client()
    if not client:
        return None

    def _sync():
        # By ID when pinned — unambiguous, and immune to duplicate titles.
        if SHEET_ID and not workbook_name:
            return client.open_by_key(SHEET_ID)
        # Title lookup: kept for back-compat, but NEVER creates. The old code
        # was `except Exception: return client.create(cache_key)`, which minted
        # a NEW spreadsheet with the same title on any transient failure —
        # owned by the service account and therefore invisible in the owner's
        # Drive. Every blip added another candidate for the next title lookup
        # to resolve to, so the ambiguity ratcheted instead of healing, and
        # writes could land somewhere nobody was looking while reporting
        # success. A backup you cannot find is not a backup.
        return client.open(cache_key)

    try:
        workbook = await asyncio.to_thread(_sync)
    except Exception as exc:
        logger.error(
            f"[SheetsSync] Could not open the CRM workbook "
            f"({'id=' + SHEET_ID if SHEET_ID and not workbook_name else 'title=' + repr(cache_key)}): "
            f"{exc}. NOT creating a replacement — a silently-created duplicate is "
            f"how lead backups went missing. Set CRM_SHEET_ID and share the sheet "
            f"with the service account as Editor.")
        return None
    if workbook is None:
        logger.error(f"[SheetsSync] Could not open workbook '{cache_key}'")
        return None

    # Say WHICH document we are actually using, so "the write is lying" is a
    # checkable claim instead of an inference. Owner can compare this id with
    # the one in their browser URL.
    if not SHEET_ID:
        logger.warning(
            f"[SheetsSync] CRM_SHEET_ID is unset — resolved title {cache_key!r} to "
            f"spreadsheet id={getattr(workbook, 'id', '?')}. Pin CRM_SHEET_ID to "
            f"remove the ambiguity.")
    else:
        logger.info(f"[SheetsSync] workbook id={getattr(workbook, 'id', '?')} "
                    f"title={getattr(workbook, 'title', '?')!r}")

    for title, headers in WORKSHEET_HEADERS.items():
        try:
            worksheet = workbook.worksheet(title)
        except WorksheetNotFound:
            worksheet = workbook.add_worksheet(title=title, rows=1000, cols=len(headers))
        values = worksheet.row_values(1)
        if not values or values != headers:
            try:
                await asyncio.to_thread(worksheet.update, values=[headers], range_name="A1")
            except TypeError:
                await asyncio.to_thread(worksheet.update, "A1", [headers])

    _workbook_cache = {"wb": workbook, "ts": now, "key": cache_key}
    return workbook

async def _get_worksheet(tab_name: str, workbook_name: Optional[str] = None):
    workbook = await _open_workbook(workbook_name)
    if not workbook:
        raise RuntimeError("Google Sheets workbook unavailable")
    try:
        return workbook.worksheet(tab_name)
    except WorksheetNotFound:
        raise RuntimeError(f"Worksheet '{tab_name}' not found")

def _int_or_none(value) -> Optional[int]:
    """Coerce a sheet cell to int, tolerating prefixed IDs ('lead_12345'),
    floats-as-text, blanks, and None. Non-numeric -> None (the DB assigns
    a fresh id on insert)."""
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


async def count_lead_rows(workbook_name: Optional[str] = None) -> Optional[int]:
    """How many DATA rows the Leads tab actually holds (header excluded).

    Exists so a sync can VERIFY itself. `sync_lead_to_sheets` returning ok
    means the API accepted a call, not that a row is readable afterwards — and
    on 2026-08-07 production logged `Sheets: 5/5 leads synced` while the very
    next boot restored 4 rows, 3 of them test fixtures. Nothing noticed,
    because nothing ever looked.

    Returns None (not 0) when the count cannot be taken, so a failed *check* is
    never mistaken for an empty *sheet* — that distinction is the whole point:
    one is "we don't know", the other is "your backup is gone".
    """
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        vals = await asyncio.wait_for(
            asyncio.to_thread(worksheet.col_values, 2),   # column 2 = Business
            timeout=SHEETS_READ_TIMEOUT_S,
        )
        non_empty = [v for v in (vals or []) if str(v).strip()]
        return max(0, len(non_empty) - 1)                 # drop the header
    except Exception as exc:
        logger.warning(f"[SheetsSync] could not count Leads rows: {exc}")
        return None


async def restore_leads_from_sheets() -> List[Dict[str, Any]]:
    try:
        worksheet = await _get_worksheet("Leads")
        try:
            records = await asyncio.wait_for(
                asyncio.to_thread(worksheet.get_all_records),
                timeout=SHEETS_READ_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[SheetsSync] restore_leads_from_sheets timed out after "
                f"{SHEETS_READ_TIMEOUT_S}s. Returning empty — DB will start fresh."
            )
            return []
        leads = []
        for row in records:
            if not row.get("Business") and not row.get("Email") and not row.get("URL"):
                continue
            # Per-row guard: one malformed row (live-observed 2026-07-10: an
            # ID cell holding "lead_12345") must not abort the whole restore —
            # this is the LAST line of defense after a deploy wipes Render's
            # ephemeral disk, so a wholesale [] here means total lead loss.
            try:
                # get_all_records() returns INTS for numeric-looking cells
                # (Sheets parses "+1404..." as a number) — text fields must
                # be str()-coerced or downstream .strip() crashes the boot
                # restore (live 2026-07-21: exit-3 on every fresh deploy).
                def _s(v):
                    return "" if v is None else str(v)
                leads.append({
                    "id": _int_or_none(row.get("ID")),
                    "business": _s(row.get("Business")),
                    "owner": _s(row.get("Owner")),
                    "email": _s(row.get("Email")),
                    "phone": _s(row.get("Phone")),
                    "url": _s(row.get("URL")),
                    "status": _s(row.get("Status")) or "New",
                    "score": _int_or_none(row.get("Score")),
                    "source": _s(row.get("Source")),
                    "date": _s(row.get("Date")),
                    "client_id": _int_or_none(row.get("ClientID")) or 0,
                    # Round-trip the rest of the record (2026-08-09). `website`
                    # was silently dropped on every restore despite having had a
                    # column all along, and `state` was never carried at all —
                    # which broke the business+state dedup key and stored
                    # ACCRETE CONSTRUCTION LLC twice. A backup that loses fields
                    # is only half a backup.
                    "website": _s(row.get("Website")),
                    "vertical": _s(row.get("Niche")),
                    "state": _s(row.get("State")).strip().upper(),
                    "principal_count": _int_or_none(row.get("Principals")) or 0,
                })
            except Exception as row_exc:
                logger.warning(f"[SheetsSync] Skipping malformed lead row: {row_exc}")
        return leads
    except Exception as exc:
        logger.warning(f"[SheetsSync] Could not restore leads from sheets: {exc}")
        return []

async def pull_manual_edits_from_sheets(workbook_name: Optional[str] = None) -> Dict[str, Any]:
    """Read owner-entered EMAILS back out of the Leads tab into the database.

    Why this exists (2026-08-09): the sheet was WRITE-ONLY. `restore_leads_from_sheets`
    is called in exactly one place — the "database appears empty" branch at
    startup — so once the DB holds any lead, nothing ever reads the sheet again.
    The owner planned to fill in emails by hand and expected Nova to use them;
    without this they would have sat in the sheet forever while every outreach
    lane saw a blank field.

    Deliberately NARROW. It pulls one field, `email`, and only into a lead that
    does not already have one. The database is the canonical owner of prospect
    data (CLAUDE.md SSoT) and the sheet is its projection — a projection that
    can overwrite arbitrary columns of its source is no longer a projection,
    and a stray edit or a mis-sorted column would silently corrupt the pipeline.

    Every address still passes the same validator as any other ingest path, so
    a typo or a role address is rejected here exactly as it would be anywhere
    else. Emails are never invented — that is the owner's own rule and the
    documented failure mode of pattern-guessing.

    Returns {"checked", "updated", "rejected", "skipped"}.
    """
    from app.core.database import DatabaseManager
    from app.skills.lead_gen_v3 import _is_valid_business_email

    out = {"checked": 0, "updated": 0, "rejected": 0, "skipped": 0}
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        records = await asyncio.wait_for(
            asyncio.to_thread(worksheet.get_all_records), timeout=SHEETS_READ_TIMEOUT_S)
    except Exception as exc:
        logger.warning(f"[SheetsSync] could not read manual edits ({exc})")
        return out

    for row in records or []:
        business = str(row.get("Business") or "").strip()
        email = str(row.get("Email") or "").strip().lower()
        if not business or not email:
            continue
        out["checked"] += 1
        if not _is_valid_business_email(email):
            logger.info(f"[SHEET-PULL] rejected {email!r} for {business!r} "
                        f"— failed the same validator every other ingest path uses")
            out["rejected"] += 1
            continue
        try:
            state = str(row.get("State") or "").strip().upper()
            existing = await DatabaseManager.fetchone(
                "SELECT id, COALESCE(email,'') AS email FROM leads "
                "WHERE lower(trim(business)) = ? "
                "AND (? = '' OR upper(trim(COALESCE(state,''))) = ?) LIMIT 1",
                (business.lower(), state, state))
            existing = dict(existing) if existing else None
            if not existing:
                out["skipped"] += 1
                continue
            if (existing.get("email") or "").strip():
                out["skipped"] += 1          # never overwrite an address we hold
                continue
            await DatabaseManager.query(
                "UPDATE leads SET email = ?, email_source = 'owner_manual', "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (email, existing["id"]))
            out["updated"] += 1
            logger.info(f"[SHEET-PULL] {business}: email set from the sheet")
        except Exception as exc:
            logger.warning(f"[SHEET-PULL] {business!r} not updated ({exc})")

    logger.info(f"[SHEET-PULL] checked={out['checked']} updated={out['updated']} "
                f"rejected={out['rejected']} skipped={out['skipped']}")
    return out


async def sync_lead_to_sheets(lead: Dict[str, Any], workbook_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        row = [
            lead.get("id") or "",
            lead.get("business") or "",
            lead.get("owner") or "",
            lead.get("email") or "",
            lead.get("phone") or "",
            lead.get("website") or "",
            lead.get("url") or "",
            lead.get("status") or "New",
            lead.get("score") if lead.get("score") is not None else 0,
            lead.get("source") or "Nova Engine",
            lead.get("date") or datetime.now().strftime("%Y-%m-%d"),
            lead.get("notes") or "",
            lead.get("vertical") or "",
            str(lead.get("state") or "").strip().upper(),
            _principals_cell(lead),
            _sole_owner_cell(lead),
            _email_sent_cell(lead),
            _called_cell(lead),
        ]

        # Match on STABLE identity — never the SQLite id. The auto-increment
        # id resets to 1,2,3… on every deploy/OOM wipe, so id-keyed matching
        # made each re-import overwrite a DIFFERENT business that recycled the
        # same id: 5 distinct leads collapsed to ~1 sheet row and the boot
        # restore recovered only 1 (live 2026-07-21). URL (domain) is the
        # strongest stable key; business name is the fallback and is what the
        # restore itself dedups on.
        target_row = None
        if lead.get("url"):
            try:
                url_vals = await asyncio.to_thread(worksheet.col_values, 7)
                search_url = str(lead["url"])
                if search_url in url_vals:
                    idx = url_vals.index(search_url) + 1
                    if idx >= 2:
                        target_row = idx
                        logger.info(f"[SheetsSync] Matched lead by URL at row {target_row}")
            except Exception as exc:
                logger.warning(f"[SheetsSync] Find by URL failed: {exc}")

        biz_vals = None
        if not target_row and lead.get("business"):
            try:
                biz_vals = await asyncio.to_thread(worksheet.col_values, 2)
                search_biz = str(lead["business"]).strip().lower()
                lowered = [str(v).strip().lower() for v in biz_vals]
                if search_biz in lowered:
                    idx = lowered.index(search_biz) + 1
                    if idx >= 2:  # never the header row
                        target_row = idx
                        logger.info(f"[SheetsSync] Matched lead by business name at row {target_row}")
            except Exception as exc:
                logger.warning(f"[SheetsSync] Find by business failed: {exc}")

        async with await _get_sheets_lock_async():
            # Jitter delay inside the lock to ensure Google respects the rate limit and smooths out throughput
            await asyncio.sleep(random.uniform(0.2, 0.6))
            if target_row:
                return await _update_with_backoff(worksheet, target_row, row)

            # ── Write to an EXPLICIT row, never append_row (fixed 2026-08-09).
            # This is the bug that destroyed lead backups for weeks. The
            # instrument added earlier today caught it on its first run —
            # five appends, five different businesses, one second apart:
            #
            #   append -> updatedRange='Leads!A2:L2' business='HEARTWOOD BUILDERS INC'
            #   append -> updatedRange='Leads!A2:L2' business='PEAK BUILDERS INC'
            #   append -> updatedRange='Leads!A2:L2' business='LEWCO CONTRACTING'
            #   append -> updatedRange='Leads!A2:L2' business='ELLCO CONSTRUCTION INC'
            #   append -> updatedRange='Leads!A2:L2' business='ACCRETE CONSTRUCTION LLC'
            #
            # EVERY append targeted the same cells and overwrote its
            # predecessor, so the tab held exactly one row no matter how many
            # leads "synced". `Sheets: 5/5 leads synced` was true and useless at
            # the same time: five API calls really did succeed, into one row.
            #
            # append_row relies on Google's table-range detection from A1, which
            # was resolving to just the header and so kept returning row 2. We
            # do not need that guesswork — column 2 was already fetched above to
            # match on business name, and its length IS the last used row. Write
            # there +1 explicitly. Deterministic, and it reuses the update path
            # that has always worked (it is how matched rows are refreshed).
            if biz_vals is None:
                try:
                    biz_vals = await asyncio.to_thread(worksheet.col_values, 2)
                except Exception as exc:
                    logger.warning(f"[SheetsSync] could not size the Leads tab ({exc}) "
                                   f"— falling back to append_row")
                    return await _append_with_backoff(worksheet, row)
            next_row = max(len(biz_vals), 1) + 1   # never row 1 (the header)
            logger.info(f"[SheetsSync] appending at computed row {next_row} "
                        f"business={row[1]!r}")
            return await _update_with_backoff(worksheet, next_row, row)
    except Exception as exc:
        logger.error(f"[SheetsSync] sync_lead_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}

async def update_lead_status_sheets(lead_id: int, new_status: str, workbook_name: Optional[str] = None) -> Dict[str, Any]:
    await asyncio.sleep(1)
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        cell = await asyncio.to_thread(worksheet.find, str(lead_id))
        headers = WORKSHEET_HEADERS["Leads"]
        status_col = headers.index("Status") + 1
        await asyncio.to_thread(worksheet.update_cell, cell.row, status_col, new_status)
        return {"ok": True, "row": cell.row}
    except Exception as exc:
        logger.error(f"[SheetsSync] update_lead_status_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}

async def sync_metric_to_sheets(client_id: int, metric_name: str, value: Any, workbook_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        worksheet = await _get_worksheet("Metrics", workbook_name)
        records = await asyncio.to_thread(worksheet.get_all_records)
        row_number = None
        for idx, row in enumerate(records, start=2):
            if int(row.get("ClientID", 0)) == int(client_id):
                row_number = idx
                break
        if row_number is None:
            row_number = len(records) + 2
            await asyncio.to_thread(worksheet.append_row, [client_id, 0, 0, 0, 0, 0, ""])

        headers = WORKSHEET_HEADERS["Metrics"]
        if metric_name not in headers:
            raise ValueError(f"Unknown metric name: {metric_name}")
        col_idx = headers.index(metric_name) + 1
        await asyncio.to_thread(worksheet.update_cell, row_number, col_idx, value)
        await asyncio.to_thread(worksheet.update_cell, row_number, headers.index("LastUpdated") + 1, datetime.utcnow().isoformat())
        return {"ok": True, "row": row_number}
    except Exception as exc:
        logger.error(f"[SheetsSync] sync_metric_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}

async def log_call_to_sheets(call_data: Dict[str, Any], workbook_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        worksheet = await _get_worksheet("CallLog", workbook_name)
        row = [
            call_data.get("call_id") or "",
            call_data.get("lead_id") or "",
            call_data.get("business") or "",
            call_data.get("phone") or "",
            call_data.get("outcome") or "",
            call_data.get("duration") or "",
            call_data.get("date") or datetime.utcnow().isoformat(),
        ]
        await asyncio.to_thread(worksheet.append_row, row)
        return {"ok": True}
    except Exception as exc:
        logger.error(f"[SheetsSync] log_call_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}


async def sync_lead_status_to_sheets(lead_id: int, new_status: str, notes: str = "", workbook_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Update a lead's status in Google Sheets CRM when pipeline state changes.
    Called automatically when Nova marks a lead as contacted, replied, meeting_booked, etc.
    """
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        # Find lead by ID column
        id_vals = await asyncio.to_thread(worksheet.col_values, 1)
        search_id = str(lead_id)
        if search_id not in id_vals:
            logger.info(f"[SheetsSync] Lead {lead_id} not found in Sheets, skipping status update")
            return {"ok": False, "reason": "lead_not_found"}
        
        row_idx = id_vals.index(search_id) + 1
        headers = WORKSHEET_HEADERS["Leads"]
        
        # Update Status column (index 7)
        status_col = headers.index("Status") + 1
        await asyncio.to_thread(worksheet.update_cell, row_idx, status_col, new_status)
        
        # Update Notes column (index 11) if provided
        if notes:
            notes_col = headers.index("Notes") + 1
            await asyncio.to_thread(worksheet.update_cell, row_idx, notes_col, notes)
        
        logger.info(f"[SheetsSync] Lead {lead_id} status updated to '{new_status}' in Sheets")
        return {"ok": True, "row": row_idx, "status": new_status}
    except Exception as exc:
        logger.error(f"[SheetsSync] sync_lead_status_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}


async def sync_lead_outcome_to_sheets(lead_id: int, action: str, result: str, details: str = "", workbook_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Log an outreach outcome for a lead in the Sheets CRM.
    Tracks email sent, call made, meeting booked, etc.
    """
    try:
        worksheet = await _get_worksheet("Leads", workbook_name)
        id_vals = await asyncio.to_thread(worksheet.col_values, 1)
        search_id = str(lead_id)
        if search_id not in id_vals:
            return {"ok": False, "reason": "lead_not_found"}
        
        row_idx = id_vals.index(search_id) + 1
        headers = WORKSHEET_HEADERS["Leads"]
        
        # Update Status based on action/result combo
        status_map = {
            ("email_sent", "sent"): "Contacted",
            ("email_sent", "rejected"): "Email Blocked",
            ("email_sent", "failed"): "Email Failed",
            ("call_made", "answered"): "Call Connected",
            ("call_made", "voicemail"): "Voicemail Left",
            ("call_made", "failed"): "Call Failed",
            ("reply", "hot"): "Replied - Hot",
            ("reply", "warm"): "Replied - Warm",
            ("reply", "cold"): "Replied - Cold",
            ("meeting", "booked"): "Meeting Booked",
        }
        new_status = status_map.get((action, result))
        if new_status:
            status_col = headers.index("Status") + 1
            await asyncio.to_thread(worksheet.update_cell, row_idx, status_col, new_status)
        
        # Append notes
        if details:
            notes_col = headers.index("Notes") + 1
            existing_cell = await asyncio.to_thread(worksheet.cell, row_idx, notes_col)
            existing_notes = existing_cell.value or ""
            timestamp = datetime.now().strftime("%m/%d %H:%M")
            new_notes = f"{existing_notes}\n[{timestamp}] {action}: {result} - {details}" if existing_notes else f"[{timestamp}] {action}: {result} - {details}"
            await asyncio.to_thread(worksheet.update_cell, row_idx, notes_col, new_notes)
        
        return {"ok": True, "row": row_idx}
    except Exception as exc:
        logger.error(f"[SheetsSync] sync_lead_outcome_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}
