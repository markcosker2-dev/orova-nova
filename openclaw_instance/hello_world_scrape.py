import asyncio
from playwright.async_api import async_playwright
import os

async def hello_world_scrape():
    print(">>> INITIALIZING OROVA HELLO WORLD SCRAPE...")
    
    async with async_playwright() as p:
        # 1. Launch Headless (VPS/Terminal Safe)
        print(">>> Launching Headless Chromium...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 2. Navigate to a complex-ish site (Wikipedia for demo)
        url = "https://en.wikipedia.org/wiki/Main_Page"
        print(f">>> Navigating to {url}...")
        await page.goto(url)
        
        # 3. Anti-Block: Wait for Network Idle
        print(">>> Waiting for networkidle (Anti-Block Logic)...")
        await page.wait_for_load_state('networkidle')
        
        # 4. Reconnaissance: Take Screenshot
        screenshot_path = "hello_world_recon.png"
        print(f">>> Taking Reconnaissance Screenshot: {screenshot_path}...")
        await page.screenshot(path=screenshot_path)
        
        # 5. Extraction
        title = await page.title()
        print(f">>> SUCCESS! Page Title: {title}")
        
        await browser.close()
        print(">>> SCRAPE COMPLETE.")

if __name__ == "__main__":
    asyncio.run(hello_world_scrape())
