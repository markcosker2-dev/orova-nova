"""
Apollo Free Scraper — SeleniumBase Edition
============================================
Clones the core concepts of FraneCal/apollo_scraper.
Uses SeleniumBase UC (undetected) mode to bypass detection.
Pipes scraped leads directly into Google Sheets via append_to_sheet().

Anti-detection built in via SeleniumBase's stealth mode:
- Hides automation fingerprints automatically
- Randomized human-like delays
- Cookie-based auth (not password)
- 500 leads/day cap
"""

import os
import re
import json
import logging
import time
import random
from datetime import date, datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# ── Safety Constants ────────────────────────────────────────────────
MAX_LEADS_PER_DAY = 500
MIN_DELAY = 3.0
MAX_DELAY = 8.0
PAUSE_AFTER = 50
PAUSE_SECONDS = 120
MAX_RETRIES = 3

# ── Cookie / Config paths ──────────────────────────────────────────
COOKIE_FILE = Path(__file__).parent / "apollo_scraper" / "apollo_cookies.json"
COUNTER_FILE = Path(__file__).parent / "apollo_scraper" / ".daily_counter"


def _daily_reset() -> int:
    """Load today's lead count from disk."""
    today = date.today().isoformat()
    if COUNTER_FILE.exists():
        try:
            data = json.loads(COUNTER_FILE.read_text())
            if data.get("date") == today:
                return data.get("count", 0)
        except: pass
    return 0


def _save_counter(count: int):
    COUNTER_FILE.write_text(json.dumps({"date": date.today().isoformat(), "count": count}))


def _load_cookies() -> Optional[List[Dict]]:
    """Load Apollo session cookies."""
    if not COOKIE_FILE.exists():
        logger.warning("[APOLLO] No cookies file. Export from Chrome via EditThisCookie first.")
        return None
    try:
        return json.loads(COOKIE_FILE.read_text())
    except: return None


def _human_delay():
    """Randomized human-like delay."""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


# ── Lead Extraction Logic ───────────────────────────────────────────

def _extract_leads_from_page_text(page_text: str) -> List[Dict[str, str]]:
    """
    Extract lead data from raw page HTML.
    Multiple fallback strategies for different Apollo UI layouts.
    """
    leads = []

    # Strategy 1: Find contact cards via regex patterns
    # Apollo often embeds JSON data in script tags
    json_patterns = [
        r'"contacts"\s*:\s*\[(.*?)\]',
        r'"people"\s*:\s*\[(.*?)\]',
        r'"results"\s*:\s*\[(.*?)\]',
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, page_text, re.DOTALL)
        for match in matches:
            try:
                # Try to parse each contact object
                objs = re.findall(r'\{[^}]+"email"[^}]+\}', match)
                for obj_str in objs:
                    try:
                        item = json.loads(obj_str)
                        if item.get("email"):
                            leads.append({
                                "name": item.get("name", ""),
                                "title": item.get("title", ""),
                                "email": item.get("email", ""),
                                "phone": "",
                                "company": item.get("organization_name", ""),
                                "domain": item.get("website_url", ""),
                                "linkedin": item.get("linkedin_url", ""),
                            })
                    except: continue
            except: continue
        if leads:
            break

    # Strategy 2: Extract from table rows (view-based scraping)
    if not leads:
        # Look for structured data in HTML
        row_pattern = re.findall(
            r'<tr[^>]*>(.*?)</tr>', page_text, re.DOTALL
        )
        for row in row_pattern[:100]:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) >= 3:
                name = re.sub(r'<[^>]+>', '', cells[0]).strip()
                title = re.sub(r'<[^>]+>', '', cells[1]).strip() if len(cells) > 1 else ""
                email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', row)
                email = email_match.group(0) if email_match else ""
                if name and len(name) > 2:
                    leads.append({
                        "name": name,
                        "title": title,
                        "email": email,
                        "phone": "",
                        "company": "",
                        "domain": "",
                        "linkedin": "",
                    })

    return leads


