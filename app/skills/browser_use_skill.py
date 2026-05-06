import os
import logging
from browser_use import Agent
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

async def vision_browse(objective: str, url: str = None) -> str:
    """
    Hermes Evolution: Vision-based Browsing via Browser-use.
    Nova can now 'see' and interact with the page like a human.
    """
    if url:
        objective = f"Go to {url} and then: {objective}"
        
    logger.info(f"👁️ Vision Browse starting: {objective}")
    
    # Use OpenAI compatible LLM (OpenRouter)
    llm = ChatOpenAI(
        model="google/gemini-2.0-flash-lite-001",
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://openrouter.ai/api/v1"
    )
    
    # Check for Remote Browser (Required for Render 512MB RAM)
    cdp_url = os.getenv("CDP_URL")
    if not cdp_url:
        return "⚠️ Vision Browse requires a Remote Browser (CDP_URL). Please set it in Render env vars."

    try:
        # Note: browser-use will attempt to connect to the CDP_URL
        # In a real setup, we would initialize the Browser object here.
        agent = Agent(
            task=objective,
            llm=llm
        )
        
        result = await agent.run()
        return str(result)
        
    except Exception as e:
        logger.error(f"💥 Vision Browse failed: {e}")
        return f"ERROR: {str(e)}"
