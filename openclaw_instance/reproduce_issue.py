
import asyncio
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock Tavily key to force fallback if needed, or leave as is to test env
# os.environ["TAVILY_API_KEY"] = "" 

from app.skills.lead_finder import find_leads

async def main():
    print("--- Testing find_leads with 'luxury remodelers in California' ---")
    try:
        result = await find_leads(count=2, query="luxury remodelers in California")
        print("\nRESULT:")
        print(result)
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    # We need to run this from the parent directory of 'app' usually, 
    # so we might need to adjust sys.path if we run it from openclaw_instance directly.
    import sys
    sys.path.append(os.getcwd())
    
    asyncio.run(main())
