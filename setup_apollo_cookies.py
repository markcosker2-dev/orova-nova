"""
Setup Apollo.io Cookies — One-Time Setup
=========================================
Opens a Playwright browser, navigates to Apollo.IO, and saves
your session cookies so the Apollo browser scraper can work
without requiring manual login in the future.

Run this once, log into Apollo in the window that opens, 
then press Enter in the terminal. Done.
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

COOKIES_PATH = Path(__file__).parent / "app/skills/apollo_scraper/apollo_cookies.json"

async def main():
    COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    async with async_playwright() as p:
        # Open visible browser (not headless) so user can log in
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context()
        page = await context.new_page()
        
        print("\n=== Apollo Cookie Setup ===")
        print(f"A browser window has opened.")
        print(f"Please navigate to app.apollo.io and log in.")
        print(f"Once you're logged in and can see the Apollo dashboard,")
        print(f"press Enter in this terminal to save cookies.")
        print(f"============================\n")
        
        await page.goto("https://app.apollo.io/#/login")
        
        # Wait for user to press Enter
        input(">>> Press Enter here after you've logged into Apollo... ")
        
        # Get cookies from current browser session
        cookies = await context.cookies()
        
        # Filter for Apollo-related cookies only
        apollo_cookies = [c for c in cookies if 'apollo' in c.get('domain', '').lower()]
        
        if not apollo_cookies:
            print("No Apollo cookies found! Make sure you're logged in at app.apollo.io")
            await browser.close()
            return
        
        # Save as JSON
        import json
        with open(COOKIES_PATH, 'w', encoding='utf-8') as f:
            json.dump(apollo_cookies, f, indent=2)
        
        print(f"\nSaved {len(apollo_cookies)} Apollo cookies to:")
        print(f"  {COOKIES_PATH}")
        print(f"\nApollo scraper is now ready to use!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())