def _extract_contacts_from_js_vars(page_text: str) -> List[Dict[str, str]]:
    """
    Try to extract from Apollo's internal JS state variables.
    Apollo often stores the full dataset in window.__INITIAL_STATE__ or similar.
    """
    leads = []
    var_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
        r'window\.__APOLLO_STATE__\s*=\s*({.*?});',
        r'window\.__NUXT__\s*=\s*({.*?});',
    ]

    for pattern in var_patterns:
        match = re.search(pattern, page_text, re.DOTALL)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
            # Recursively search for contact/people arrays
            def find_contacts(obj, depth=0):
                if depth > 6 or not isinstance(obj, (dict, list)):
                    return
                if isinstance(obj, dict):
                    for key in ["contacts", "people", "results", "hits", "records"]:
                        if key in obj and isinstance(obj[key], list):
                            for item in obj[key]:
                                if isinstance(item, dict) and item.get("email"):
                                    leads.append({
                                        "name": item.get("name", ""),
                                        "title": item.get("title", ""),
                                        "email": item.get("email", ""),
                                        "phone": item.get("phone", ""),
                                        "company": item.get("organization_name", item.get("company", "")),
                                        "domain": item.get("website_url", item.get("domain", "")),
                                        "linkedin": item.get("linkedin_url", ""),
                                    })
                    if not leads:
                        for v in obj.values():
                            find_contacts(v, depth + 1)
                elif isinstance(obj, list):
                    for item in obj:
                        find_contacts(item, depth + 1)

            find_contacts(data)
        except: continue
        if leads:
            break

    return leads


def _deduplicate_leads(leads: List[Dict]) -> List[Dict]:
    """Remove duplicate leads by email or name+company."""
    seen_emails = set()
    seen_names = set()
    unique = []
    for lead in leads:
        email = lead.get("email", "").lower().strip()
        name = lead.get("name", "").strip()
        company = lead.get("company", "").strip()
        key = email if email else f"{name}|{company}"
        if key and key not in seen_emails and key not in seen_names:
            seen_emails.add(key)
            seen_names.add(key)
            unique.append(lead)
    return unique


