"""
Smart Scraper — FREE + Reliable Lead Extraction
================================================
Uses ScrapeGraphAI (open-source) with Groq as the LLM backend.

Pipeline:
  1. sgai_search_and_extract() — DDG search + AI extraction
  2. sgai_deep_extract() — Deep scrape a single URL
  3. enrich_lead_ai() — Unified enrichment: tries search, then deep extract, then fallback

Cost: $0 (Groq free tier + ScrapeGraphAI open source)

The LLM backend is Groq (free tier: 30K requests/day), which powers the
AI extraction of owner names, emails, and phone numbers from web pages.
"""

import os
import re
import json
import logging
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ─── APOLLO BROWSER SCRAPER (FREE, PRIMARY) ────────────────────────────────
APOLLO_COOKIES_PATH = Path(__file__).parent / "apollo_scraper" / "apollo_cookies.json"

async def apollo_search_people(query: str, max_results: int = 10) -> dict:
    """
    Apollo browser scraper — FREE, uses Playwright to read Apollo's free tier.
    Returns list of leads with name, title, email, phone, company.
    """
    if not APOLLO_COOKIES_PATH.exists():
        return {"status": "error", "error": "Apollo cookies not set up. Run setup_apollo_cookies.py first."}

    scraper = None
    try:
        from app.skills.apollo_scraper.scraper import ApolloBrowserScraper
        scraper = ApolloBrowserScraper(cookies_path=str(APOLLO_COOKIES_PATH))
        await scraper.launch(headless=True)

        if not await scraper.ensure_logged_in():
            return {"status": "error", "error": "Apollo cookies expired. Run setup_apollo_cookies.py again."}

        leads = await scraper.search_people(query=query, max_results=max_results)

        if leads:
            results = []
            for lead in leads:
                results.append({
                    "name": lead.name,
                    "title": lead.title,
                    "email": lead.email,
                    "phone": lead.phone,
                    "company": lead.company,
                    "location": lead.location,
                })
            return {"status": "success", "data": results}
        return {"status": "error", "error": "No Apollo results found"}
    except ImportError:
        logger.warning("[SMART SCRAPER] Apollo scraper not importable")
        return {"status": "error", "error": "Apollo scraper module not available"}
    except Exception as e:
        logger.error(f"[SMART SCRAPER] Apollo search failed: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if scraper:
            try: await scraper.close()
            except: pass

# ─── EXTRACTION SCHEMA ─────────────────────────────────────────────────────
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

EXTRACTION_PROMPT = (
    "Find the Owner, CEO, or Principal of this business. "
    "Extract their full name, personal-looking email, and any direct or mobile phone numbers. "
    "Flag the phone as 'Verified_Mobile' if it appears in a 'Contact the Owner' context. "
    "Disqualify generic 1-800 or info@ contact points."
)

# ─── GROQ LLM CONFIG (FREE) ───────────────────────────────────────────────
# Uses Groq's free tier: 30K requests/day with Llama 3
# This is the LLM backend for ScrapeGraphAI's AI extraction

SGAI_GRAPH_CONFIG = {
    "llm": {
        "model": "groq/llama3-8b-8192",
        "api_key": os.getenv("GROQ_API_KEY", ""),
    },
    "browser_config": {
        "headless": True,
        "browser_type": "playwright",
    },
    "verbose": False,
}

# ─── CORE FUNCTIONS (FREE) ────────────────────────────────────────────────

async def sgai_search_and_extract(query: str, count: int = 3) -> dict:
    """
    ScrapeGraphAI search + AI extraction.
    Uses Groq (free) as the LLM backend.
    Returns structured dict with business_name, owner_name, email, phone.
    """
    logger.info(f"[SMART SCRAPER] Search: {query}")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        logger.warning("[SMART SCRAPER] GROQ_API_KEY not set — falling back to basic search")
        return await _simple_search_fallback(query, count)

    try:
        from scrapegraphai.graphs import SearchGraph

        graph = SearchGraph(
            prompt=EXTRACTION_PROMPT,
            config={
                "llm": {
                    "model": "groq/llama3-8b-8192",
                    "api_key": groq_key,
                },
                "verbose": False,
            },
        )
        result = graph.run({"query": query, "num_results": count})
        logger.info("[SMART SCRAPER] Search+Extract SUCCESS")
        return {"status": "success", "data": result}
    except ImportError:
        logger.warning("[SMART SCRAPER] scrapegraphai not installed — using fallback")
        return await _simple_search_fallback(query, count)
    except Exception as e:
        logger.error(f"[SMART SCRAPER] Search failed: {e}")
        return {"status": "error", "error": str(e)}


async def sgai_deep_extract(url: str) -> dict:
    """
    ScrapeGraphAI deep extraction on a single URL.
    Uses Groq (free) to extract owner name, email, phone from the page.
    """
    logger.info(f"[SMART SCRAPER] Deep extract: {url}")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        return {"status": "error", "error": "GROQ_API_KEY not set"}

    try:
        from scrapegraphai.graphs import SmartScraperGraph

        graph = SmartScraperGraph(
            prompt=EXTRACTION_PROMPT,
            source=url,
            config={
                "llm": {
                    "model": "groq/llama3-8b-8192",
                    "api_key": groq_key,
                },
                "verbose": False,
            },
        )
        result = graph.run()
        logger.info("[SMART SCRAPER] Deep extract SUCCESS")

        # Save to lead wiki if we got good data
        if isinstance(result, dict):
            await _save_to_lead_wiki(url, result)
        return {"status": "success", "data": result}
    except ImportError:
        logger.warning("[SMART SCRAPER] scrapegraphai not installed — falling back to HTML parse")
        return await _html_scrape_fallback(url)
    except Exception as e:
        logger.error(f"[SMART SCRAPER] Deep extract failed: {e}")
        return {"status": "error", "error": str(e)}


async def enrich_lead_ai(
    business_name: str,
    url: str = "",
    query: str = "",
) -> dict:
    """
    Unified enrichment pipeline — tries multiple methods:
      0. Apollo browser scraper (free, ~75% hit rate — PRIMARY)
      1. ScrapeGraphAI deep extract (AI-powered, free)
      2. ScrapeGraphAI search (AI-powered, free)
      3. HTML scrape fallback (basic)
    Returns: { business_name, owner_name, email, phone, source }
    """
    result = {
        "business_name": business_name,
        "owner_name": None,
        "email": None,
        "phone": None,
        "source": "none",
    }

    # Strategy 0: Apollo browser scraper (free, ~75% hit rate — try first)
    apollo_query = query or business_name
    apollo_result = await apollo_search_people(apollo_query, max_results=3)
    if apollo_result.get("status") == "success" and apollo_result.get("data"):
        # Apollo returns a list of people
        for person in apollo_result["data"]:
            if person.get("email") or person.get("name"):
                result["owner_name"] = person.get("name")
                result["email"] = person.get("email")
                result["phone"] = person.get("phone")
                result["source"] = "apollo_browser"
                score_lead_for_orova(result)
                return result

    # Strategy 1: Deep extract from URL (most reliable)
    if url:
        extracted = await sgai_deep_extract(url)
        if extracted.get("status") == "success" and extracted.get("data"):
            data = extracted["data"]
            if isinstance(data, dict):
                result["owner_name"] = data.get("owner_name")
                result["email"] = data.get("personal_email")
                result["phone"] = data.get("direct_phone")
                result["source"] = "sgai_deep_extract"
                if result["owner_name"] or result["email"]:
                    score_lead_for_orova(result)
                    return result

    # Strategy 2: Search + extract
    search_query = query or f"{business_name} owner email phone"
    extracted = await sgai_search_and_extract(search_query, count=3)
    if extracted.get("status") == "success" and extracted.get("data"):
        data = extracted["data"]
        if isinstance(data, dict):
            result["owner_name"] = result["owner_name"] or data.get("owner_name")
            result["email"] = result["email"] or data.get("personal_email")
            result["phone"] = result["phone"] or data.get("direct_phone")
            result["source"] = "sgai_search"
            if result["owner_name"] or result["email"]:
                score_lead_for_orova(result)
                return result

    # Strategy 3: Basic HTML scrape fallback
    if url:
        html_result = await _html_scrape_fallback(url)
        if html_result.get("status") == "success":
            data = html_result.get("data", {})
            result["owner_name"] = result["owner_name"] or data.get("owner_name")
            result["email"] = result["email"] or data.get("personal_email")
            result["phone"] = result["phone"] or data.get("direct_phone")
            result["source"] = "html_scrape"
            if result["owner_name"] or result["email"]:
                score_lead_for_orova(result)
                return result

    score_lead_for_orova(result)
    return result


# ─── SCORE BEFORE RETURNING ────────────────────────────────────────────────
def enrich_and_score(result: dict) -> dict:
    """Score the enrichment result before returning to Nova."""
    score_lead_for_orova(result)
    return result


# ─── FALLBACK: HTML SCRAPE (NO LLM REQUIRED) ──────────────────────────────

async def _html_scrape_fallback(url: str) -> dict:
    """
    Basic HTML scrape + regex extraction. No LLM needed.
    Scans homepage + /contact + /about pages for email, phone, owner names.
    """
    try:
        import httpx
        from bs4 import BeautifulSoup

        pages_to_check = [url]
        # Try common subpages
        base = url.rstrip("/")
        for path in ["/contact", "/about", "/about-us", "/team"]:
            pages_to_check.append(base + path)

        emails = set()
        phones = set()
        names = set()

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for page_url in pages_to_check:
                try:
                    resp = await client.get(page_url, headers={"User-Agent": "Mozilla/5.0"})
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text(separator=" ")

                    # Extract emails
                    for m in re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text):
                        m = m.lower()
                        if m not in ("info@contact.com", "user@example.com"):
                            emails.add(m)

                    # Extract phones
                    for m in re.findall(r'(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}', text):
                        m = m.strip()
                        if len(m) >= 10:
                            phones.add(m)

                    # Extract plausible names from common patterns
                    for m in re.findall(r'(?:CEO|Owner|Founder|Principal|Director|Manager)\s+(?:named?\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+)', text):
                        if _is_plausible_name(m):
                            names.add(m)

                except Exception:
                    continue

        result = {
            "business_name": url.split("//")[-1].split("/")[0],
            "owner_name": list(names)[0] if names else None,
            "personal_email": list(emails)[0] if emails else None,
            "direct_phone": list(phones)[0] if phones else None,
            "is_verified_mobile": False,
            "confidence_score": 3 if emails else 1,
        }

        if names or emails or phones:
            await _save_to_lead_wiki(url, result)
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"[HTML SCRAPE] Fallback failed: {e}")
        return {"status": "error", "error": str(e)}


