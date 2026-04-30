
import asyncio
from duckduckgo_search import DDGS, AsyncDDGS

async def main():
    print("Testing AsyncDDGS...")
    try:
        results = await AsyncDDGS().text("luxury remodelers in California", max_results=5)
        print("Async Results:", results)
    except Exception as e:
        print("Async failed:", e)
        print("Trying Sync DDGS in executor...")
        try:
            loop = asyncio.get_running_loop()
            with DDGS() as ddgs:
                results = await loop.run_in_executor(None, lambda: list(ddgs.text("luxury remodelers in California", max_results=5)))
            print("Sync (Thread) Results:", results)
        except Exception as e2:
            print("Sync failed:", e2)

if __name__ == "__main__":
    asyncio.run(main())
