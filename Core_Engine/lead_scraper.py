"""
Core_Engine/lead_scraper.py
Fixed version — real regex-based contact extraction instead of hardcoded placeholder.
"""

import re
import logging
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("nova.scraper")

# Common headers so sites don't block us
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Regex patterns
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
# US/CA phone: covers (555) 123-4567, 555-123-4567, +1-555-123-4567 etc.
PHONE_RE = re.compile(
    r"(\+?1[\s.\-]?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})"
)
# Throw away emails that are obviously not contacts
EMAIL_BLACKLIST = {
    "example.com", "domain.com", "email.com", "yoursite.com",
    "sentry.io", "wixpress.com", "squarespace.com", "shopify.com",
}

# Contact page hints — we'll try these paths if main page is thin
CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/team"]


class UniversalScraper:
    """Discovers leads via DuckDuckGo and extracts real contact info from websites."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    def discover_leads(self, query: str, max_results: int = 10):
        """
        Search DuckDuckGo and return a list of result dicts.
        Each dict has: title, href, body
        """
        logger.info(f"[SCRAPER] Searching: '{query}' (max={max_results})")
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            logger.info(f"[SCRAPER] Found {len(results)} results")
            return results
        except Exception as e:
            logger.error(f"[SCRAPER] Search failed: {e}")
            return []

    def scrape_contact_info(self, url: str) -> dict:
        """
        Visit a URL (and optionally its /contact page) and extract:
        - email
        - phone
        - contact_name (best-effort)

        Returns a dict with these keys (values may be None if not found).
        """
        if not url or not url.startswith("http"):
            return {"email": None, "phone": None, "contact_name": None}

        logger.info(f"[SCRAPER] Scraping: {url}")

        # Try the main page first, then contact sub-pages
        pages_to_try = [url] + [
            url.rstrip("/") + path for path in CONTACT_PATHS
        ]

        all_emails = []
        all_phones = []

        for page_url in pages_to_try[:3]:  # cap at 3 pages per domain
            try:
                resp = requests.get(
                    page_url, timeout=10, headers=HEADERS,
                    allow_redirects=True
                )
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Strip script/style noise
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()

                # Check mailto: links first — most reliable source
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("mailto:"):
                        email = href.replace("mailto:", "").split("?")[0].strip()
                        if email and "@" in email:
                            all_emails.append(email)
                    if href.startswith("tel:"):
                        phone = re.sub(r"[^\d+]", "", href.replace("tel:", ""))
                        if len(phone) >= 10:
                            all_phones.append(phone)

                text = soup.get_text(separator=" ", strip=True)

                # Email regex across full text
                found_emails = EMAIL_RE.findall(text)
                all_emails.extend(found_emails)

                # Phone regex
                phone_matches = PHONE_RE.findall(text)
                for match in phone_matches:
                    raw = "".join(match).strip()
                    digits = re.sub(r"\D", "", raw)
                    if len(digits) >= 10:
                        all_phones.append(raw.strip())

                if all_emails:
                    break  # Good enough, don't scrape more pages

            except requests.exceptions.RequestException as e:
                logger.debug(f"[SCRAPER] Failed to fetch {page_url}: {e}")
                continue

        # Clean and de-duplicate
        clean_email = self._best_email(all_emails)
        clean_phone = self._best_phone(all_phones)

        logger.info(
            f"[SCRAPER] {url} → email={clean_email} phone={clean_phone}"
        )
        return {
            "email": clean_email,
            "phone": clean_phone,
            "contact_name": None,  # Would need ML/NER for reliable name extraction
        }

    def _best_email(self, emails: list) -> str | None:
        """Pick the best email from a list — prefer info@/contact@, filter junk."""
        seen = set()
        clean = []
        for e in emails:
            e = e.lower().strip()
            domain = e.split("@")[-1]
            if domain in EMAIL_BLACKLIST:
                continue
            # Skip image files falsely matched
            if any(e.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg", ".webp"]):
                continue
            if e not in seen:
                seen.add(e)
                clean.append(e)

        if not clean:
            return None

        # Prefer info@, contact@, hello@ as primary business contacts
        priority = ["info@", "contact@", "hello@", "sales@", "admin@"]
        for prefix in priority:
            for e in clean:
                if e.startswith(prefix):
                    return e

        return clean[0]

    def _best_phone(self, phones: list) -> str | None:
        """Pick the best phone number — longest (most digits) wins."""
        if not phones:
            return None
        seen = set()
        clean = []
        for p in phones:
            digits = re.sub(r"\D", "", p)
            if len(digits) >= 10 and digits not in seen:
                seen.add(digits)
                clean.append(p.strip())
        if not clean:
            return None
        # Sort by digit count descending (more complete number first)
        clean.sort(key=lambda x: len(re.sub(r"\D", "", x)), reverse=True)
        return clean[0]
