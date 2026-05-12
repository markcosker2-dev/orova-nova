"""
Hunt Porsche Dealerships Script
Uses gspread, Firecrawl, and HAWK persona to find and score Porsche dealerships in California.
"""

import os
import asyncio
import gspread
from app.core.firecrawl_bridge import FirecrawlBridge
from app.core.hawk import HAWK
from app.main import task_queue  # Import the global task_queue


async def hunt_porsche_dealerships():
    """
    Main function to hunt and score Porsche dealerships.
    """
    task_name = "hunt_porsche"

    # Check if task can run
    if not task_queue.start_task(task_name):
        print("Task blocked - another conflicting task is running")
        return

    try:
        # 1. Authenticate with gspread
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        gc = gspread.service_account(filename=creds_path)

        # 2. Open "OROVA Leads" sheet, get HUNT worksheet
        spreadsheet = gc.open("OROVA Leads")
        try:
            worksheet = spreadsheet.worksheet("HUNT")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="HUNT", rows=100, cols=10)
            # Add header
            worksheet.append_row(["Name", "Business", "Email", "Phone", "Website", "HAWK Score", "Luxury Alignment", "Source", "Date Added", "Status"])

        # 3. Check if sheet has data (besides header)
        all_values = worksheet.get_all_values()
        if len(all_values) > 1:
            print("HUNT sheet already has data, skipping hunt")
            return

        # 4. Find 3 Porsche dealerships in California
        # Use websearch to find dealerships
        from app.core.ai_client import UnifiedAIClient  # For searching
        ai_client = UnifiedAIClient()

        search_prompt = """
        Find 3 Porsche dealerships in California. Return JSON array with:
        [{"name": "Dealership Name", "website": "https://...", "location": "City, CA", "phone": "phone number"}]
        """

        search_results = await ai_client.reason(search_prompt)
        import json
        dealerships = json.loads(search_results)

        if not dealerships or len(dealerships) < 3:
            # Fallback to hardcoded or search again
            dealerships = [
                {"name": "Porsche Beverly Hills", "website": "https://www.porschebeverlyhills.com", "location": "Beverly Hills, CA", "phone": "(310) 274-5200"},
                {"name": "Porsche Newport Beach", "website": "https://www.porschenewportbeach.com", "location": "Newport Beach, CA", "phone": "(949) 719-7000"},
                {"name": "Porsche San Diego", "website": "https://www.porschesandiego.com", "location": "San Diego, CA", "phone": "(858) 450-2000"}
            ]

        # Initialize Firecrawl and HAWK
        firecrawl = FirecrawlBridge()
        hawk = HAWK()

        for dealer in dealerships[:3]:  # Take first 3
            # Scrape website for more info
            scrape_result = await firecrawl.scrape_url(dealer["website"])
            if scrape_result["status"] == "success":
                description = scrape_result.get("markdown", "")[:500]  # Limit description
            else:
                description = "Porsche dealership"

            lead_data = {
                "name": dealer["name"],
                "business": dealer["name"],
                "website": dealer["website"],
                "description": description,
                "location": dealer["location"],
                "niche": "automotive"
            }

            # Score with HAWK
            evaluation = await hawk.evaluate_lead_quality(lead_data)
            score = evaluation.get("score", 0)
            justification = evaluation.get("justification", "")

            # Append to sheet
            from datetime import datetime
            date_added = datetime.now().strftime("%Y-%m-%d")
            row = [
                dealer.get("name", ""),
                dealer.get("name", ""),
                "",  # Email
                dealer.get("phone", ""),
                dealer.get("website", ""),
                score,
                justification,
                "Porsche Hunt",
                date_added,
                "New"
            ]
            worksheet.append_row(row)
            print(f"Added {dealer['name']} with HAWK score {score}")

    except Exception as e:
        print(f"Error in hunt_porsche_dealerships: {e}")
    finally:
        task_queue.end_task(task_name)


if __name__ == "__main__":
    asyncio.run(hunt_porsche_dealerships())