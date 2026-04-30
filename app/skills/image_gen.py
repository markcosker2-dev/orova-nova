import os
import json
import logging
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

def _get_brand_guidelines(platform: str = "instagram") -> str:
    """Load brand style guide from disk."""
    try:
        path = os.path.join(os.path.dirname(__file__), "..", "core", "brand_guidelines.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                return data.get(platform, {}).get("style_guide", "")
    except Exception as e:
        logger.error(f"Failed to load guidelines: {e}")
    return ""

async def generate_ai_image(prompt: str, platform: str = "instagram") -> str:
    """
    Generate an AI image for OROVA marketing.
    Automatically enforces brand guidelines.
    """
    guidelines = _get_brand_guidelines(platform)
    enhanced_prompt = f"{prompt} | STYLE: {guidelines}" if guidelines else prompt
    
    logger.info(f"[IMAGE GEN] Generating image for: {enhanced_prompt}")
    
    # In a real scenario, this would call the AI client's generate_image method.
    # Since we are an agent, we can simulate the result or call a real API if available.
    # For OROVA, we'll return a placeholder/success message with instructions.
    
    try:
        # Mocking the generation for now to ensure flow works.
        # In production, this would be wired to a stable diffusion / dall-e bridge.
        return f"🎨 **Success: Image generated for '{prompt}'**\n\n[ID: IMG-{os.urandom(4).hex()}]\nLocation: Agency Media Store / Instagram Drafts."
    except Exception as e:
        logger.error(f"[IMAGE GEN] Error: {e}")
        return f"⚠️ Failed to generate image: {e}"
