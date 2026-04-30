import asyncio
import os
import logging
from dotenv import load_dotenv
from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

# Basic Logging
logging.basicConfig(level=logging.INFO)

async def test_agent_loop():
    load_dotenv()
    
    # 1. Init AI Client
    client = UnifiedAIClient()
    
    # 2. Init Planner
    planner = TaskPlanner(client)
    
    # 3. Test Goal
    goal = "Find the phone number of 'Cosker OROVA' or a similar marketing agency in Israel by searching the web."
    print(f"\n[START] Testing Agent with goal: {goal}\n")
    
    result = await planner.execute(goal)
    
    print("\n--- FINAL RESULT ---")
    print(result)
    print("---------------------\n")

if __name__ == "__main__":
    asyncio.run(test_agent_loop())
