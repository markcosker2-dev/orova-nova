import gspread
from google.oauth2.service_account import Credentials
import os
import logging
import asyncio
import json
import base64
from typing import List, Any, Optional

logger = logging.getLogger(__name__)

# Correct OAuth scopes: drive scope alone can silently fail on append_rows
# drive.file = per-file access (narrowest), spreadsheets scope required for write
SHEET_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

def get_sheets_client() -> Optional[gspread.Client]:
    """Get authorized Google Sheets client using env vars or file."""
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")

    try:
        if creds_b64:
            creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
            creds = Credentials.from_service_account_info(creds_dict, scopes=SHEET_SCOPES)
        else:
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            if not os.path.exists(creds_path):
                logger.error(f"Google Sheets: Credentials not found at {creds_path}")
                return None
            creds = Credentials.from_service_account_file(creds_path, scopes=SHEET_SCOPES)

        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Google Sheets auth error: {e}")
        return None


async def append_to_sheet(sheet_name: str, rows: List[List[Any]]):
    """
    Append rows to a Google Sheet.
    :param sheet_name: Name of the Google Sheet.
    :param rows: List of rows to append (each row is a list of values).
    """
    try:
        loop = asyncio.get_running_loop()
        client = await loop.run_in_executor(None, get_sheets_client)
        if not client:
            return "❌ error: Google Sheets credentials not configured."

        # Open sheet and append rows in executor to avoid blocking event loop
        def _append():
            try:
                sheet = client.open(sheet_name).sheet1
                sheet.append_rows(rows)
                return True
            except Exception as inner:
                # Retry once after brief backoff for 429s
                import time
                time.sleep(2)
                try:
                    sheet = client.open(sheet_name).sheet1
                    sheet.append_rows(rows)
                    return True
                except Exception as retry_err:
                    raise retry_err

        await loop.run_in_executor(None, _append)
        logger.info(f"Sheets: Appended {len(rows)} rows to {sheet_name}")
        return f"✅ successfully appended {len(rows)} rows to '{sheet_name}'."
    except Exception as e:
        logger.error(f"Sheets Error: {e}", exc_info=True)
        return f"❌ error appending to sheet: {str(e)}"


async def create_new_sheet(sheet_name: str):
    """Create a new Google Sheet."""
    try:
        loop = asyncio.get_running_loop()
        client = await loop.run_in_executor(None, get_sheets_client)
        if not client:
            return "❌ error: Google Sheets credentials not configured."

        def _create():
            return client.create(sheet_name)

        sheet = await loop.run_in_executor(None, _create)
        return f"✅ successfully created new sheet: '{sheet_name}' (ID: {sheet.id})"
    except Exception as e:
        logger.error(f"Sheets Error: {e}", exc_info=True)
        return f"❌ error creating sheet: {str(e)}"