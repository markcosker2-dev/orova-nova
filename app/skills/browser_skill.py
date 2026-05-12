import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def browse_agent(url: str, objective: str):
    """
    Advanced browsing agent. Visits a URL, scrolls, and extracts info based on objective.
    """
    logger.info(f"🌐 BrowseAgent: Visiting {url} with objective: {objective}")
    
    try:
        async with async_playwright() as p:
            from app.core.browser_utils import get_browser_launch_args
            launch_options = get_browser_launch_args()
            browser = await p.chromium.launch(**launch_options)
            page = await browser.new_page()
            
            # Go to URL
            await page.goto(url, timeout=30000, wait_until="networkidle")
            
            # Basic scroll to load dynamic content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            await page.wait_for_timeout(1000)
            
            # Extract content
            title = await page.title()
            # Try to find relevant text based on objective (simple logic)
            content = await page.evaluate("document.body.innerText")
            
            await browser.close()
            
            # Clean and truncate
            cleaned = " ".join(content.split())
            # Return a slightly larger chunk for the "Advanced" agent
            return f"🌐 [BrowseAgent Result for: {objective}]\nTitle: {title}\nContent Snippet: {cleaned[:5000]}..."

    except Exception as e:
        logger.error(f"BrowseAgent Error: {e}")
        return f"⚠️ BrowseAgent failed: {str(e)}"
