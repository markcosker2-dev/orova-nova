import gspread
from google.oauth2.service_account import Credentials
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def get_sheets_client():
    import base64
    import json
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON")
    
    try:
        if creds_b64:
            creds_dict = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        else:
            creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
            if not os.path.exists(creds_path):
                logger.error(f"Google Sheets: Credentials not found at {creds_path}")
                return None
            creds = Credentials.from_service_account_file(creds_path, scopes=scope)
            
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
        client = get_sheets_client()
        if not client:
            return "❌ error: Google Sheets credentials not configured."
        
        sheet = client.open(sheet_name).sheet1
        sheet.append_rows(rows)
        logger.info(f"Sheets: Appended {len(rows)} rows to {sheet_name}")
        return f"✅ successfully appended {len(rows)} rows to '{sheet_name}'."
    except Exception as e:
        logger.error(f"Sheets Error: {e}")
        return f"❌ error appending to sheet: {str(e)}"

async def create_new_sheet(sheet_name: str):
    """Create a new Google Sheet."""
    try:
        client = get_sheets_client()
        if not client:
            return "❌ error: Google Sheets credentials not configured."
        
        sheet = client.create(sheet_name)
        # Share with personal email if needed? For now just create.
        return f"✅ successfully created new sheet: '{sheet_name}' (ID: {sheet.id})"
    except Exception as e:
        logger.error(f"Sheets Error: {e}")
        return f"❌ error creating sheet: {str(e)}"
