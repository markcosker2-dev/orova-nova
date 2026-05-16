import logging
import asyncio
from typing import Dict, Any
from app.core.ai_client import UnifiedAIClient
from app.skills.browser_ops import browse_and_extract

logger = logging.getLogger(__name__)
ai = UnifiedAIClient()

async def scan_opportunity(url: str, business_name: str) -> Dict[str, Any]:
    """
    Visits a business website and identifies 'Opportunity Gaps' 
    (e.g., slow load, no contact form, poor SEO, outdated design).
    """
    logger.info(f"[OPPORTUNITY SCANNER] Scanning {business_name} at {url}...")
    
    try:
        # 1. Scrape the site for content
        content = await browse_and_extract(url=url, objective="Identify marketing weaknesses and business goals")
        
        # 2. Ask AI to find the 'Gaps'
        prompt = f"""
        Analyze the website content of '{business_name}' and identify 3-5 'Marketing Gaps' or weaknesses.
        Focus on things OROVA (an AI agency) can fix:
        - Lack of AI automation (no chatbot)
        - Poor lead capture (no clear CTA)
        - SEO weaknesses
        - Outdated design
        
        Content:
        {str(content)[:4000]}
        
        Format your response as a JSON object:
        {{
            "gaps": ["gap 1", "gap 2"],
            "hook": "A one-sentence icebreaker mentioning one of these gaps",
            "score": 1-10 (how much they need help)
        }}
        """
        
        res_raw = await ai.extract(prompt)
        # Attempt to parse JSON from AI response
        import json
        try:
            # Clean possible markdown code blocks
            clean_res = res_raw.strip().replace("```json", "").replace("```", "")
            data = json.loads(clean_res)
        except:
            data = {
                "gaps": ["General digital presence optimization"],
                "hook": f"I noticed some opportunities to enhance {business_name}'s digital footprint.",
                "score": 5
            }
            
        logger.info(f"[OPPORTUNITY SCANNER] Scan complete for {business_name}. Score: {data.get('score')}")
        return data

    except Exception as e:
        logger.error(f"[OPPORTUNITY SCANNER] Error scanning {url}: {e}")
        return {
            "gaps": ["Unknown"],
            "hook": f"I'd love to chat about growing {business_name}.",
            "score": 0
        }
