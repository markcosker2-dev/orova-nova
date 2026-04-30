import asyncio
import os
from dotenv import load_dotenv
from app.core.ai_client import UnifiedAIClient
from app.core.planner import TaskPlanner

async def test_supercharged_nova():
    load_dotenv()
    client = UnifiedAIClient()
    planner = TaskPlanner(client)
    
    test_queries = [
        "Check my inbox for unread emails.",
        "What's on my calendar for today?",
        "Create a meeting called 'Ferrari Strategy' for tomorrow at 2pm.",
        "Perform an SEO audit on https://www.ferrari.com"
    ]
    
    print("\n[TEST] Testing Supercharged Nova Skills...\n")
    
    for query in test_queries:
        print(f"User: {query}")
        try:
            response = await planner.execute(query)
            content = getattr(response, 'content', response)
            print(f"Nova: {str(content).encode('ascii', 'ignore').decode('ascii')}")
        except Exception as e:
            print(f"Error executing '{query}': {e}")
        print("-" * 30)

if __name__ == "__main__":
    asyncio.run(test_supercharged_nova())
