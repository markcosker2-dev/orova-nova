# -*- coding: utf-8 -*-
import asyncio
from typing import Dict
from playwright.async_api import async_playwright

async def research_lead(url: str) -> Dict[str, str]:
    defaults = {"business_name": "your business", "icebreaker": "your recent projects"}
    if not url: return defaults
    
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            await page.goto(url, timeout=30000)
            
            # Extract business name
            title = await page.title()
            h1 = await page.evaluate("() => document.querySelector('h1')?.innerText")
            business_name = (h1 or title or "your business").strip()
            
            # Extract icebreaker
            desc = await page.evaluate("() => document.querySelector('meta[name=\"description\"]')?.content")
            p_text = await page.evaluate("() => document.querySelector('p')?.innerText")
            icebreaker = (desc or p_text or "your recent projects").strip()[:150]
            
            return {
                "business_name": business_name,
                "icebreaker": icebreaker
            }
    except Exception as e:
        print(f"Research failed: {e}")
        return defaults
    finally:
        pass # Context manager handles close
