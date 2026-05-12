# -*- coding: utf-8 -*-
"""
Lead Generation Skill for OROVA MikeBot
The "Rainmaker" - Finds and qualifies business leads (100% Free)

Logic:
1. Search DuckDuckGo for "{niche} {location} business"
2. Extract business names and URLs
3. Score leads based on OROVA criteria
4. Save to CSV in ./data folder
"""

import os
import csv
import json
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

# Data storage
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

LEADS_FILE = DATA_DIR / "leads.csv"
LEADS_ARCHIVE = DATA_DIR / "leads_archive"
LEADS_ARCHIVE.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD SEARCH (Using DuckDuckGo - FREE)
# ═══════════════════════════════════════════════════════════════════════════════

def search_leads(niche: str, location: str, max_results: int = 20) -> List[Dict]:
    """Search for potential leads using DuckDuckGo"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return [{"error": "duckduckgo-search not installed. Run: pip install duckduckgo-search"}]
    
    # Build search queries
    queries = [
        f"{niche} businesses in {location}",
        f"{niche} companies {location}",
        f"{niche} services {location} contact",
    ]
    
    all_results = []
    seen_urls = set()
    
    with DDGS() as ddgs:
        for query in queries:
            try:
                results = list(ddgs.text(query, max_results=max_results // len(queries)))
                for r in results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "description": r.get("body", ""),
                            "query": query
                        })
            except Exception as e:
                print(f"Search error for '{query}': {e}")
                continue
    
    return all_results[:max_results]

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD QUALIFICATION (OPAL-Style Scoring)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_opal_score(lead: Dict) -> int:
    """
    Calculate OPAL-style score for a lead (0-100)
    
    Scoring Criteria:
    - Has a website (+20)
    - Business-related domain (+15)
    - Contact info in description (+15)
    - Location match (+15)
    - Social media presence hints (+10)
    - Professional title/description (+10)
    - Not a directory/listing site (+15)
    """
    score = 0
    url = lead.get("url", "").lower()
    title = lead.get("title", "").lower()
    desc = lead.get("description", "").lower()
    
    # Has a website
    if url and "http" in url:
        score += 20
    
    # Business-related domain (not just directories)
    directory_sites = ["yelp", "yellowpages", "facebook.com/pages", "linkedin.com/company", 
                       "mapquest", "manta", "bbb.org", "chamberofcommerce", "angi.com"]
    is_directory = any(d in url for d in directory_sites)
    
    if not is_directory:
        score += 15
    
    # Has own domain (not social media profile)
    social_sites = ["facebook.com", "instagram.com", "twitter.com", "linkedin.com", "tiktok.com"]
    if not any(s in url for s in social_sites):
        score += 10
    
    # Contact info hints
    contact_keywords = ["contact", "call", "phone", "email", "@", "schedule", "appointment"]
    if any(kw in desc for kw in contact_keywords):
        score += 15
    
    # Professional indicators
    professional_keywords = ["owner", "ceo", "founder", "manager", "dealership", "auto", 
                            "collision", "repair", "service", "shop", "center"]
    if any(kw in title or kw in desc for kw in professional_keywords):
        score += 10
    
    # Business indicators in title
    business_keywords = ["inc", "llc", "corp", "company", "group", "automotive", "motors"]
    if any(kw in title for kw in business_keywords):
        score += 10
    
    # Penalize generic results
    generic_keywords = ["list of", "best 10", "top 10", "directory", "find a", "near me"]
    if any(kw in title for kw in generic_keywords):
        score -= 20
    
    return max(0, min(100, score))  # Clamp between 0-100

def qualify_leads(leads: List[Dict], min_score: int = 40) -> List[Dict]:
    """Score and filter leads based on OPAL criteria"""
    qualified = []
    
    for lead in leads:
        score = calculate_opal_score(lead)
        lead["opal_score"] = score
        lead["qualified"] = score >= min_score
        lead["scored_at"] = datetime.now().isoformat()
        
        if score >= min_score:
            qualified.append(lead)
    
    # Sort by score descending
    qualified.sort(key=lambda x: x["opal_score"], reverse=True)
    
    return qualified

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD STORAGE
# ═══════════════════════════════════════════════════════════════════════════════

def save_leads_to_csv(leads: List[Dict], filename: Optional[str] = None) -> str:
    """Save leads to CSV file"""
    if not leads:
        return "No leads to save"
    
    if filename:
        filepath = DATA_DIR / filename
    else:
        filepath = LEADS_FILE
    
    # Define CSV columns
    fieldnames = ["title", "url", "description", "opal_score", "qualified", "scored_at", "query"]
    
    # Check if file exists for append mode
    file_exists = filepath.exists()
    
    with open(filepath, 'a' if file_exists else 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        
        if not file_exists:
            writer.writeheader()
        
        for lead in leads:
            writer.writerow(lead)
    
    return str(filepath)

def load_leads_from_csv(filename: Optional[str] = None) -> List[Dict]:
    """Load leads from CSV file"""
    if filename:
        filepath = DATA_DIR / filename
    else:
        filepath = LEADS_FILE
    
    if not filepath.exists():
        return []
    
    leads = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            leads.append(row)
    
    return leads

def archive_leads():
    """Archive current leads file with timestamp"""
    if not LEADS_FILE.exists():
        return {"success": False, "error": "No leads file to archive"}
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"leads_{timestamp}.csv"
    archive_path = LEADS_ARCHIVE / archive_name
    
    LEADS_FILE.rename(archive_path)
    
    return {"success": True, "archived_to": str(archive_path)}

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN FUNCTION: find_leads
# ═══════════════════════════════════════════════════════════════════════════════

def find_leads(niche: str, location: str, max_results: int = 20, min_score: int = 40) -> Dict[str, Any]:
    """
    Main lead generation function.
    
    Args:
        niche: Industry/business type (e.g., "automotive", "real estate")
        location: Geographic location (e.g., "Miami", "California")
        max_results: Maximum number of leads to search for
        min_score: Minimum OPAL score to qualify (0-100)
    
    Returns:
        Dict with search results, qualified leads, and file path
    """
    # Search for leads
    print(f"🔍 Searching for {niche} leads in {location}...")
    raw_leads = search_leads(niche, location, max_results)
    
    if not raw_leads:
        return {
            "success": False,
            "error": "No leads found",
            "niche": niche,
            "location": location
        }
    
    # Check for errors
    if raw_leads and "error" in raw_leads[0]:
        return {"success": False, "error": raw_leads[0]["error"]}
    
    # Qualify leads
    print(f"📊 Scoring {len(raw_leads)} leads with OPAL criteria...")
    qualified_leads = qualify_leads(raw_leads, min_score)
    
    # Save to CSV
    if qualified_leads:
        filepath = save_leads_to_csv(qualified_leads)
        print(f"💾 Saved {len(qualified_leads)} qualified leads to {filepath}")
    
    return {
        "success": True,
        "niche": niche,
        "location": location,
        "total_found": len(raw_leads),
        "qualified_count": len(qualified_leads),
        "min_score_used": min_score,
        "saved_to": str(LEADS_FILE) if qualified_leads else None,
        "top_leads": qualified_leads[:5],  # Return top 5 for display
        "message": f"Found {len(qualified_leads)} qualified leads out of {len(raw_leads)} searched"
    }

def get_leads_summary() -> Dict:
    """Get summary of current leads"""
    leads = load_leads_from_csv()
    
    if not leads:
        return {"total": 0, "message": "No leads in database"}
    
    qualified = [l for l in leads if l.get("qualified") == "True"]
    
    # Score distribution
    scores = []
    for l in leads:
        try:
            scores.append(int(l.get("opal_score", 0)))
        except:
            pass
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    return {
        "total": len(leads),
        "qualified": len(qualified),
        "average_score": round(avg_score, 1),
        "file": str(LEADS_FILE)
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SKILL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_lead_gen_skills(TOOLS, tool_decorator):
    """Register Lead Generation tools"""
    
    @tool_decorator("find_leads", "Search for business leads in a niche and location")
    def _find_leads(niche: str, location: str, max_results: int = 20):
        return find_leads(niche, location, max_results)
    
    @tool_decorator("leads_summary", "Get summary of current leads database")
    def _leads_summary():
        return get_leads_summary()
    
    @tool_decorator("archive_leads", "Archive current leads file")
    def _archive_leads():
        return archive_leads()
    
    TOOLS["find_leads"] = {"func": _find_leads, "description": "Search for business leads"}
    TOOLS["leads_summary"] = {"func": _leads_summary, "description": "Get leads summary"}
    TOOLS["archive_leads"] = {"func": _archive_leads, "description": "Archive current leads"}
    
    return TOOLS
