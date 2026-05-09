import os
import asyncio
import logging
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

async def vision_browse(objective: str, url: str = None) -> str:
    """
    Hermes Evolution: Vision-based Browsing via Browser-use.
    Nova can now 'see' and interact with the page like a human.
    """
    # [P0] Remote Browser connection is mandatory for Render (512MB RAM)
    cdp_url = os.getenv("CDP_URL")
    if not cdp_url:
        return "⚠️ Vision Browse requires a Remote Browser (CDP_URL). Please set it in Render env vars."

    if url:
        objective = f"Go to {url} and then: {objective}"
        
    logger.info(f"👁️ Vision Browse starting: {objective}")
    
    # [P0] FIXED: Use OPENROUTER_API_KEY for OpenRouter calls via ChatOpenAI
    llm = ChatOpenAI(
        model="google/gemini-2.0-flash-lite-preview-02-05",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )
    
    # [P0] FIXED: Pass cdp_url to BrowserConfig to connect to remote browser
    browser = Browser(
        config=BrowserConfig(cdp_url=cdp_url)
    )

    try:
        agent = Agent(
            task=objective,
            llm=llm,
            browser=browser
        )
        
        # [P0] FIXED: Add explicit timeout and extract final result properly
        result = await asyncio.wait_for(agent.run(), timeout=60.0)
        return result.final_result() if hasattr(result, "final_result") else str(result)
        
    except asyncio.TimeoutError:
        return "ERROR: Vision browse timed out after 60s"
    except Exception as e:
        logger.error(f"💥 Vision Browse failed: {e}")
        return f"ERROR: {str(e)}"
    finally:
        # [P0] Ensure browser resources are released
        await browser.close()
