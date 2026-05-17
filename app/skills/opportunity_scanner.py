import logging
import asyncio
import httpx
import re
import json
from typing import Dict, Any
from bs4 import BeautifulSoup
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

_ai = None
SCAN_FETCH_TIMEOUT_S = 12.0

def _get_scanner_ai() -> UnifiedAIClient:
    global _ai
    if _ai is None:
        _ai = UnifiedAIClient()
    return _ai

def _parse_scanner_json(raw: str, business_name: str) -> dict:
    """Extract and validate the scanner JSON payload from LLM output."""
    # Handle markdown fences and leading/trailing whitespace
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    
    # Attempt to isolate a JSON object if the model added prose
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        clean = match.group(0)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.warning(
            f"[OPPORTUNITY SCANNER] JSON parse failed for {business_name}: {exc}. "
            f"Raw snippet: {raw[:200]!r}"
        )
        return {
            "gaps": ["General digital presence optimization"],
            "hook": f"I'd love to chat about growing {business_name}.",
            "score": 5,
            "_parse_error": True,
        }

    # Enforce type contract
    if not isinstance(data.get("score"), (int, float)):
        try:
            data["score"] = int(data["score"])
        except (TypeError, ValueError):
            data["score"] = 5
    data["score"] = max(0, min(10, int(data["score"])))

    if not isinstance(data.get("gaps"), list):
        data["gaps"] = [str(data.get("gaps", "Unknown"))]

    return data

async def _fetch_page_content(url: str, headers: dict) -> str:
    """Isolated fetch with hard wall-clock timeout."""
    try:
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0),
        ) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                return soup.get_text(separator=" ", strip=True)[:4000]
            return f"HTTP {resp.status_code} — Could not load website."
    except httpx.TimeoutException:
        return "Request timed out fetching website."
    except Exception as e:
        return f"Failed to load website: {e}"

async def scan_opportunity(url: str, business_name: str) -> Dict[str, Any]:
    """
    Visits a business website and identifies 'Opportunity Gaps' 
    (e.g., slow load, no contact form, poor SEO, outdated design).
    Uses httpx instead of Playwright for Render compatibility.
    """
    logger.info(f"[OPPORTUNITY SCANNER] Scanning {business_name} at {url}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    }
    
    try:
        content = await asyncio.wait_for(
            _fetch_page_content(url, headers),
            timeout=SCAN_FETCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        content = f"Website fetch exceeded {SCAN_FETCH_TIMEOUT_S}s wall-clock limit."
    except Exception as e:
        content = f"Error fetching site content: {e}"
        
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
    
    try:
        res_raw = await _get_scanner_ai().extract(prompt)
        data = _parse_scanner_json(res_raw, business_name)
    except Exception as e:
        logger.error(f"[OPPORTUNITY SCANNER] LLM execution or JSON extraction failed: {e}")
        data = {
            "gaps": ["General digital presence optimization"],
            "hook": f"I'd love to chat about growing {business_name}.",
            "score": 5,
            "_exception_raised": True
        }
        
    logger.info(f"[OPPORTUNITY SCANNER] Scan complete for {business_name}. Score: {data.get('score')} parse_error={data.get('_parse_error', False)}")
    return data