async def scrape_apollo_to_sheets(
    query: str,
    title: str = "",
    company: str = "",
    location: str = "",
    max_results: int = 25,
    sheet_name: str = "Leads",
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Scrape Apollo leads using SeleniumBase and pipe them into Google Sheets.

    Args:
        query: Search query (e.g., "luxury construction NYC")
        title: Job title filter (e.g., "CEO", "Owner")
        company: Company name filter
        location: Location filter
        max_results: Max leads to scrape
        sheet_name: Google Sheet tab name for append_to_sheet()
        headless: Run browser headless

    Returns:
        {"success": bool, "count": int, "leads": [...], "sheets_result": ..., "error": str}
    """
    count_today = _daily_reset()
    if count_today >= MAX_LEADS_PER_DAY:
        return {"success": False, "count": 0, "leads": [], "error": f"Daily limit reached ({MAX_LEADS_PER_DAY})"}

    max_results = min(max_results, MAX_LEADS_PER_DAY - count_today)
    cookies = _load_cookies()
    if not cookies:
        return {"success": False, "count": 0, "leads": [],
                "error": "No Apollo cookies. Export from Chrome via EditThisCookie, save to app/skills/apollo_scraper/apollo_cookies.json"}

    # We'll use seleniumbase's UC mode for undetected browsing
    try:
        from seleniumbase import Driver
        from seleniumbase import js_utils

        driver = Driver(uc=True, headless=headless, headless2=headless)

        # Inject cookies before navigating
        driver.get("https://app.apollo.io")
        _human_delay()

        for cookie in cookies:
            try:
                driver.add_cookie({
                    "name": cookie.get("name"),
                    "value": cookie.get("value"),
                    "domain": cookie.get("domain", ".apollo.io"),
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", True),
                })
            except: continue

        _human_delay()

        # Build search URL
        search_parts = [query]
        if title: search_parts.append(f'&title[]={title.replace(" ", "+")}')
        if company: search_parts.append(f'&company[]={company.replace(" ", "+")}')
        if location: search_parts.append(f'&location[]={location.replace(" ", "+")}')
        search_url = f'https://app.apollo.io/#/people?q={search_parts[0].replace(" ", "+")}'

        _human_delay(2, 4)

        leads = []
        page_num = 0

        while len(leads) < max_results and page_num < 10:
            page_num += 1
            logger.info(f"[APOLLO] Scraping page {page_num}...")

            _human_delay()

            # Get page content
            page_html = driver.get_page_source()

            # Extract leads
            page_leads = _extract_leads_from_page_text(page_html)
            if not page_leads:
                page_leads = _extract_contacts_from_js_vars(page_html)

            # Filter new leads
            existing_count = len(leads)
            for lead in page_leads:
                if len(leads) >= max_results:
                    break
                leads.append(lead)

            new_count = len(leads) - existing_count
            logger.info(f"[APOLLO] Found {new_count} leads on page {page_num}")

            # Pause every N leads
            if len(leads) % PAUSE_AFTER == 0 and len(leads) > 0:
                logger.info(f"[APOLLO] Pausing {PAUSE_SECONDS}s after {len(leads)} leads")
                time.sleep(PAUSE_SECONDS + random.uniform(-10, 10))

            # Try to go to next page
            try:
                next_btn = driver.find_element("css selector", '[aria-label="Next"], .next-page, a[rel="next"]')
                if not next_btn or "disabled" in next_btn.get_attribute("class"):
                    break
                next_btn.click()
                _human_delay()
            except: break

        driver.quit()

        # Deduplicate
        leads = _deduplicate_leads(leads)

        # Update daily counter
        new_count = count_today + len(leads)
        _save_counter(new_count)

        # Pipe into Google Sheets
        sheets_result = None
        if leads:
            try:
                from app.skills.sheets_skill import append_to_sheet
                rows = []
                for lead in leads:
                    rows.append([
                        lead.get("name", ""),
                        lead.get("title", ""),
                        lead.get("email", ""),
                        lead.get("phone", ""),
                        lead.get("company", ""),
                        lead.get("domain", ""),
                        lead.get("linkedin", ""),
                        "Scraped",
                        datetime.now().isoformat(),
                    ])
                sheets_result = await append_to_sheet(sheet_name, rows)
                logger.info(f"[APOLLO] Piped {len(rows)} leads to Google Sheet '{sheet_name}'")
            except Exception as e:
                logger.warning(f"[APOLLO] Sheets pipe failed (non-fatal): {e}")
                sheets_result = {"error": str(e)}

        return {
            "success": True,
            "count": len(leads),
            "leads": leads,
            "sheets_result": sheets_result,
            "error": None,
        }

    except ImportError:
        return {"success": False, "count": 0, "leads": [],
                "error": "SeleniumBase not installed. Run: pip install seleniumbase"}
    except Exception as e:
        logger.error(f"[APOLLO] Scraper failed: {e}")
        return {"success": False, "count": 0, "leads": [], "error": str(e)}


async def search_apollo_and_enrich(
    query: str,
    title: str = "",
    company: str = "",
    location: str = "",
    max_results: int = 25,
    sheet_name: str = "Leads",
) -> Dict[str, Any]:
    """
    One-shot: scrape Apollo → enrich → save to sheets.
    This is the main entry point for the pipeline.
    """
    result = await scrape_apollo_to_sheets(
        query=query, title=title, company=company,
        location=location, max_results=max_results,
        sheet_name=sheet_name,
    )

    # If we have leads without email, try enrichment
    if result.get("leads"):
        enriched_count = 0
        for lead in result["leads"]:
            if not lead.get("email") and lead.get("domain"):
                try:
                    from app.skills.lead_enrichment import enrich_lead
                    enriched = await enrich_lead(
                        url=f"https://{lead['domain']}",
                        business_name=lead.get("company", ""),
                    )
                    if enriched.get("email"):
                        lead["email"] = enriched["email"]
                        enriched_count += 1
                except: pass

        if enriched_count > 0:
            logger.info(f"[APOLLO] Enriched {enriched_count} leads with email from website scraping")

    return result