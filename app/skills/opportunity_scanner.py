import logging
import asyncio
import httpx
from typing import Dict, Any
from bs4 import BeautifulSoup
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)
ai = UnifiedAIClient()

async def scan_opportunity(url: str, business_name: str) -> Dict[str, Any]:
    """
    Visits a business website and identifies 'Opportunity Gaps' 
    (e.g., slow load, no contact form, poor SEO, outdated design).
    Uses httpx instead of Playwright for Render compatibility.
    """
    logger.info(f"[OPPORTUNITY SCANNER] Scanning {business_name} at {url}...")
    
    try:
        # 1. Scrape the site using httpx (works on Render, no Playwright needed)
        content = ""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            }
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    content = soup.get_text(separator=" ", strip=True)[:4000]
                else:
                    content = f"HTTP {resp.status_code} — Could not load website."
        except Exception as e:
            content = f"Failed to load website: {e}"
        
        # 2. Ask AI to find the 'Gaps'
        prompt = f"""
        Analyze the website content of '{business_name}' and identify 3-5 'Marketing Gaps' or weaknesses.
        Focus on things OROVA (an AI agency) can fix:
        - Lack of AI automation (no chatbot)
        - Poor lead capture (no clear CTA)
        - SEO weaknesses
        - Outdated design
        
        Content:
        {content}
        
        Format your response as a JSON object:
        {{
            "gaps": ["gap 1", "gap 2"],
            "hook": "A one-sentence icebreaker mentioning one of these gaps",
            "score": 1-10 (how much they need help)
        }}
        """
        
        res_raw = await ai.extract(prompt)
        import json
        try:
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
