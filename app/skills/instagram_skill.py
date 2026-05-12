import logging
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

async def generate_instagram_content(topic: str) -> str:
    """Uses Pixel (Creative Director) to plan scroll-stopping IG content."""
    prompt = f"""You are Pixel, OROVA's Creative Director. 
    Mark (the CEO) wants a scroll-stopping Instagram Reel or Carousel about: {topic}
    
    Using 2026 social media best practices, output EXACTLY these 3 things in Markdown:
    1. **Visual/Video Hook** (What happens in the first 1.5 seconds to stop the scroll?)
    2. **Caption** (Engaging, bold, maximum 3 short paragraphs. End with a question to drive DMs).
    3. **Hashtags** (5 highly optimized SEO tags).
    
    Keep it raw, powerful, and luxurious. 
    """
    
    ai = UnifiedAIClient()
    response = await ai.generate(prompt)
    
    if not response or "Failed" in response:
        return "⚠️ Pixel encountered an error generating the Instagram content."
        
    return f"📸 **Pixel's IG Content Studio**\n\n{response}"
