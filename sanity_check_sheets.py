import asyncio
import os
from dotenv import load_dotenv
from app.skills.lead_finder import find_leads
from app.skills.sheets_skill import append_to_sheet, create_new_sheet

import sys
import io

# Fix for Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

async def sanity_check():
    print("Running Direct Sanity Check...")
    
    # 1. Scrape a lead (using specific query for speed)
    print("Step 1: Scraping 1 lead...")
    try:
        # We don't print leads_raw directly to avoid console encoding issues if utf-8 setup fails
        leads_raw = await find_leads(count=1, query="luxury remodeling Manhattan Beach")
        print("Scrape completed.")
        
        # Parse lead (find_leads returns a formatted string)
        # For the test, we'll just extract a title and URL if possible
        # Or just use mock data to verify SHEETS posting works
        lead_data = [["Test Business", "https://example.com", "Test Snippet"]]
        
        # 2. Post to Sheets
        sheet_name = "OROVA Leads"
        print(f"Step 2: Posting to sheet '{sheet_name}'...")
        
        result = await append_to_sheet(sheet_name, lead_data)
        print(f"Result: {result}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(sanity_check())
