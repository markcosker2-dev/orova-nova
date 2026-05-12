import asyncio
import os
import sys
from dotenv import load_dotenv

# Add app path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env from the correct place
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

async def check_connectivity():
    print("--- SYSTEM CONNECTIVITY CHECK ---")
    
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        print("[-] Tavily: API Key MISSING from .env")
    else:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            # Short search
            res = client.search(query="test", max_results=1)
            print(f"[+] Tavily: Connected (Found {len(res.get('results', []))} results)")
        except Exception as e:
            print(f"[-] Tavily: Error - {e}")

    # 2. Google Sheets
    sheets_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not sheets_creds:
        print("[-] Google Sheets: Credentials path MISSING from .env")
    elif not os.path.exists(sheets_creds):
        print(f"[-] Google Sheets: File NOT FOUND at {sheets_creds}")
    else:
        try:
            import gspread
            client = gspread.service_account(filename=sheets_creds)
            # Try to list sheets
            sheets = client.openall()
            print(f"[+] Google Sheets: Connected (Found {len(sheets)} sheets)")
        except Exception as e:
            print(f"[-] Google Sheets: Error - {e}")

    # 3. OpenAI / OpenRouter
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        print("[-] OpenRouter: API Key MISSING from .env")
    else:
        print("[+] OpenRouter: Key present")

if __name__ == "__main__":
    asyncio.run(check_connectivity())
