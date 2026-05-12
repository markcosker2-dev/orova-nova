import gspread
import os

def diag():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    print(f"DEBUG: Using creds from {creds_path}")

    try:
        client = gspread.service_account(filename=creds_path)
        email = getattr(getattr(client, "auth", None), "service_account_email", None)
        if email:
            print(f"DEBUG: Service Account Email: {email}")
        
        sheets = client.openall()
        print(f"DEBUG: Found {len(sheets)} spreadsheets:")
        for s in sheets:
            print(f"  - '{s.title}' (ID: {s.id})")
            
    except Exception as e:
        print(f"DEBUG: FAILED with error: {str(e)}")

if __name__ == "__main__":
    diag()
