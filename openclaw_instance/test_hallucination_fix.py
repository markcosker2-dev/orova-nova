import asyncio
import os
import sys
import traceback
from dotenv import load_dotenv

# Add app path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

import sys
import io

# Fix for Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

async def test_hallucination_fix():
    print("--- TESTING HALLUCINATION FIX ---")
    ai_client = UnifiedAIClient()
    planner = TaskPlanner(ai_client)
    
    # This query previously triggered "ETA 3 minutes"
    goal = "Find 5 luxury CA home remodelers and 5 LA premium auto shops with name, phone, website."
    
    print(f"Goal: {goal}")
    print("Nova should call 'find_leads' multiple times instead of promising an ETA.")
    
    # We use a mocked history if needed, but let's see a fresh start
    try:
        response = await planner.execute(goal)
        print("\n--- Nova's Final Response ---")
        print(response)
        
        # Check for forbidden keywords
        hallucination_keywords = ["minute", "eta", "check back", "manual", "bypass"]
        if any(k in response.lower() for k in hallucination_keywords):
            print("\n[-] FAILED: Response still contains hallucination keywords.")
        else:
            print("\n[+] PASSED: No hallucination keywords found.")
            
    except Exception as e:
        print(f"\n[-] ERROR: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_hallucination_fix())
