import os
import json
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

async def process_pdf(file_path: str, mode: str = "text") -> Dict[str, Any]:
    """
    Extract text or tables from a PDF file.
    
    Args:
        file_path: Path to the PDF file
        mode: "text" for extraction or "tables" for table data
        
    Returns:
        Dict with extracted content or error
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}
    
    result = {
        "success": False,
        "file_path": file_path,
        "timestamp": datetime.now().isoformat(),
        "content": ""
    }
    
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            if mode == "text":
                text = ""
                for page in pdf.pages:
                    text += page.extract_text() or ""
                result["content"] = text
            elif mode == "tables":
                tables = []
                for page in pdf.pages:
                    extracted = page.extract_tables()
                    if extracted:
                        tables.extend(extracted)
                result["content"] = tables
            
            result["success"] = True
    except Exception as e:
        result["error"] = str(e)
    
    return result

async def advanced_browser(url: str, objective: str) -> Dict[str, Any]:
    """
    Execute a complex browsing task using the Reconnaissance-Then-Action pattern.
    
    Args:
        url: The URL to start from
        objective: What you want to achieve (e.g., "Find the pricing table and take a screenshot")
        
    Returns:
        Dict with results and status
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"success": False, "error": "Playwright not available on this system"}
    
    result = {
        "success": False,
        "url": url,
        "objective": objective,
        "actions_taken": [],
        "data": {}
    }
    
    playwright = None
    browser = None
    
    try:
        playwright = await async_playwright().start()
        from app.core.browser_utils import get_browser_launch_args
        launch_options = get_browser_launch_args()
        browser = await playwright.chromium.launch(**launch_options)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # 1. Reconnaissance
        await page.goto(url, wait_until='networkidle')
        result["actions_taken"].append(f"Navigated to {url}")
        
        # 2. Extract context
        title = await page.title()
        content_preview = await page.evaluate("document.body.innerText.slice(0, 1000)")
        
        # 3. Handle Objective (Simple logic for now, can be expanded)
        # Note: In a full implementation, this might call another LLM step to determine actions
        # For now, we extract structured data based on the objective
        
        goal_data = {}
        if "pricing" in objective.lower():
            goal_data = await page.evaluate(r'''() => {
                const prices = document.body.innerText.match(/\$[\d,]+\.?\d*/g) || [];
                return { prices: [...new Set(prices)].slice(0, 10) };
            }''')
            result["actions_taken"].append("Extracted pricing information")
            
        elif "contact" in objective.lower():
            goal_data = await page.evaluate(r'''() => {
                const text = document.body.innerText;
                const emails = text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g) || [];
                return { emails: [...new Set(emails)].slice(0, 5) };
            }''')
            result["actions_taken"].append("Extracted contact information")
            
        result["success"] = True
        result["data"] = {
            "title": title,
            "preview": content_preview,
            "goal_result": goal_data
        }
        
    except Exception as e:
        result["error"] = str(e)
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
            
    return result
