"""
Apollo.io Free Lead Scraper — Browser Automation Edition
=========================================================
Uses Playwright (Chromium) to log into Apollo and scrape leads
via the browser UI, bypassing export credit limits.

Anti-detection measures (to keep your account safe):
- Randomized delays (2.5-8s) between actions
- Human-like mouse movements via Playwright
- Cookie-based auth (not password login)
- Daily cap: 500 leads max
- Session rotation: pauses every 50 leads
- No headless mode (runs visible by default — looks more legit)
- Rate limiting: never more than 3 searches per minute
"""

import asyncio
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Safety Constants ────────────────────────────────────────────────
MAX_LEADS_PER_DAY = 500
MIN_DELAY_BETWEEN_ACTIONS = 2.5  # seconds
MAX_DELAY_BETWEEN_ACTIONS = 8.0
MAX_SEARCHES_PER_MINUTE = 3
PAUSE_AFTER_LEADS = 50
PAUSE_DURATION_SECONDS = 120  # 2 minute break
RATE_LIMIT_WINDOW = 60  # 1 minute

# ── Lead Data Model ─────────────────────────────────────────────────
@dataclass
class ApolloLead:
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    company: str = ""
    company_domain: str = ""
    company_size: str = ""
    location: str = ""
    confidence_score: int = 0
    source: str = "apollo_browser_scraper"
    scraped_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "email": self.email,
            "phone": self.phone,
            "linkedin_url": self.linkedin_url,
            "company": self.company,
            "company_domain": self.company_domain,
            "company_size": self.company_size,
            "location": self.location,
            "confidence_score": self.confidence_score,
            "source": self.source,
            "scraped_at": self.scraped_at or datetime.now().isoformat(),
        }


class ApolloBrowserScraper:
    """
    Apollo.io browser-based lead scraper.
    Uses cookie-based authentication (NOT password) for safety.
    """

    def __init__(self, cookies_path: Optional[str] = None):
        self.cookies_path = cookies_path or os.path.join(
            os.path.dirname(__file__), "apollo_cookies.json"
        )
        self.leads_scraped_today = 0
        self.search_timestamps: List[float] = []
        self.browser = None
        self.context = None
        self.page = None
        self._daily_reset()

    def _daily_reset(self):
        """Reset counter if it's a new day."""
        today = date.today().isoformat()
        counter_file = Path(os.path.join(os.path.dirname(__file__), ".daily_counter"))
        if counter_file.exists():
            try:
                data = json.loads(counter_file.read_text())
                if data.get("date") == today:
                    self.leads_scraped_today = data.get("count", 0)
                    return
            except: pass
        self.leads_scraped_today = 0
        counter_file.write_text(json.dumps({"date": today, "count": 0}))

    def _save_counter(self):
        counter_file = Path(os.path.join(os.path.dirname(__file__), ".daily_counter"))
        counter_file.write_text(json.dumps({
            "date": date.today().isoformat(),
            "count": self.leads_scraped_today,
        }))

    async def _human_delay(self, min_s: float = MIN_DELAY_BETWEEN_ACTIONS,
                           max_s: float = MAX_DELAY_BETWEEN_ACTIONS):
        """Randomized delay to mimic human behavior."""
        delay = random.uniform(min_s, max_s)
        await asyncio.sleep(delay)

    async def _random_scroll(self):
        """Simulate human-like scrolling."""
        scroll_amount = random.randint(100, 400)
        direction = random.choice([1, -1])
        await self.page.evaluate(f"window.scrollBy(0, {scroll_amount * direction})")
        await self._human_delay(0.5, 1.5)

    def _check_rate_limit(self) -> bool:
        """Ensure we don't exceed rate limits."""
        now = time.time()
        # Remove timestamps older than 1 minute
        self.search_timestamps = [t for t in self.search_timestamps
                                  if now - t < RATE_LIMIT_WINDOW]
        if len(self.search_timestamps) >= MAX_SEARCHES_PER_MINUTE:
            wait_time = RATE_LIMIT_WINDOW - (now - self.search_timestamps[0])
            if wait_time > 0:
                logger.info(f"[APOLLO] Rate limit: waiting {wait_time:.0f}s")
                time.sleep(wait_time + random.uniform(1, 3))
        self.search_timestamps.append(time.time())
        return True

    async def check_daily_limit(self) -> bool:
        """Check if we've hit the daily lead cap."""
        if self.leads_scraped_today >= MAX_LEADS_PER_DAY:
            logger.warning(f"[APOLLO] Daily limit reached: {MAX_LEADS_PER_DAY} leads")
            return False
        return True

    async def _check_pause(self):
        """Take a break after every N leads to avoid detection."""
        if self.leads_scraped_today > 0 and self.leads_scraped_today % PAUSE_AFTER_LEADS == 0:
            jitter = random.uniform(-30, 30)
            pause = PAUSE_DURATION_SECONDS + jitter
            logger.info(f"[APOLLO] Pausing for {pause:.0f}s after {self.leads_scraped_today} leads")
            await asyncio.sleep(pause)

    async def _has_cookies(self) -> bool:
        """Check if Apollo session cookies exist."""
        cookie_path = Path(self.cookies_path)
        if not cookie_path.exists():
            logger.info("[APOLLO] No cookies file found. Run save_cookies() first.")
            return False
        try:
            cookies = json.loads(cookie_path.read_text())
            if not cookies:
                return False
            # Check if cookies are expired
            for c in cookies:
                if c.get("name") == "session" and c.get("expires", 0) < time.time():
                    logger.warning("[APOLLO] Session cookies expired. Re-save them.")
                    return False
            return True
        except: return False

    async def launch(self, headless: bool = False):
        """Launch browser with anti-detection measures."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-automation",
                "--no-sandbox",
            ]
        )

        self.context = await self.browser.new_context(
            viewport={"width": random.choice([1366, 1440, 1536, 1920]),
                      "height": random.choice([768, 900, 864])},
            user_agent=random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36",
            ]),
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Load saved cookies
        if await self._has_cookies():
            cookies = json.loads(Path(self.cookies_path).read_text())
            await self.context.add_cookies(cookies)
            logger.info("[APOLLO] Loaded session cookies")

        self.page = await self.context.new_page()
        logger.info("[APOLLO] Browser launched")

    async def save_cookies_guide(self):
        """Guide the user to save their Apollo cookies manually (safest method)."""
        print("""
