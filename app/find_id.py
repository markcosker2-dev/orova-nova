import gspread
import os
from google.oauth2.service_account import Credentials

def get_id():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/service_account.json")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scope)
    client = gspread.authorize(creds)
    
    sheet_name = "OROVA Leads" # The name from test_ceo.py
    try:
        s = client.open(sheet_name)
        print(f"ID_FOUND:{s.id}")
    except Exception as e:
        print(f"ERROR: {e}")
        # Try listing all
        print(f"AVAILABLE: {[sh.title for sh in client.openall()]}")

if __name__ == "__main__":
    get_id()
