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

async def _append_with_backoff(worksheet, row, retries=4):
    """Appends a row to a worksheet with exponential backoff for Google API 429 errors.

    RAW input option: without it Sheets parses "+14047334400" as the NUMBER
    14047334400, which round-trips back as an int and crashed the boot
    restore (2026-07-21). RAW stores exactly the strings we send."""
    for attempt in range(retries):
        try:
            await asyncio.to_thread(worksheet.append_row, row, value_input_option="RAW")
            return {"ok": True, "updated": False}
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
            try:
                await asyncio.to_thread(worksheet.update, values=[row], range_name=f"A{target_row}:L{target_row}")
            except TypeError:
                await asyncio.to_thread(worksheet.update, f"A{target_row}:L{target_row}", [row])
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
WORKSHEET_HEADERS = {
    "Leads": ["ID", "Business", "Owner", "Email", "Phone", "Website", "URL", "Status", "Score", "Source", "Date", "Notes"],
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
        try:
            return client.open(cache_key)
        except Exception:
            return client.create(cache_key)

    workbook = await asyncio.to_thread(_sync)
    if workbook is None:
        logger.error(f"[SheetsSync] Could not open or create workbook '{cache_key}'")
        return None

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
                })
            except Exception as row_exc:
                logger.warning(f"[SheetsSync] Skipping malformed lead row: {row_exc}")
        return leads
    except Exception as exc:
        logger.warning(f"[SheetsSync] Could not restore leads from sheets: {exc}")
        return []

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

            return await _append_with_backoff(worksheet, row)
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
