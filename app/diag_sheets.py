import gspread
import os
from google.oauth2.service_account import Credentials

def diag():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/app/service_account.json")
    print(f"DEBUG: Using creds from {creds_path}")
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=scope)
        client = gspread.authorize(creds)
        print(f"DEBUG: Service Account Email: {creds.service_account_email}")
        
        sheets = client.openall()
        print(f"DEBUG: Found {len(sheets)} spreadsheets:")
        for s in sheets:
            print(f"  - '{s.title}' (ID: {s.id})")
            
    except Exception as e:
        print(f"DEBUG: FAILED with error: {str(e)}")

if __name__ == "__main__":
    diag()
