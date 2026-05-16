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
JUNK_EMAIL_PATTERNS = ['example', 'png', 'jpg', 'gif', 'sentry', 'webpack', 'wixpress', 'noreply', 'test@', 'email@']


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
    emails = re.findall(EMAIL_REGEX, text)
    return [e for e in emails if not any(j in e.lower() for j in JUNK_EMAIL_PATTERNS)]


def _extract_phones(text: str) -> list:
    return re.findall(PHONE_REGEX, text)


def _firecrawl_scrape(url: str) -> Optional[str]:
    """Use Firecrawl to scrape a page (renders JavaScript). Returns markdown."""
    try:
        from firecrawl import FirecrawlApp
        key = os.getenv("FIRECRAWL_API_KEY")
        if not key:
            return None
        app = FirecrawlApp(api_key=key)
        result = app.scrape_url(url, params={'formats': ['markdown']})
        return result.get("markdown", "")
    except Exception as e:
        logger.warning(f"[ENRICH] Firecrawl scrape failed for {url}: {e}")
        return None


def _extract_from_yelp_markdown(markdown: str) -> Dict[str, Any]:
    """Extract phone, website, and business info from Yelp page markdown."""
    data = {"phone": None, "website": None, "address": None}

    # Phone: Look for phone number patterns
    phones = _extract_phones(markdown)
    if phones:
        data["phone"] = phones[0]

    # Website: Look for URLs that aren't yelp/social media
    social = ["yelp.com", "facebook.com", "instagram.com", "twitter.com", "linkedin.com", "youtube.com", "tiktok.com"]
    urls = re.findall(r'https?://[^\s\)\]\"\'<>]+', markdown)
    for u in urls:
        u_clean = u.rstrip('.,;:)')
        if not any(s in u_clean.lower() for s in social):
            data["website"] = u_clean
            break

    # Also try to find website from common Yelp markdown patterns
    # Yelp often shows "Business website" or just the domain
    website_patterns = [
        r'(?:Business website|Website)[:\s]*\[?([^\]\s]+)',
        r'(?:http[s]?://(?:www\.)?[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:/[^\s\)\]]*)?)',
    ]
    if not data["website"]:
        for pattern in website_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE)
            if match:
                url_candidate = match.group(1) if match.lastindex else match.group(0)
                if not any(s in url_candidate.lower() for s in social):
                    data["website"] = url_candidate
                    break

    # Address: Look for state abbreviations near numbers
    addr_match = re.search(r'\d+\s+[A-Za-z\s]+(?:St|Ave|Blvd|Dr|Rd|Way|Ln|Ct|Pl|Pkwy)[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2}\s*\d{5}', markdown)
    if addr_match:
        data["address"] = addr_match.group(0)

    return data


async def enrich_lead_lite(lead: Dict[str, Any]) -> Dict[str, Any]:
    """
    3-step enrichment:
    1. Use Firecrawl to read the Yelp page (renders JS) → phone + real website
    2. Visit real website with httpx → email + about info
    3. Apollo API → decision-maker name + verified email
    """
    url = lead.get("url")
    if not url or not url.startswith("http"):
        return lead

    biz_name = lead.get("business", "Unknown")
    logger.info(f"[ENRICH] Starting enrichment for: {biz_name}")

    # If lead already has phone from the search tier, don't re-scrape unless needed
    if lead.get("phone"):
        logger.info(f"[ENRICH] Lead already has phone: {lead['phone']}. Skipping Yelp deep-scrape.")
        real_website = None # We'll try to find it on the Yelp page still if we need email
    
    real_website = None

    # ─── STEP 1: Firecrawl the Yelp page ──────────────────────
    if "yelp.com/biz/" in url:
        # If we have phone but no email/website, we still need to hit Yelp to find the real website
        if lead.get("phone") and lead.get("email"):
             logger.info("[ENRICH] Lead already fully enriched. Skipping.")
             return lead

        logger.info(f"[ENRICH] Step 1: Firecrawl reading Yelp page...")
        # Use Firecrawl (renders JS, bypasses Yelp's bot wall)
        markdown = await asyncio.get_event_loop().run_in_executor(None, _firecrawl_scrape, url)
        
        if markdown:
            logger.info(f"[TELEMETRY] Firecrawl returned {len(markdown)} chars of markdown.")
            yelp_data = _extract_from_yelp_markdown(markdown)

            if yelp_data["phone"]:
                lead["phone"] = yelp_data["phone"]
                logger.info(f"[ENRICH] → Phone: {lead['phone']}")

            if yelp_data["website"]:
                real_website = yelp_data["website"]
                logger.info(f"[ENRICH] → Website: {real_website}")

            if yelp_data["address"]:
                lead["notes"] = (lead.get("notes", "") + f" | Address: {yelp_data['address']}").strip(" |")
        else:
            logger.warning("[ENRICH] Firecrawl returned nothing for Yelp page")
    else:
        real_website = url

    # ─── STEP 2: Visit real website for email ─────────────────
    if real_website:
        logger.info(f"[ENRICH] Step 2: Scraping real website: {real_website}")
        site_html = await _fetch_page(real_website)
        if site_html:
            if not lead.get("email"):
                emails = _extract_emails(site_html)
                if emails:
                    lead["email"] = emails[0]
                    logger.info(f"[ENRICH] → Email: {lead['email']}")

            if not lead.get("phone"):
                phones = _extract_phones(site_html)
                if phones:
                    lead["phone"] = phones[0]
                    logger.info(f"[ENRICH] → Phone: {lead['phone']}")

            # Try contact page too
            if not lead.get("email"):
                for path in ["/contact", "/contact-us", "/about", "/about-us"]:
                    try:
                        contact_url = real_website.rstrip("/") + path
                        contact_html = await _fetch_page(contact_url)
                        if contact_html:
                            emails = _extract_emails(contact_html)
                            if emails:
                                lead["email"] = emails[0]
                                logger.info(f"[ENRICH] → Email (from {path}): {lead['email']}")
                                break
                            if not lead.get("phone"):
                                phones = _extract_phones(contact_html)
                                if phones:
                                    lead["phone"] = phones[0]
                    except:
                        pass

    # ─── STEP 3: Apollo enrichment ────────────────────────────
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

    logger.info(f"[ENRICH] Done: {biz_name} | Phone: {lead.get('phone', 'N/A')} | Email: {lead.get('email', 'N/A')}")
    return lead
