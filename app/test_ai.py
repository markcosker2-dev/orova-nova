import asyncio
from app.core.ai_client import UnifiedAIClient

async def test():
    c = UnifiedAIClient()
    print("\n=== TEST 1: Quick (GPT-4o-mini via OpenRouter) ===")
    r = await c.quick("Say OK in exactly one word")
    print(f"RESULT: {r}")

    print("\n=== TEST 2: Write (Claude via OpenRouter) ===")
    r2 = await c.write("Write one sentence about lead generation")
    print(f"RESULT: {r2[:100]}")

    print("\n=== ALL TESTS PASSED ===")

asyncio.run(test())
