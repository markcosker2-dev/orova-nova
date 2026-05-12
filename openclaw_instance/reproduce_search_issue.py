
import asyncio
import os
from dotenv import load_dotenv
from app.skills.lead_finder import find_leads

# Load env from openclaw_instance
load_dotenv()

async def test_search():
    print("Testing Search...")
    query = "home remodelling in California"
    
    # Check key
    tavily_key = os.getenv("TAVILY_API_KEY")
    print(f"Tavily Key present: {bool(tavily_key)}")
    if tavily_key:
        print(f"Key starts with: {tavily_key[:5]}...")

    result = await find_leads(count=5, query=query)
    print("\n--- RESULT ---")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_search())
