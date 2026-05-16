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
            soup = BeautifulSoup(text, "parser.html" if "parser.html" in str(sys.modules) else "html.parser")
            
            # ─── APOLLO.IO ENRICHMENT (Free Tier) ─────────────────────
            apollo_key = os.getenv("APOLLO_API_KEY")
            domain = url.split("//")[-1].split("/")[0].replace("www.", "")
            
            if apollo_key and domain:
                logger.info(f"   -> Querying Apollo for {domain} Decision Makers...")
                try:
                    async with httpx.AsyncClient(timeout=10.0) as apollo_client:
                        apollo_url = "https://api.apollo.io/v1/people/match"
                        payload = {
                            "api_key": apollo_key,
                            "domain": domain,
                            "reveal_personal_emails": True
                        }
                        apollo_res = await apollo_client.post(apollo_url, json=payload)
                        if apollo_res.status_code == 200:
                            data = apollo_res.json().get("person", {})
                            if data:
                                lead["owner"] = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
                                lead["email"] = data.get("email") or lead.get("email")
                                lead["notes"] = f"Title: {data.get('title', 'Owner')} | LinkedIn: {data.get('linkedin_url', 'N/A')}"
                                logger.info(f"   -> Apollo Found: {lead['owner']} ({lead['email']})")
                except Exception as ap_err:
                    logger.warning(f"   -> Apollo Match failed: {ap_err}")

            # ─── REGEX FALLBACK (If Apollo misses) ────────────────────
            if not lead.get("email"):
                emails = re.findall(EMAIL_REGEX, text)
                if emails:
                    valid_emails = [e for e in emails if not any(x in e.lower() for x in ['example', 'png', 'jpg', 'gif', 'sentry'])]
                    if valid_emails:
                        lead["email"] = valid_emails[0]
                        logger.info(f"   -> Regex Found Email: {lead['email']}")

            # 2. Extract Phone (Always try to find)
            phones = re.findall(PHONE_REGEX, text)
            if phones:
                lead["phone"] = phones[0]
                logger.info(f"   -> Found Phone: {lead['phone']}")

    except Exception as e:
        logger.warning(f"[ENRICH LITE] Failed to scrape {url}: {e}")

    return lead
