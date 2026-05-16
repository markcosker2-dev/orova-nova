import sys
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

# Emails to ignore (junk patterns from JS/CSS files)
JUNK_EMAIL_PATTERNS = ['example', 'png', 'jpg', 'gif', 'sentry', 'webpack', 'wixpress', 'noreply', 'test@']


async def _fetch_page(url: str) -> Optional[str]:
    """Fetch a page's HTML with proper headers."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        logger.warning(f"[ENRICH] Failed to fetch {url}: {e}")
    return None


def _extract_emails(text: str) -> list:
    """Extract valid emails from text, filtering junk."""
    emails = re.findall(EMAIL_REGEX, text)
    return [e for e in emails if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)]


def _extract_phones(text: str) -> list:
    """Extract phone numbers from text."""
    return re.findall(PHONE_REGEX, text)


def _extract_real_website_from_yelp(html: str) -> Optional[str]:
    """Extract the business's actual website from a Yelp business page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Strategy 1: Look for outbound links that Yelp redirects through
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Yelp wraps external links like: /biz_redir?url=https://realbusiness.com
        if "biz_redir" in href and "url=" in href:
            real_url = href.split("url=")[-1].split("&")[0]
            from urllib.parse import unquote
            return unquote(real_url)
    
    # Strategy 2: Look for aria-label "Business website" or similar
    for a in soup.find_all("a", href=True):
        label = a.get("aria-label", "").lower()
        text = a.get_text(strip=True).lower()
        if any(k in label or k in text for k in ["business website", "website", "company site"]):
            href = a["href"]
            if href.startswith("http") and "yelp.com" not in href:
                return href
    
    # Strategy 3: Look for any external link that's not social media
    social = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com", "tiktok.com", "yelp.com"]
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and not any(s in href for s in social):
            return href
    
    return None


def _extract_phone_from_yelp(html: str) -> Optional[str]:
    """Extract phone number from Yelp page."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for phone patterns in the page text
    text = soup.get_text()
    phones = _extract_phones(text)
    if phones:
        return phones[0]
    
    # Look for tel: links
    for a in soup.find_all("a", href=True):
        if a["href"].startswith("tel:"):
            return a["href"].replace("tel:", "").strip()
    
    return None


async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrichment pipeline:
    1. Visit Yelp page → extract phone + real website URL
    2. Visit real website → extract email, phone, owner name
    3. Try Apollo API for decision-maker info
    """
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    logger.info(f"[ENRICH] Starting enrichment for: {lead.get('business', url)}")
    
    real_website = None
    
    # ─── STEP 1: Extract data from Yelp page ──────────────────
    if "yelp.com/biz/" in url:
        logger.info(f"[ENRICH] Step 1: Reading Yelp page...")
        yelp_html = await _fetch_page(url)
        if yelp_html:
            # Get phone from Yelp (they often show it)
            phone = _extract_phone_from_yelp(yelp_html)
            if phone:
                lead["phone"] = phone
                logger.info(f"[ENRICH] → Yelp Phone: {phone}")
            
            # Get real website from Yelp
            real_website = _extract_real_website_from_yelp(yelp_html)
            if real_website:
                logger.info(f"[ENRICH] → Real Website: {real_website}")
    else:
        real_website = url
    
    # ─── STEP 2: Visit real website for email/phone ───────────
    if real_website:
        logger.info(f"[ENRICH] Step 2: Scraping real website: {real_website}")
        site_html = await _fetch_page(real_website)
        if site_html:
            # Extract emails
            if not lead.get("email"):
                emails = _extract_emails(site_html)
                if emails:
                    lead["email"] = emails[0]
                    logger.info(f"[ENRICH] → Email: {lead['email']}")
            
            # Extract phone if we don't have one yet
            if not lead.get("phone"):
                phones = _extract_phones(site_html)
                if phones:
                    lead["phone"] = phones[0]
                    logger.info(f"[ENRICH] → Phone: {lead['phone']}")
            
            # Try to find owner/contact name
            soup = BeautifulSoup(site_html, "html.parser")
            # Look for "About" sections or owner mentions
            about_text = ""
            for sel in ["#about", ".about", "[class*='about']", "[id*='about']", "[class*='team']", "[class*='owner']"]:
                el = soup.select_one(sel)
                if el:
                    about_text = el.get_text(strip=True)[:500]
                    break
            
            if about_text and not lead.get("owner"):
                lead["notes"] = (lead.get("notes", "") + f" | About: {about_text[:200]}").strip(" |")

    # ─── STEP 3: Apollo Enrichment (if key available) ─────────
    apollo_key = os.getenv("APOLLO_API_KEY")
    domain = (real_website or url).split("//")[-1].split("/")[0].replace("www.", "")
    
    if apollo_key and domain and "yelp.com" not in domain:
        logger.info(f"[ENRICH] Step 3: Apollo lookup for {domain}...")
        try:
            async with httpx.AsyncClient(timeout=10.0) as apollo_client:
                payload = {
                    "api_key": apollo_key,
                    "domain": domain,
                    "reveal_personal_emails": True
                }
                apollo_res = await apollo_client.post("https://api.apollo.io/v1/people/match", json=payload)
                if apollo_res.status_code == 200:
                    data = apollo_res.json().get("person", {})
                    if data:
                        lead["owner"] = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
                        lead["email"] = data.get("email") or lead.get("email")
                        lead["notes"] = f"Title: {data.get('title', 'Owner')} | LinkedIn: {data.get('linkedin_url', 'N/A')}"
                        logger.info(f"[ENRICH] → Apollo: {lead.get('owner')} ({lead.get('email')})")
        except Exception as ap_err:
            logger.warning(f"[ENRICH] Apollo failed: {ap_err}")

    logger.info(f"[ENRICH] Complete: {lead.get('business')} | Email: {lead.get('email', 'N/A')} | Phone: {lead.get('phone', 'N/A')}")
    return lead
