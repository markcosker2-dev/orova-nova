"""
check_header.py — PATCHED
BUG FIX: oauth2client is deprecated. Using google.oauth2.service_account.
"""

import gspread
from google.oauth2.service_account import Credentials  # FIX: was oauth2client
import os
from dotenv import load_dotenv

load_dotenv()


def check_header():
    sheet_name = "OROVA Leads"
    print(f"Checking header of '{sheet_name}'...")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if not creds_path:
        print("GOOGLE_APPLICATION_CREDENTIALS not set in .env")
        return

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    # FIX: google-auth replaces deprecated oauth2client
    creds  = Credentials.from_service_account_file(creds_path, scopes=scope)
    client = gspread.authorize(creds)

    try:
        sheet = client.open(sheet_name).sheet1
        print("Header:", sheet.row_values(1))
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    check_header()
