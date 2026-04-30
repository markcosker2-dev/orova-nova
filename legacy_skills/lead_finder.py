import logging
import asyncio
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def find_leads(count: int = 5, query: str = "business leads"):
    """
    Scrape leads using headless Chromium (Playwright).
    """
    logger.info(f"LeadFinder: Searching for {count} leads for '{query}'...")
    leads = []
    
    try:
        async with async_playwright() as p:
            # Launch compatible browser
            # args recommended for container environments
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = await context.new_page()

            # 1. Search DuckDuckGo (Easier to scrape than Google)
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}&t=h_&ia=web"
            await page.goto(search_url, timeout=30000)
            await page.wait_for_selector('.result', timeout=10000)

            results = await page.query_selector_all('.result')
            
            for res in results[:count]:
                try:
                    title_el = await res.query_selector('.result__title')
                    link_el = await res.query_selector('.result__a')
                    snippet_el = await res.query_selector('.result__snippet')

                    if title_el and link_el:
                        title = await title_el.inner_text()
                        url = await link_el.get_attribute('href')
                        snippet = await snippet_el.inner_text() if snippet_el else ""

                        if url and url.startswith('http'):
                            leads.append({
                                "title": title,
                                "url": url,
                                "snippet": snippet
                            })
                except Exception as e:
                    continue
            
            await browser.close()
            
    except Exception as e:
        logger.error(f"LeadFinder Error: {e}")
        return [{"error": str(e)}]

    # Formatted String Output for Bot
    if not leads:
        return "No leads found."
    
    result_text = f"🔍 **Found {len(leads)} Leads:**\n\n"
    for l in leads:
        result_text += f"• [{l['title']}]({l['url']})\n  _{l['snippet'][:100]}..._\n\n"
    
    return result_text

async def read_webpage(url: str):
    """
    Visit a specific URL and extract main text content.
    """
    logger.info(f"Broswer: Visiting {url}...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            page = await browser.new_page()
            
            # Go to URL with timeout
            await page.goto(url, timeout=30000)
            
            # Get title and basic text
            title = await page.title()
            content = await page.evaluate("document.body.innerText")
            
            await browser.close()
            
            # Clean content (limit length)
            cleaned_content = " ".join(content.split())[:3000]
            
            return f"📄 **Page: {title}**\n\n{cleaned_content}..."
            
    except Exception as e:
        logger.error(f"ReadPage Error: {e}")
        return f"⚠️ Could not read page: {str(e)}"