async def _simple_search_fallback(query: str, count: int) -> dict:
    """
    DuckDuckGo search fallback when ScrapeGraphAI isn't available.
    Returns raw search results (no AI extraction).
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=count):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error(f"[FALLBACK] DuckDuckGo error: {e}")
        return {"status": "error", "error": str(e)}


# ─── LEAD SCORING & FILTERING ─────────────────────────────────────────────

def score_lead_for_orova(lead: dict) -> dict:
    """
    Score a lead 0-10 for OROVA's luxury/high-ticket targeting.
    Returns lead dict augmented with score and filter_decision.
    """
    score = 5
    reasons = []
    
    # Contact quality
    email = (lead.get("email") or "").lower()
    phone = lead.get("phone") or ""
    name = lead.get("owner_name") or lead.get("name") or ""
    
    has_personal_email = email and not email.startswith(("info@", "contact@", "support@", "hello@", "admin@"))
    has_name = len(name.split()) >= 2
    has_phone = len(phone) >= 10
    
    if has_personal_email:
        score += 2
        reasons.append("personal email")
    elif email:
        score += 0.5
        reasons.append("generic email")
    
    if has_name:
        score += 1.5
        reasons.append("owner name found")
    
    if has_phone:
        score += 1
        reasons.append("phone number")
    
    # Source quality bonus
    source = lead.get("source", "")
    if source == "apollo_browser":
        score += 1
        reasons.append("apollo verified")

    # Email verification status (set by enrichment waterfall)
    email_status = lead.get("email_status", "")
    if email_status == "verified":
        score += 1
        reasons.append("email verified")
    elif email_status == "guessed":
        score -= 1
        reasons.append("email guessed")

    if lead.get("owner_title"):
        score += 0.5
        reasons.append("title known")
    
    score = min(10, max(0, score))
    
    # Filter decision
    if score >= 7 and (has_personal_email or has_name):
        decision = "PASS"
    elif score >= 5 and email:
        decision = "PASS"
    elif score >= 4:
        decision = "BORDERLINE"
    else:
        decision = "REJECT"
    
    lead["orova_score"] = round(score, 1)
    lead["score_reasons"] = reasons
    lead["filter_decision"] = decision
    return lead


def score_and_filter_leads(leads: list, min_score: float = 4.0) -> list:
    """
    Score a list of leads and filter out low-quality ones.
    Returns leads sorted by score (highest first), only those above min_score.
    """
    scored = [score_lead_for_orova(lead) for lead in leads]
    filtered = [lead for lead in scored if lead.get("orova_score", 0) >= min_score]
    filtered.sort(key=lambda x: x.get("orova_score", 0), reverse=True)
    return filtered


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _is_plausible_name(text: str) -> bool:
    if not text or len(text) < 4 or len(text) > 50:
        return False
    parts = text.split()
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Za-z'\-]+$", p) for p in parts):
        return False
    if not parts[0][0].isupper():
        return False
    return True


async def _save_to_lead_wiki(url: str, extracted_data: dict):
    """Save a verified lead to a persistent Markdown Wiki file."""
    if not extracted_data:
        return

    b_name = extracted_data.get("business_name")
    if not b_name:
        return

    if not extracted_data.get("owner_name") and not extracted_data.get("personal_email"):
        return

    logger.info(f"[LEAD WIKI] Generating wiki for {b_name}...")
    # Lead wikis live in the Obsidian vault (see CLAUDE.md / ADR-0001)
    wiki_dir = Path(os.getenv("LEAD_WIKI_DIR", "vault/30-leads"))
    wiki_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join([c for c in b_name if c.isalpha() or c.isdigit() or c==' ']).rstrip()
    safe_name = safe_name.replace(' ', '_').lower()
    wiki_path = wiki_dir / f"{safe_name}.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Frontmatter matches the vault convention (vault/_templates/lead.md)
    md_content = (
        "---\n"
        f"name: lead-{safe_name.replace('_', '-')}\n"
        f"description: Lead wiki for {b_name}\n"
        "type: lead\n"
        f"created: {datetime.now().strftime('%Y-%m-%d')}\n"
        "status: active\n"
        "---\n\n"
    )
    md_content += f"# Lead Wiki: {b_name}\n"
    md_content += f"> **Hunted On:** {now}\n> **Source URL:** {url}\n> **Confidence Score:** {extracted_data.get('confidence_score', 'N/A')}/10\n\n"
    md_content += "## Owner / Decision Maker\n"
    md_content += f"- **Name:** {extracted_data.get('owner_name', 'Unknown')}\n"
    md_content += f"- **Role:** {extracted_data.get('owner_role', 'Unknown')}\n\n"
    md_content += "## Contact Info\n"
    md_content += f"- **Email:** {extracted_data.get('personal_email', 'None found')}\n"
    phone = extracted_data.get('direct_phone', 'None found')
    badge = "(Mobile)" if extracted_data.get('is_verified_mobile') else "(Standard)"
    md_content += f"- **Phone:** {phone} {badge}\n\n"
    md_content += "---\n*Auto-generated by Smart Scraper (ScrapeGraphAI + Groq)*\n"

    try:
        with open(wiki_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        logger.info(f"[LEAD WIKI] Saved -> {wiki_path}")
    except Exception as e:
        logger.error(f"[LEAD WIKI] Failed: {e}")