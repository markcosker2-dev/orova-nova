import gspread
import os

def get_id():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    client = gspread.service_account(filename=creds_path)
    
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
