import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import os
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
SHEET_NAME = "OROVA Leads"
TEST_PHONE = "+15550000000" # User can replace this

def inject_test_lead():
    print("🧪 [TEST MODE] Injecting a fake lead into OROVA Pipeline...")
    
    # 1. Connect to Google Sheets
    # Use the path from env or default
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    
    try:
        sheet = client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"❌ Error: Could not find sheet '{SHEET_NAME}'. Make sure it exists and the service account has access.")
        return
    
    # 2. Define the Test Data
    # OROVA Leads Header: ['Timestamp', ' First Name ', 'Last Name', 'Number', 'Business Name', 'Email', 'Location']
    # CEO Agent will look for 'Ready for Call' in the Status column (we'll use column 8/H)
    test_lead = [
        time.strftime("%Y-%m-%d %H:%M:%S"), # Timestamp
        "Test",                             # First Name
        "Ferrari",                          # Last Name
        TEST_PHONE,                         # Number/Phone
        "Test Ferrari BKK (Simulation)",    # Business Name
        "test@ferrari.com",                 # Email
        "Bangkok, Thailand",                # Location
        "Ready for Call",                   # Status (Column 8)
        "Found via Test Script."            # Notes (Column 9)
    ]
    
    # 3. Append to Sheet
    sheet.append_row(test_lead)
    print(f"✅ Success! Added '{test_lead[0]}' to the sheet.")
    print("👀 WATCH YOUR TELEGRAM NOW. The CEO Agent should message you in ~10 seconds.")

if __name__ == "__main__":
    inject_test_lead()
