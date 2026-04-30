
import asyncio
import os
import logging
from app.skills.browser_ops import google_search_scrape_async, capture_screenshot_async

# Configure logging
logging.basicConfig(level=logging.INFO)

async def main():
    print("--- Debugging Google Scraper ---")
    query = "luxury remodelers in California"
    
    # 1. Try Scraper
    results = await google_search_scrape_async(query, limit=5)
    print(f"Results: {results}")
    
    # 2. Capture Screenshot of Search Page (manual reconstruction of what the scraper does)
    print("Capturing screenshot...")
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://www.google.com/search?q={query}", wait_until='domcontentloaded')
        await page.screenshot(path="google_debug.png")
        print("Screenshot saved to google_debug.png")
        
        # Save full HTML
        content = await page.content()
        with open("google_debug.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("HTML saved to google_debug.html")

        if "class=\"g\"" in content or "class='g'" in content:
             print("Selector .g FOUND in HTML")
        else:
             print("Selector .g NOT FOUND in HTML")
             
        # Print a snippet of body to see if we are blocked
        print(f"Body snippet: {content[:500]}")
        
        await browser.close()

if __name__ == "__main__":
    import sys
    sys.path.append(os.getcwd())
    asyncio.run(main())
