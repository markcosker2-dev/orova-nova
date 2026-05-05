import os
import logging
import asyncio
import json
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── EXTRACTION SCHEMA ───────────────────────────────────────────────
LEAD_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "business_name": {
            "type": "string",
            "description": "The official name of the business"
        },
        "owner_name": {
            "type": "string",
            "description": "Full name of the Owner, CEO, Founder, or Principal. Leave null if not explicitly found."
        },
        "owner_role": {
            "type": "string",
            "description": "The exact title held (e.g., CEO, Founder, Principal)."
        },
        "personal_email": {
            "type": "string",
            "description": "A personal-looking email address (e.g., john@domain.com). Strictly exclude 'info@', 'contact@', or 'support@'."
        },
        "direct_phone": {
            "type": "string",
            "description": "Direct or mobile phone number. Do not include 1-800 numbers if a local number is available."
        },
        "is_verified_mobile": {
            "type": "boolean",
            "description": "Set to true ONLY if the phone appears in a 'Contact the Owner' context or is explicitly labeled as a mobile/cell number."
        },
        "confidence_score": {
            "type": "integer",
            "description": "Score from 1-10 on how likely this is a high-ticket luxury brand."
        }
    },
    "required": ["business_name"]
}

# ─── CORE SDK WRAPPERS ───────────────────────────────────────────────

async def sgai_search_and_extract(query: str, count: int = 3) -> dict:
    """
    Uses ScrapeGraphAI Cloud SDK to search the web and extract structured JSON directly.
    """
    logger.info(f"[SMART SCRAPER] Initiating SGAI Search: {query}")
    
    # Check for API Key
    if not os.getenv("SGAI_API_KEY"):
        logger.error("[SMART SCRAPER] SGAI_API_KEY is not set. Returning error.")
        return {"error": "SGAI_API_KEY not configured in environment."}

    try:
        from scrapegraph_py import AsyncScrapeGraphAI
        
        async with AsyncScrapeGraphAI() as sgai:
            res = await sgai.search(
                query=query,
                num_results=count,
                prompt="Find the Owner, CEO, or Principal of this business. Extract their full name, personal-looking email, and any direct or mobile phone numbers. Flag the phone as 'Verified_Mobile' if it appears in a 'Contact the Owner' context. Disqualify generic 1-800 or info@ contact points.",
                schema=LEAD_EXTRACTION_SCHEMA
            )
            
            if res.status == "success":
                logger.info("[SMART SCRAPER] Search & Extract SUCCESS")
                return {"status": "success", "data": res.data}
            else:
                logger.warning(f"[SMART SCRAPER] API Error: {res.error}")
                return {"status": "error", "error": res.error}
                
    except ImportError:
        logger.error("[SMART SCRAPER] scrapegraph-py not installed.")
        return {"error": "scrapegraph-py SDK not installed."}
    except Exception as e:
        logger.error(f"[SMART SCRAPER] Exception: {e}")
        return {"error": str(e)}

async def sgai_deep_extract(url: str) -> dict:
    """
    Uses ScrapeGraphAI Cloud SDK to perform a deep extraction on a specific URL.
    """
    logger.info(f"[SMART SCRAPER] Initiating SGAI Extract on: {url}")
    
    if not os.getenv("SGAI_API_KEY"):
        return {"error": "SGAI_API_KEY not configured in environment."}

    try:
        from scrapegraph_py import AsyncScrapeGraphAI
        from scrapegraph_py import FetchConfig
        
        async with AsyncScrapeGraphAI() as sgai:
            res = await sgai.extract(
                prompt="Find the Owner, CEO, or Principal of this business. Extract their full name, personal-looking email, and any direct or mobile phone numbers. Flag the phone as 'Verified_Mobile' if it appears in a 'Contact the Owner' context.",
                url=url,
                schema=LEAD_EXTRACTION_SCHEMA,
                fetch_config=FetchConfig(mode="js", stealth=True, timeout=30000)
            )
            
            if res.status == "success":
                logger.info("[SMART SCRAPER] Deep Extract SUCCESS")
                # Immediately write to Wiki if we have good data
                await _save_to_lead_wiki(url, res.data.get("results", {}).get("json", {}).get("data", {}))
                return {"status": "success", "data": res.data}
            else:
                logger.warning(f"[SMART SCRAPER] API Error: {res.error}")
                return {"status": "error", "error": res.error}
                
    except Exception as e:
        logger.error(f"[SMART SCRAPER] Exception: {e}")
        return {"error": str(e)}

# ─── LEAD WIKI SYSTEM ───────────────────────────────────────────────

async def _save_to_lead_wiki(url: str, extracted_data: dict):
    """
    Saves a verified lead to a persistent Markdown Wiki file.
    """
    if not extracted_data:
        return
        
    b_name = extracted_data.get("business_name")
    if not b_name:
        return
        
    # Only save if we found an owner or email (High Quality)
    if not extracted_data.get("owner_name") and not extracted_data.get("personal_email"):
        return
        
    logger.info(f"[LEAD WIKI] Generating wiki file for {b_name}...")
    
    # Ensure directory exists
    wiki_dir = Path("leads")
    wiki_dir.mkdir(exist_ok=True)
    
    # Create a safe filename
    safe_name = "".join([c for c in b_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    safe_name = safe_name.replace(' ', '_').lower()
    wiki_path = wiki_dir / f"{safe_name}.md"
    
    # Prepare Content
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    md_content = f"# 🏰 OROVA Lead Wiki: {b_name}\n"
    md_content += f"> **Hunted On:** {now}\n> **Source URL:** {url}\n> **Confidence Score:** {extracted_data.get('confidence_score', 'N/A')}/10\n\n"
    
    md_content += "## 👤 The 'Big Fish' (Owner/Decision Maker)\n"
    md_content += f"- **Name:** {extracted_data.get('owner_name', 'Unknown')}\n"
    md_content += f"- **Role:** {extracted_data.get('owner_role', 'Unknown')}\n\n"
    
    md_content += "## 📞 Contact Vectors\n"
    md_content += f"- **Personal Email:** {extracted_data.get('personal_email', 'None found')}\n"
    
    phone = extracted_data.get('direct_phone', 'None found')
    is_mobile = extracted_data.get('is_verified_mobile', False)
    badge = "📱 (Verified Mobile)" if is_mobile else "☎️ (Standard)"
    md_content += f"- **Direct Phone:** {phone} {badge}\n\n"
    
    md_content += "## 📝 Outreach Log & System State\n"
    md_content += "- [ ] Initial Email Sent\n"
    md_content += "- [ ] Retell AI Call Triggered\n"
    md_content += "- [ ] Deal Closed\n\n"
    
    md_content += "---\n*Auto-generated by Antigravity Smart Scraper (ScrapeGraphAI SDK)*\n"
    
    try:
        # If it exists, we append an update. If not, we create new.
        if wiki_path.exists():
            with open(wiki_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n### Update: {now}\nData re-verified via ScrapeGraphAI.\n")
        else:
            with open(wiki_path, "w", encoding="utf-8") as f:
                f.write(md_content)
        logger.info(f"[LEAD WIKI] Saved -> {wiki_path}")
    except Exception as e:
        logger.error(f"[LEAD WIKI] Failed to save {wiki_path}: {e}")