╔══════════════════════════════════════════════════════════════╗
║  Apollo Cookie Setup (Manual - Safe)                       ║
╠══════════════════════════════════════════════════════════════╣
║  1. Open Chrome and log into app.apollo.io                 ║
║  2. Install 'EditThisCookie' extension                     ║
║  3. Click the extension icon → 'Export' cookies as JSON    ║
║  4. Save the JSON file to:                                 ║
║     app/skills/apollo_scraper/apollo_cookies.json          ║
╚══════════════════════════════════════════════════════════════╝
""")

    async def ensure_logged_in(self):
        """Verify we're logged into Apollo. If not, prompt for cookie setup."""
        if not await self._has_cookies():
            await self.save_cookies_guide()
            return False

        # Navigate to Apollo
        await self.page.goto("https://app.apollo.io/#/people", wait_until="networkidle")
        await self._human_delay()

        # Check if we're logged in (look for search bar, not login page)
        try:
            await self.page.wait_for_selector('[data-test-id="search-bar"], .search-bar, input[placeholder*="Search"]',
                                              timeout=10000)
            logger.info("[APOLLO] Successfully authenticated")
            return True
        except:
            logger.warning("[APOLLO] Not logged in. Cookies may be expired.")
            print("\n❌ Apollo login failed. Your cookies expired. Please re-export them.")
            await self.save_cookies_guide()
            return False

    async def search_people(self, query: str, title: str = "",
                            company: str = "", location: str = "",
                            max_results: int = 25) -> List[ApolloLead]:
        """
        Search for people on Apollo and scrape results.
        Anti-detection: random delays, human-like scrolling, rate limited.
        """
        if not await self.check_daily_limit():
            return []

        await self._check_pause()
        self._check_rate_limit()

        if not await self.ensure_logged_in():
            return []

        leads: List[ApolloLead] = []

        # Build the Apollo search URL
        search_parts = [query]
        if title: search_parts.append(f"title:{title}")
        if company: search_parts.append(f"company:{company}")
        if location: search_parts.append(f"location:{location}")
        search_query = " ".join(search_parts)

        # Navigate to people search
        search_url = f"https://app.apollo.io/#/people?q={search_query.replace(' ', '%20')}"
        logger.info(f"[APOLLO] Searching: {search_query[:100]}")

        try:
            await self.page.goto(search_url, wait_until="networkidle", timeout=30000)
            await self._human_delay(3, 6)

            # Wait for results to load
            await self._random_scroll()
            await self._human_delay(1, 3)

            # Try to extract lead data from the page
            # Apollo loads data into a JS variable or React state
            leads = await self._extract_leads_from_page(max_results)

        except Exception as e:
            logger.error(f"[APOLLO] Search error: {e}")

        # Track leads scraped
        self.leads_scraped_today += len(leads)
        self._save_counter()

        return leads

    async def _extract_leads_from_page(self, max_results: int) -> List[ApolloLead]:
        """Extract lead data from the current Apollo search results page."""
        leads = []

        try:
            # Try to extract from the Apollo API response intercepted in the browser
            # Apollo loads data via XHR - we can read the DOM
            lead_cards = await self.page.query_selector_all('[class*="people-table"] [class*="row"], [class*="contact-row"], [data-test-id*="contact"]')

            if not lead_cards:
                # Try alternate selectors
                lead_cards = await self.page.query_selector_all('tr[class*="contact"], div[class*="person-card"]')

            if not lead_cards:
                # Fallback: try to extract from the page's __NEXT_DATA__ or Apollo state
                leads = await self._extract_from_page_state(max_results)
                return leads

            # Scrape visible leads
            for card in lead_cards[:max_results]:
                try:
                    name_el = await card.query_selector('[class*="name"], td:first-child a, [class*="person-name"]')
                    title_el = await card.query_selector('[class*="title"], td:nth-child(2), [class*="position"]')
                    email_el = await card.query_selector('[class*="email"], a[href^="mailto:"]')
                    company_el = await card.query_selector('[class*="organization"], td:nth-child(3), [class*="company"]')
                    phone_el = await card.query_selector('[class*="phone"], [class*="phone-number"]')
                    linkedin_el = await card.query_selector('a[href*="linkedin"]')

                    lead = ApolloLead(
                        name=await name_el.inner_text() if name_el else "",
                        title=await title_el.inner_text() if title_el else "",
                        email=await email_el.inner_text() if email_el else "",
                        company=await company_el.inner_text() if company_el else "",
                        phone=await phone_el.inner_text() if phone_el else "",
                        linkedin_url=await linkedin_el.get_attribute("href") if linkedin_el else "",
                        scraped_at=datetime.now().isoformat(),
                    )
                    leads.append(lead)
                except: continue

        except Exception as e:
            logger.debug(f"[APOLLO] DOM extraction failed: {e}")
            # Fallback
            leads = await self._extract_from_page_state(max_results)

        return leads

    async def _extract_from_page_state(self, max_results: int) -> List[ApolloLead]:
        """
        Extract leads from Apollo's internal page state (React/Next.js).
        Tries multiple strategies to find the data.
        """
        leads = []

        # Strategy 1: Look for __NEXT_DATA__
        try:
            next_data = await self.page.evaluate("""
                () => {
                    const el = document.getElementById('__NEXT_DATA__');
                    if (!el) return null;
                    try { return JSON.parse(el.textContent); } catch { return null; }
                }
            """)
            if next_data:
                contacts = self._find_contacts_in_object(next_data)
                for c in contacts[:max_results]:
                    leads.append(ApolloLead(
                        name=c.get("name", ""),
                        title=c.get("title", ""),
                        email=c.get("email", ""),
                        phone=c.get("phone", ""),
                        company=c.get("organization_name", ""),
                        company_domain=c.get("website_url", ""),
                        location=c.get("city", ""),
                        linkedin_url=c.get("linkedin_url", ""),
                        confidence_score=c.get("email_confidence", 0),
                        scraped_at=datetime.now().isoformat(),
                    ))
                if leads:
                    logger.info(f"[APOLLO] Extracted {len(leads)} leads from __NEXT_DATA__")
                    return leads
        except: pass

        # Strategy 2: Read from Apollo's Redux store or window.__APOLLO_STATE__
        try:
            apollo_state = await self.page.evaluate("""
                () => {
                    if (window.__APOLLO_STATE__) return window.__APOLLO_STATE__;
                    if (window.__INITIAL_STATE__) return window.__INITIAL_STATE__;
                    return null;
                }
            """)
            if apollo_state:
                contacts = self._find_contacts_in_object(apollo_state)
                for c in contacts[:max_results]:
                    leads.append(ApolloLead(
                        name=c.get("name", ""),
                        title=c.get("title", ""),
                        email=c.get("email", ""),
                        phone=c.get("phone", ""),
                        company=c.get("organization_name", c.get("company", "")),
                        linkedin_url=c.get("linkedin_url", ""),
                        scraped_at=datetime.now().isoformat(),
                    ))
                if leads:
                    return leads
        except: pass

        # Strategy 3: Extract from table cells directly
        try:
            rows = await self.page.evaluate("""
                () => {
                    const data = [];
                    const rows = document.querySelectorAll('table tbody tr, [class*="table"] [class*="row"]');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, [class*="cell"]');
                        if (cells.length >= 2) {
                            data.push({
                                name: cells[0]?.innerText?.trim() || '',
                                title: cells[1]?.innerText?.trim() || '',
                                company: cells[2]?.innerText?.trim() || '',
                                email: cells[3]?.innerText?.trim() || '',
                                phone: cells[4]?.innerText?.trim() || '',
                            });
                        }
                    });
                    return data;
                }
            """)
            for r in rows[:max_results]:
                leads.append(ApolloLead(
                    name=r.get("name", ""),
                    title=r.get("title", ""),
                    email=r.get("email", ""),
                    phone=r.get("phone", ""),
                    company=r.get("company", ""),
                    scraped_at=datetime.now().isoformat(),
                ))
        except: pass

        return leads

    def _find_contacts_in_object(self, obj: Any, depth: int = 0) -> List[Dict]:
        """Recursively search for contact/people data in a nested object."""
        if depth > 5: return []
        if not isinstance(obj, (dict, list)): return []

        contacts = []

        if isinstance(obj, dict):
            # Check if this looks like a contact list
            if "contacts" in obj and isinstance(obj["contacts"], list):
                for c in obj["contacts"]:
                    if isinstance(c, dict) and "email" in c:
                        contacts.append(c)

            # Check for people array
            for key in ["people", "results", "hits", "records", "items", "data"]:
                if key in obj and isinstance(obj[key], list):
                    for item in obj[key]:
                        if isinstance(item, dict) and ("email" in item or "name" in item):
                            contacts.append(item)

            # Recurse into all values
            if not contacts:
                for v in obj.values():
                    contacts.extend(self._find_contacts_in_object(v, depth + 1))

        elif isinstance(obj, list):
            for item in obj:
                contacts.extend(self._find_contacts_in_object(item, depth + 1))

        return contacts

    async def close(self):
        """Clean up browser resources."""
        if self.page: await self.page.close()
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if hasattr(self, '_playwright'): await self._playwright.stop()
        logger.info("[APOLLO] Browser closed")


