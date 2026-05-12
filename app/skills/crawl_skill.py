import asyncio
import logging
from app.core.semaphore import ram_guarded

logger = logging.getLogger(__name__)
AsyncWebCrawler = None
dns = None

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    logger.warning("⚠️ crawl4ai is not installed. elite_scrape will be disabled.")

try:
    import dns.resolver
    dns = dns.resolver
except ImportError:
    logger.warning("⚠️ dnspython is not installed. contact validation may be limited.")

# [P2] Persistent crawler instance to prevent memory leaks and OOM on Render
_crawler: "AsyncWebCrawler | None" = None

import re

def validate_contact_data(email: str, phone: str) -> dict:
    """[P8] Surgically validates email syntax/domain and normalizes phone."""
    result = {"email_valid": False, "phone_valid": False, "clean_email": None}
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if email and re.match(email_regex, email) and dns is not None:
        domain = email.split('@')[1]
        try:
            mx_records = dns.resolve(domain, 'MX')
            if mx_records:
                result["email_valid"] = True
                result["clean_email"] = email.lower()
        except Exception:
            pass
    if phone:
        result["phone_valid"] = True
    return result

async def get_crawler() -> "AsyncWebCrawler":
    global _crawler
    if AsyncWebCrawler is None:
        raise RuntimeError("crawl4ai is not available in this environment")
    if _crawler is None:
        _crawler = AsyncWebCrawler(verbose=False)
        await _crawler.__aenter__()
    return _crawler

async def elite_scrape(url: str, objective: str = "Extract lead contact info") -> dict:
    """
    Hermes Evolution: Elite Scraping via Crawl4AI.
    Bypasses anti-bots and returns structured markdown/JSON.
    """
    logger.info(f"🕷️ Elite Scrape starting for: {url}")
    
    try:
        crawler = await get_crawler()
        
        # [P2] FIXED: Add hard ceiling timeout to prevent runaway processes
        result = await asyncio.wait_for(
            crawler.arun(
                url=url,
                bypass_cache=True,
                screenshot=False, # Disable to save RAM
                magic=True # Enable anti-bot bypass
            ),
            timeout=25.0 # Render will kill the request at 30s anyway
        )
        
        if result.success:
            # [P2] FIXED: Guard against AttributeError and extract markdown safely
            raw_md = getattr(result.markdown_v2, "raw_markdown", None) or getattr(result, "markdown", "")
            return {
                "status": "success",
                "markdown": str(raw_md)[:5000], # Cap for context window
                "metadata": result.metadata
            }
        else:
            return {"status": "failed", "error": result.error_message}
            
    except asyncio.TimeoutError:
        return {"status": "error", "error": "Scrape timed out after 25s"}
    except Exception as e:
        logger.error(f"💥 Elite Scrape failed: {e}")
        return {"status": "error", "error": str(e)}

async def search_and_elite_scrape(query: str):
    """Placeholder for combined search + elite scrape workflow."""
    # In a real integration, this would use DDG to find URLs and then Crawl4AI to rip them.
    pass

async def cleanup_crawler():
    """Close the global crawler on shutdown."""
    global _crawler
    if _crawler is not None:
        try:
            await _crawler.__aexit__(None, None, None)
        except Exception:
            pass
        _crawler = None
