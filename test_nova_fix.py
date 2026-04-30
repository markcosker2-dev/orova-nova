import asyncio
import os
import sys
from dotenv import load_dotenv

# Load env for API keys
load_dotenv()

# Force UTF-8 for Windows Terminal
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add app path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

async def test_fix():
    print(">>> TESTING NOVA BRAIN OPTIMIZATION...")
    ai_client = UnifiedAIClient()
    planner = TaskPlanner(ai_client)
    
    query = "Nova look up Alex Hormozi and tell me the best way to run OROVA and give me skills i can install into you brain"
    print(f">>> Query: {query}")
    
    # Run with a 2-step limit for the test (to avoid high cost but verify termination/tools)
    # Actually, let's just run it and see if it calls tools and if it says DONE:
    try:
        response = await planner.execute(query)
        print(f"\n>>> NOVA'S RESPONSE:\n{response}")
    except Exception as e:
        print(f">>> Error during test: {e}")

if __name__ == "__main__":
    asyncio.run(test_fix())
