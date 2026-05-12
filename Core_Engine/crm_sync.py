# -*- coding: utf-8 -*-
"""
OROVA Core Engine — CRM Sync
Extracted from worker.py. Syncs leads to Google Sheets per vertical.
"""

import os
import json
import logging
import requests
import gspread

logger = logging.getLogger(__name__)


class CRMSync:
    """Sync leads to Google Sheets / CRM. One sheet per vertical."""

    def __init__(self, vertical_name: str = None):
        self.vertical_name = vertical_name
        self.creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        self.client = None
        self._connect()

    def _connect(self):
        """Authenticate with Google Sheets."""
        try:
            self.client = gspread.service_account(filename=self.creds_path)
            logger.info("CRM: Connected to Google Sheets")
        except Exception as e:
            logger.error(f"CRM: Connection failed: {e}")

    def get_sheet(self, sheet_name: str = None):
        """Get or create a sheet for the vertical."""
        if not self.client:
            return None

        if sheet_name is None:
            sheet_name = f"OROVA Leads - {self.vertical_name}" if self.vertical_name else "OROVA Leads"

        try:
            spreadsheet = self.client.open(sheet_name)
            return spreadsheet.sheet1
        except gspread.SpreadsheetNotFound:
            logger.warning(f"Sheet '{sheet_name}' not found.")
            return None

    def push_leads(self, leads: list, sheet_name: str = None):
        """Push a list of lead dicts to Google Sheets."""
        sheet = self.get_sheet(sheet_name)
        if not sheet:
            return False

        headers = sheet.row_values(1)
        if not headers:
            # Initialize headers from first lead
            if leads:
                headers = list(leads[0].keys())
                sheet.append_row(headers)

        for lead in leads:
            row = [str(lead.get(h, "")) for h in headers]
            sheet.append_row(row)

        logger.info(f"Pushed {len(leads)} leads to '{sheet_name or 'default'}'")
        return True

    def get_leads_by_status(self, status: str, sheet_name: str = None) -> list:
        """Get all leads with a specific status."""
        sheet = self.get_sheet(sheet_name)
        if not sheet:
            return []

        rows = sheet.get_all_records()
        return [r for r in rows if r.get("Status", "") == status]

    def update_status(self, row_index: int, new_status: str, sheet_name: str = None):
        """Update lead status in the sheet."""
        sheet = self.get_sheet(sheet_name)
        if not sheet:
            return

        headers = sheet.row_values(1)
        status_col = headers.index("Status") + 1 if "Status" in headers else 8
        sheet.update_cell(row_index, status_col, new_status)

    def send_telegram_report(self, message: str):
        """Send a report to Telegram (CEO notification)."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("PERSONAL_CHAT_ID")
        if not token or not chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, data={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            })
        except Exception as e:
            logger.error(f"Telegram report failed: {e}")
