"""
Core_Engine/crm_sync.py
Fixed version — uses google-auth instead of deprecated oauth2client,
adds two-way sync (pull updates from sheet back into SQLite).
"""

import logging
from typing import List, Dict, Any

import gspread
from google.oauth2.service_account import Credentials

from .db_manager import DatabaseManager

logger = logging.getLogger("nova.crm")

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

HEADERS = ["ID", "Business", "Contact", "Phone", "Email", "Website", "Vertical", "Score", "Status"]


class CRMSync:
    """Synchronises SQLite lead data with Google Sheets (both directions)."""

    def __init__(self, sheet_id: str, credentials_file: str = "service_account.json"):
        self.sheet_id = sheet_id
        self.db = DatabaseManager()

        try:
            creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
            gc = gspread.authorize(creds)
            self.sheet = gc.open_by_key(sheet_id).sheet1
            logger.info(f"[CRM] Connected to sheet: {sheet_id}")
        except FileNotFoundError:
            logger.error(f"[CRM] service_account.json not found — CRM sync disabled")
            self.sheet = None
        except Exception as e:
            logger.error(f"[CRM] Failed to connect to Google Sheets: {e}")
            self.sheet = None

    def _check_sheet(self):
        if not self.sheet:
            raise RuntimeError("Google Sheets not connected. Check service_account.json and CRM_SHEET_ID.")

    def sync_leads_to_sheet(self, client_id: int = 0):
        """Push all leads from SQLite → Google Sheets. Clears sheet first."""
        self._check_sheet()
        leads = self.db.get_all_leads(client_id)
        logger.info(f"[CRM] Syncing {len(leads)} leads to Google Sheets")

        self.sheet.clear()
        self.sheet.append_row(HEADERS)

        rows = []
        for lead in leads:
            rows.append([
                lead.get("id", ""),
                lead.get("business", ""),
                lead.get("contact", ""),
                lead.get("phone", ""),
                lead.get("email", ""),
                lead.get("website", ""),
                lead.get("vertical", ""),
                lead.get("score", 0),
                lead.get("status", "New"),
            ])

        if rows:
            self.sheet.append_rows(rows, value_input_option="USER_ENTERED")

        logger.info(f"[CRM] ✅ Synced {len(rows)} rows to Google Sheets")

    def sync_sheet_to_leads(self) -> int:
        """
        Pull status updates from Google Sheets back into SQLite.
        Only the Status column is synced back (don't overwrite scores etc.).
        Returns the count of records updated.
        """
        self._check_sheet()
        rows = self.sheet.get_all_records()
        updated = 0

        for row in rows:
            lead_id = row.get("ID")
            new_status = row.get("Status", "").strip()

            if not lead_id or not new_status:
                continue

            try:
                lead_id = int(lead_id)
                existing = self.db.get_lead(lead_id)
                if existing and existing.get("status") != new_status:
                    self.db.update_lead_status(lead_id, new_status)
                    logger.info(f"[CRM] Lead {lead_id} status updated from sheet: {new_status}")
                    updated += 1
            except (ValueError, TypeError) as e:
                logger.debug(f"[CRM] Skipping invalid row: {e}")
                continue

        logger.info(f"[CRM] Pulled {updated} status updates from Google Sheets")
        return updated
