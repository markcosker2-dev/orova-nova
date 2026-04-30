import asyncio
import os
from dotenv import load_dotenv
from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

# Load environment variables
load_dotenv()

async def test_sheets_integration():
    print("Testing Nova's Google Sheets Integration...")
    
    # Initialize AI client and Planner
    # We use a real AI client here to see if Nova actually picks the tools
    ai_client = UnifiedAIClient()
    planner = TaskPlanner(ai_client)
    
    # Test Goal: Scrape 1 lead and post it to a sheet
    # We'll use a specific query to make it fast
    goal = "Find 1 luxury home remodeling lead in California and post its title and URL into a Google Sheet named 'Nova Leads Test'."
    
    print(f"Goal: {goal}")
    response = await planner.execute(goal)
    print("\n--- Nova's Response ---")
    print(response)

if __name__ == "__main__":
    asyncio.run(test_sheets_integration())
