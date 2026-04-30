import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from dotenv import load_dotenv

load_dotenv()

def check_header():
    sheet_name = "OROVA Leads"
    print(f"🔍 Checking header of '{sheet_name}'...")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(sheet_name).sheet1
        print("Header:", sheet.row_values(1))
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_header()