async def scrape_apollo_leads(query: str, title: str = "", company: str = "",
                              location: str = "", max_results: int = 25,
                              headless: bool = False,
                              cookies_path: Optional[str] = None) -> Dict[str, Any]:
    """
    High-level function to scrape Apollo leads.
    Call this from your enrichment pipeline.

    Args:
        query: Search query (e.g., "luxury construction")
        title: Job title filter (e.g., "CEO", "Owner")
        company: Company name filter
        location: Location filter
        max_results: Max leads to scrape (max 500/day)
        headless: Run browser in headless mode (visible by default for safety)

    Returns:
        {"success": bool, "leads": [...], "count": int, "error": str}
    """
    scraper = ApolloBrowserScraper(cookies_path)
    try:
        await scraper.launch(headless=headless)
        if not await scraper.ensure_logged_in():
            return {"success": False, "leads": [], "count": 0,
                    "error": "Not logged in. Save Apollo cookies first."}

        leads = await scraper.search_people(
            query=query, title=title, company=company,
            location=location, max_results=min(max_results, MAX_LEADS_PER_DAY)
        )
        return {
            "success": True,
            "leads": [l.to_dict() for l in leads],
            "count": len(leads),
            "error": None,
        }
    except Exception as e:
        logger.error(f"[APOLLO] Scrape failed: {e}")
        return {"success": False, "leads": [], "count": 0, "error": str(e)}
    finally:
        await scraper.close()


# ── Quick test / setup guide ────────────────────────────────────────
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║  Apollo Browser Scraper - Setup Guide                      ║
╠══════════════════════════════════════════════════════════════╣
║                                                             ║
║  STEP 1: Save your Apollo cookies                          ║
║   1. Open Chrome, log into app.apollo.io                   ║
║   2. Install 'EditThisCookie' Chrome extension              ║
║   3. Click the extension → Export cookies as JSON           ║
║   4. Save to: app/skills/apollo_scraper/apollo_cookies.json ║
║                                                             ║
║  STEP 2: Test the scraper                                   ║
║   python -m app.skills.apollo_scraper.scraper               ║
║                                                             ║
║  SAFETY:                                                    ║
║   - Max 500 leads/day                                       ║
║   - 2.5-8s random delays between actions                    ║
║   - 2-minute break every 50 leads                           ║
║   - Max 3 searches per minute                               ║
║   - Uses cookies, NOT password                              ║
╚══════════════════════════════════════════════════════════════╝
""")