# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Universal Lead Scraper
Refactored from scraper.py to be industry-agnostic.
Accepts queries from vertical config instead of hardcoded lists.
"""

import os
import time
import re
import requests
import pandas as pd
import logging
from bs4 import BeautifulSoup
from ddgs import DDGS
from Core_Engine.config import load_vertical

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UniversalScraper:
    """Industry-agnostic lead scraper. Driven by vertical config."""

    def __init__(self, vertical_name: str):
        self.vertical = load_vertical(vertical_name)
        self.vertical_name = vertical_name
        self.queries = self.vertical.get("queries", {}).get("search_queries", [])
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        }
        self.leads = []

        if not self.queries:
            logger.warning(f"No search queries found for vertical '{vertical_name}'")

    def discover_websites(self, max_results: int = 5):
        """Phase 1: Discover business websites using DuckDuckGo."""
        logger.info(f"--- Phase 1: Discovering {self.vertical_name} businesses ---")

        with DDGS() as ddgs:
            for query in self.queries:
                logger.info(f"Searching: {query}...")
                try:
                    count = 0
                    results = ddgs.text(query, max_results=max_results)
                    if results:
                        for r in results:
                            url = r.get("href")
                            if url and not any(
                                x in url for x in
                                ["yelp", "yellowpages", "facebook", "instagram",
                                 "linkedin", "pinterest", "reddit", "twitter"]
                            ):
                                if any(l["Website"] == url for l in self.leads):
                                    continue
                                self.leads.append({
                                    "Business Name": "TBD",
                                    "Website": url,
                                    "Instagram": "N/A",
                                    "Decision Maker": "N/A",
                                    "Contact Email": "N/A",
                                    "Phone": "N/A",
                                    "Vertical": self.vertical_name
                                })
                                count += 1
                    logger.info(f"  Query: {query} | Found: {count}")
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"  Search error: {e}")

        logger.info(f"Total leads discovered: {len(self.leads)}")

    @staticmethod
    def format_phone_e164(phone: str) -> str:
        """Format phone to E.164 (e.g., +15551234567)."""
        if not phone or phone == "N/A":
            return "N/A"
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith('1'):
            return f"+{digits}"
        return phone

    def scrape_details(self):
        """Phase 2: Scrape business details from discovered websites."""
        logger.info(f"--- Phase 2: Scraping details for {len(self.leads)} leads ---")

        for i, lead in enumerate(self.leads):
            url = lead["Website"]
            logger.info(f"[{i+1}/{len(self.leads)}] {url}")

            try:
                resp = requests.get(url, headers=self.headers, timeout=15, verify=False)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Business Name
                if lead["Business Name"] == "TBD":
                    title = soup.find("title")
                    lead["Business Name"] = title.text.split("|")[0].strip() if title else "Unknown"

                # Instagram
                for link in soup.find_all("a", href=True):
                    if "instagram.com" in link["href"].lower():
                        lead["Instagram"] = link["href"]
                        break

                # Phone
                phone_tag = soup.find("a", href=re.compile(r"tel:"))
                if phone_tag:
                    phone_raw = phone_tag["href"].replace("tel:", "")
                else:
                    match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', soup.get_text())
                    phone_raw = match.group(0) if match else "N/A"
                lead["Phone"] = self.format_phone_e164(phone_raw)

                # Email
                email_match = re.search(
                    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
                    soup.get_text()
                )
                if email_match:
                    email = email_match.group(0)
                    if not any(x in email for x in ["example.com", "sentry", "wixpress"]):
                        lead["Contact Email"] = email

                # Decision Maker left as N/A (handled by lead_scorer with AI)
                lead["Decision Maker"] = "N/A"

                logger.info(f"  Name: {lead['Business Name']} | Phone: {lead['Phone']}")

                # Incremental save
                if lead["Phone"] != "N/A":
                    self.save_lead(lead)

                time.sleep(1)
            except Exception as e:
                logger.error(f"  Error: {e}")

    def save_lead(self, lead: dict):
        """Save a single lead to DB."""
        from Core_Engine.db_manager import add_lead
        
        # Map scraper keys to DB schema
        lead_data = {
            "business_name": lead.get("Business Name"),
            "phone": lead.get("Phone"),
            "email": lead.get("Contact Email"),
            "website": lead.get("Website"),
            "vertical": self.vertical_name,
            "status": "New",
            "metadata": {
                "instagram": lead.get("Instagram"),
                "decision_maker": lead.get("Decision Maker")
            }
        }
        add_lead(lead_data)


def ingest_webhook_lead(data: dict):
    """
    Entry point for Meta Ads / External Webhooks.
    Called by OpenClaw (main.py).
    Expected data: { "name": "...", "phone": "...", "email": "...", "vertical": "..." }
    """
    from Core_Engine.db_manager import add_lead
    
    vertical = data.get("vertical", "Unknown")
    # Clean/Format phone here if needed
    
    lead_data = {
        "business_name": data.get("name", "Unknown Lead"),
        "phone": data.get("phone"),
        "email": data.get("email"),
        "vertical": vertical,
        "status": "Qualified", # Webhook leads are high intent
        "metadata": {
            "source": "Meta Ads Webhook",
            "ad_id": data.get("ad_id")
        }
    }
    
    lead_id = add_lead(lead_data)
    logger.info(f"Webhook Lead Ingested: ID {lead_id}")
    return lead_id


def run_scraper(vertical: str, max_results: int = 8):
    """CLI entry point."""
    scraper = UniversalScraper(vertical)
    scraper.discover_websites(max_results=max_results)
    scraper.scrape_details()
    # Results are saved incrementally to DB during scrape_details
    return scraper.leads


if __name__ == "__main__":
    import sys
    # Initialize DB if running standalone
    from Core_Engine.db_manager import init_db
    init_db()
    
    vertical = sys.argv[1] if len(sys.argv) > 1 else "Automotive"
    print(f"\n🔍 OROVA Universal Scraper — Vertical: {vertical}\n")
    run_scraper(vertical)
