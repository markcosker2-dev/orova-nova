# -*- coding: utf-8 -*-
"""
Google Sheets Manager
"""
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from loguru import logger
from datetime import datetime

class SheetManager:
    SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    CREDENTIALS_FILE = "service_account.json"
    SHEET_NAME = "OROVA Leads 2026"
    WORKSHEET_NAME = "Automated Leads"

    @classmethod
    def setup(cls):
        """Verify environment and connect to Sheets."""
        if not os.path.exists(cls.CREDENTIALS_FILE):
             # Try checking in parent if expected there
             if os.path.exists(f"../{cls.CREDENTIALS_FILE}"):
                 cls.CREDENTIALS_FILE = f"../{cls.CREDENTIALS_FILE}"
             else:
                 error_msg = f"CRITICAL: Missing {cls.CREDENTIALS_FILE}. Cannot connect to Google Sheets."
                 logger.critical(error_msg)
                 raise FileNotFoundError(error_msg)
        
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(cls.CREDENTIALS_FILE, cls.SCOPE)
            client = gspread.authorize(creds)
            logger.info(f"Connected to Sheets as: {creds.service_account_email}")
            return client
        except Exception as e:
            logger.error(f"Failed to authorize Google Sheets: {e}")
            raise e

    @classmethod
    def count_recent_leads(cls, hours=24):
        """Count leads added in the last N hours."""
        try:
            client = cls.setup()
            try:
                sheet = client.open(cls.SHEET_NAME)
                worksheet = sheet.worksheet(cls.WORKSHEET_NAME)
            except Exception:
                return 0 # Sheet or worksheet missing

            # Fetch all data (or just first column to be faster)
            # Date Found is column 1 (A)
            dates = worksheet.col_values(1)

            # Remove header if present
            if dates and dates[0] == "Date Found":
                dates = dates[1:]

            count = 0
            now = datetime.now()

            for date_str in dates:
                try:
                    # Format: 2024-06-25 14:30:00 (from log_leads)
                    lead_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    diff = now - lead_date
                    if diff.total_seconds() <= hours * 3600:
                        count += 1
                except ValueError:
                    continue # Skip invalid dates

            return count
        except Exception as e:
            logger.error(f"Failed to count recent leads: {e}")
            return 0

    @classmethod
    def log_leads(cls, leads_list):
        """Batch append leads to the sheet."""
        if not leads_list:
            return

        client = cls.setup()
        
        try:
            # Open Sheet
            try:
                sheet = client.open(cls.SHEET_NAME)
            except gspread.SpreadsheetNotFound:
                logger.warning(f"Spreadsheet '{cls.SHEET_NAME}' not found. Creating it...")
                sheet = client.create(cls.SHEET_NAME)
                sheet.share(client.auth.service_account_email, perm_type='user', role='owner') # Usually fails if service acc creates, but worth a shot if using personal drive logic
            
            # Open/Create Worksheet
            try:
                worksheet = sheet.worksheet(cls.WORKSHEET_NAME)
            except gspread.WorksheetNotFound:
                worksheet = sheet.add_worksheet(title=cls.WORKSHEET_NAME, rows="1000", cols="20")
                
            # Header Check
            if not worksheet.acell('A1').value:
                headers = ["Date Found", "Source Query", "Business Name", "URL", "Snippet/Context"]
                worksheet.append_row(headers)
            
            # Batch Prepare
            rows = []
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for lead in leads_list:
                rows.append([
                    today,
                    "Automated Search", # Placeholder for query if not passed
                    lead.get('title', 'N/A'),
                    lead.get('url', 'N/A'),
                    lead.get('snippet', 'N/A')
                ])
                
            # Batch Append
            worksheet.append_rows(rows)
            logger.success(f"Logged {len(rows)} leads to '{cls.SHEET_NAME}' ({cls.WORKSHEET_NAME})")
            
        except Exception as e:
            logger.error(f"Sheet Error: {e}")
            raise e
