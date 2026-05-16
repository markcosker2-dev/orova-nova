import os
import re
import asyncio
import httpx
import logging
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
PHONE_REGEX = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'

async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight enrichment: visits URL with httpx and extracts email/phone via regex.
    Free Tier Friendly (No Playwright).
    """
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    logger.info(f"[ENRICH LITE] Visiting {url} for contact info...")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return lead
            
            text = resp.text
            soup = BeautifulSoup(text, "html.parser")
            
            # 1. Extract Emails
            emails = re.findall(EMAIL_REGEX, text)
            if emails:
                # Filter out garbage
                valid_emails = [e for e in emails if not any(x in e.lower() for x in ['example', 'png', 'jpg', 'gif', 'sentry'])]
                if valid_emails:
                    lead["email"] = valid_emails[0]
                    logger.info(f"   -> Found Email: {lead['email']}")

            # 2. Extract Phone
            phones = re.findall(PHONE_REGEX, text)
            if phones:
                lead["phone"] = phones[0]
                logger.info(f"   -> Found Phone: {lead['phone']}")

            # 3. Guess Owner/CEO (Simple heuristic)
            # Look for "Owner", "Founder", "CEO" in the text
            if "owner" in text.lower() or "founder" in text.lower():
                # This is a very rough guess - real enrichment usually needs AI
                # We'll keep it empty for now or use the AI client if available
                pass

    except Exception as e:
        logger.warning(f"[ENRICH LITE] Failed to scrape {url}: {e}")

    return lead
