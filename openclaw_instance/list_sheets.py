import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

def list_sheets():
    print("Listing all accessible Google Sheets...")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path or not os.path.exists(creds_path):
        print(f"❌ Error: Credentials not found at {creds_path}")
        return

    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    sheets = client.openall()
    if not sheets:
        print("Empty: No sheets shared with this service account.")
    else:
        for s in sheets:
            print(f"- {s.title} (ID: {s.id})")

if __name__ == "__main__":
    list_sheets()
