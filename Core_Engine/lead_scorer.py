# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Universal Lead Scorer
CLV-based scoring instead of niche-specific keywords.
Refactored from batch_processor.py.
"""

import os
import time
import re
import json
import logging
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Core_Engine.config import load_vertical, get_scoring_prompt
from Core_Engine.notifications import alert_high_score_lead

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UniversalLeadScorer:
    """Scores leads using CLV-based AI analysis, driven by vertical config."""

    def __init__(self, vertical_name: str, api_key: str = None):
        self.vertical = load_vertical(vertical_name)
        self.vertical_name = vertical_name
        self.scoring_rules = self.vertical.get("scoring_rules", {})
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        }

        # AI Setup (Gemini for scoring)
        self.client = None
        self.model_id = 'gemini-2.5-flash'
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
                logger.info("AI Scorer ready (google.genai)")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

        # DuckDuckGo for owner hunting
        self.ddgs_available = True
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            self.ddgs_available = False

    def find_owner(self, business_name: str) -> str:
        """Hunt for the business owner/founder name via web search."""
        if not self.ddgs_available or not self.client:
            return "N/A"

        logger.info(f"🕵️ Hunting owner of {business_name}...")
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                query = f"Owner Founder CEO {business_name}"
                results = list(ddgs.text(query, max_results=5))
                if not results:
                    return "N/A"

                snippets = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
                prompt = f"""
                Find the name of the Owner, Founder, or CEO from these search results.
                Business: {business_name}

                Search Results:
                {snippets}

                Return ONLY the name (e.g. "John Smith") or "N/A".
                """
                response = self.client.models.generate_content(
                    model=self.model_id, contents=prompt
                )
                name = response.text.strip().replace('"', '').replace("'", "")
                if "N/A" in name or len(name) > 30:
                    return "N/A"
                logger.info(f"  Found: {name}")
                return name
        except Exception as e:
            logger.error(f"  Hunter error: {e}")
            return "N/A"

    def scrape_content(self, url: str) -> str:
        """Scrape and clean text from a website."""
        try:
            resp = requests.get(url, headers=self.headers, timeout=15, verify=False)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                return soup.get_text(separator=" ", strip=True)[:5000]
            return ""
        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return ""

    def score_lead(self, business_name: str, url: str, content: str) -> dict:
        """Score a lead using CLV-based AI analysis with retry."""
        if not content or not self.client:
            return {"qualification_score": 0, "qualification_reason": "No data", "icebreaker": ""}

        prompt = get_scoring_prompt(self.scoring_rules, business_name, url, content)

        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id, contents=prompt
                )
                text = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e):
                    wait = 30
                    match = re.search(r'retry in (\d+\.?\d*)s', str(e))
                    if match:
                        wait = float(match.group(1)) + 1
                    logger.warning(f"Rate limited. Waiting {wait:.0f}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"AI Error: {e}")
                    return {"qualification_score": 0, "qualification_reason": "AI Error", "icebreaker": ""}

        return {"qualification_score": 0, "qualification_reason": "Rate limit", "icebreaker": ""}

    def run_batch_db(self, limit: int = 10):
        """Process 'New' leads from DB and score them."""
        from Core_Engine.db_manager import get_leads_by_status, update_lead_status
        
        leads = get_leads_by_status("New", self.vertical_name)
        if not leads:
            logger.info("No 'New' leads to score.")
            return

        logger.info(f"Scoring {len(leads)} leads from DB...")
        
        for i, lead in enumerate(leads[:limit]):
            lead_id = lead["id"]
            name = lead["business_name"]
            url = lead["website"]
            
            logger.info(f"Analyzing [{i+1}/{len(leads)}]: {name}")
            
            if not url:
                update_lead_status(lead_id, "Dead", "No website found")
                continue

            # Scrape content
            content = self.scrape_content(url)
            
            # AI Score
            analysis = self.score_lead(name, url, content)
            
            score = analysis.get("qualification_score", 0)
            status = "Qualified" if score >= 7 else "Unqualified"

            # Alert for high-score leads
            alert_high_score_lead(name, score, self.vertical_name)
            
            metadata = json.loads(lead["metadata"]) if lead["metadata"] else {}
            metadata.update({
                "market_tier": analysis.get("market_tier"),
                "primary_service": analysis.get("primary_service"),
                "estimated_clv": analysis.get("estimated_clv"),
                "icebreaker": analysis.get("icebreaker"),
                "qualification_reason": analysis.get("qualification_reason")
            })
            
            # Update DB with raw SQL for metadata complexity or just use helper
            # Since update_lead_status only does status/notes, we need a custom update here
            # Or extend db_manager.update_lead_status to handle everything.
            # For now, let's just update via direct connection or extend db_manager.
            
            self._update_full_lead(lead_id, status, score, metadata)
            time.sleep(1)

    def _update_full_lead(self, lead_id, status, score, metadata):
        import sqlite3
        conn = sqlite3.connect("Client_Data/leads.db") # Hardcoded path for now to match db_manager
        # Actually use db_manager.DB_PATH if possible, but importing it is cleaner
        from Core_Engine.db_manager import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE leads 
            SET status = ?, clv_score = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, score, json.dumps(metadata), lead_id))
        conn.commit()
        conn.close()
        logger.info(f"  -> Scored {score}/10 ({status})")


if __name__ == "__main__":
    import sys
    from Core_Engine.db_manager import init_db
    init_db()
    
    vertical = sys.argv[1] if len(sys.argv) > 1 else "Automotive"
    print(f"\n📊 OROVA Universal Lead Scorer — Vertical: {vertical}\n")
    scorer = UniversalLeadScorer(vertical)
    scorer.run_batch_db()
