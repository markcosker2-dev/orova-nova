"""
Firecrawl Bridge - Route all web scraping through Firecrawl API
Prevents 403 blocks from luxury domains on Render IPs.
"""

import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class FirecrawlBridge:
    """
    Routes all web scraping through Firecrawl API to avoid IP blocks.
    """

    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.base_url = "https://api.firecrawl.dev/v1"

    async def scrape_url(self, url: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Scrape a URL using Firecrawl API.
        Options can include format, onlyMainContent, etc.
        """
        if not self.api_key:
            return {"status": "error", "message": "Firecrawl API key not configured"}

        if not options:
            options = {"formats": ["markdown"], "onlyMainContent": True}

        payload = {
            "url": url,
            **options
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.base_url}/scrape",
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "content": data.get("data", {}).get("content", ""),
                    "markdown": data.get("data", {}).get("markdown", ""),
                    "metadata": data.get("data", {}).get("metadata", {})
                }
            else:
                return {
                    "status": "error",
                    "message": f"Firecrawl API error: {response.status_code} - {response.text}"
                }

        except Exception as e:
            logger.error(f"Firecrawl scrape failed: {e}")
            return {"status": "error", "message": f"Scrape failed: {str(e)}"}

    async def crawl_website(self, url: str, max_pages: int = 10, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Crawl an entire website using Firecrawl.
        """
        if not self.api_key:
            return {"status": "error", "message": "Firecrawl API key not configured"}

        if not options:
            options = {
                "limit": max_pages,
                "formats": ["markdown"],
                "onlyMainContent": True
            }

        payload = {
            "url": url,
            **options
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.base_url}/crawl",
                json=payload,
                headers=headers,
                timeout=60  # Crawling takes longer
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "pages": data.get("data", []),
                    "total_pages": len(data.get("data", []))
                }
            else:
                return {
                    "status": "error",
                    "message": f"Firecrawl crawl error: {response.status_code} - {response.text}"
                }

        except Exception as e:
            logger.error(f"Firecrawl crawl failed: {e}")
            return {"status": "error", "message": f"Crawl failed: {str(e)}"}

    async def extract_structured_data(self, url: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract structured data from a URL using Firecrawl's LLM extraction.
        """
        if not self.api_key:
            return {"status": "error", "message": "Firecrawl API key not configured"}

        payload = {
            "url": url,
            "formats": ["extract"],
            "extract": {
                "schema": schema
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                f"{self.base_url}/scrape",
                json=payload,
                headers=headers,
                timeout=45
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "success",
                    "extracted_data": data.get("data", {}).get("extract", {})
                }
            else:
                return {
                    "status": "error",
                    "message": f"Firecrawl extraction error: {response.status_code} - {response.text}"
                }

        except Exception as e:
            logger.error(f"Firecrawl extraction failed: {e}")
            return {"status": "error", "message": f"Extraction failed: {str(e)}"}