import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound

logger = logging.getLogger(__name__)

SHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")
WORKSHEET_HEADERS = {
    "Leads": ["ID", "Business", "Owner", "Email", "Phone", "URL", "Status", "Score", "Source", "Date", "ClientID"],
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

async def _open_workbook() -> Optional[gspread.Spreadsheet]:
    client = await get_sheets_client()
    if not client:
        return None

    def _sync():
        try:
            return client.open(SHEET_NAME)
        except Exception:
            return client.create(SHEET_NAME)

    workbook = await asyncio.to_thread(_sync)
    if workbook is None:
        logger.error(f"[SheetsSync] Could not open or create workbook '{SHEET_NAME}'")
        return None

    for title, headers in WORKSHEET_HEADERS.items():
        try:
            worksheet = workbook.worksheet(title)
        except WorksheetNotFound:
            worksheet = workbook.add_worksheet(title=title, rows=1000, cols=len(headers))
        values = worksheet.row_values(1)
        if not values or values != headers:
            worksheet.update("A1", [headers])
    return workbook

async def _get_worksheet(tab_name: str):
    workbook = await _open_workbook()
    if not workbook:
        raise RuntimeError("Google Sheets workbook unavailable")
    try:
        return workbook.worksheet(tab_name)
    except WorksheetNotFound:
        raise RuntimeError(f"Worksheet '{tab_name}' not found")

async def restore_leads_from_sheets() -> List[Dict[str, Any]]:
    try:
        worksheet = await _get_worksheet("Leads")
        records = await asyncio.to_thread(worksheet.get_all_records)
        leads = []
        for row in records:
            if not row.get("Business") and not row.get("Email") and not row.get("URL"):
                continue
            leads.append({
                "id": int(row.get("ID")) if row.get("ID") else None,
                "business": row.get("Business"),
                "owner": row.get("Owner"),
                "email": row.get("Email"),
                "phone": row.get("Phone"),
                "url": row.get("URL"),
                "status": row.get("Status") or "New",
                "score": int(row.get("Score")) if row.get("Score") not in (None, "") else None,
                "source": row.get("Source"),
                "date": row.get("Date"),
                "client_id": int(row.get("ClientID")) if row.get("ClientID") not in (None, "") else 0,
            })
        return leads
    except Exception as exc:
        logger.warning(f"[SheetsSync] Could not restore leads from sheets: {exc}")
        return []

async def sync_lead_to_sheets(lead: Dict[str, Any]) -> Dict[str, Any]:
    # [P0] Rate Limit Protection: Wait to avoid Google 429 errors
    await asyncio.sleep(2)
    try:
        worksheet = await _get_worksheet("Leads")
        row = [
            lead.get("id") or "",
            lead.get("business") or "",
            lead.get("owner") or "",
            lead.get("email") or "",
            lead.get("phone") or "",
            lead.get("url") or "",
            lead.get("status") or "New",
            lead.get("score") if lead.get("score") is not None else "",
            lead.get("source") or "",
            lead.get("date") or "",
            lead.get("client_id") or 0,
        ]

        if lead.get("id"):
            try:
                cell = worksheet.find(str(lead["id"]))
                target_row = cell.row
            except Exception:
                target_row = None
        else:
            target_row = None

        if not target_row and lead.get("url"):
            try:
                url_cell = worksheet.find(lead["url"])
                target_row = url_cell.row
            except Exception:
                target_row = None

        if target_row:
            await asyncio.to_thread(worksheet.update, f"A{target_row}:K{target_row}", [row])
            return {"ok": True, "updated": True, "row": target_row}

        await asyncio.to_thread(worksheet.append_row, row)
        return {"ok": True, "updated": False}
    except Exception as exc:
        logger.error(f"[SheetsSync] sync_lead_to_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}

async def update_lead_status_sheets(lead_id: int, new_status: str) -> Dict[str, Any]:
    await asyncio.sleep(1)
    try:
        worksheet = await _get_worksheet("Leads")
        cell = await asyncio.to_thread(worksheet.find, str(lead_id))
        headers = WORKSHEET_HEADERS["Leads"]
        status_col = headers.index("Status") + 1
        await asyncio.to_thread(worksheet.update_cell, cell.row, status_col, new_status)
        return {"ok": True, "row": cell.row}
    except Exception as exc:
        logger.error(f"[SheetsSync] update_lead_status_sheets failed: {exc}")
        return {"ok": False, "error": str(exc)}

async def sync_metric_to_sheets(client_id: int, metric_name: str, value: Any) -> Dict[str, Any]:
    try:
        worksheet = await _get_worksheet("Metrics")
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

async def log_call_to_sheets(call_data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        worksheet = await _get_worksheet("CallLog")
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
