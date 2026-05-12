# -*- coding: utf-8 -*-
"""
Google Maps Skill (Robust)
Uses SerpApi (best), Google Search (fallback), or DuckDuckGo (tertiary) to find places.
"""

import os
import time
from duckduckgo_search import DDGS
try:
    from serpapi import GoogleSearch
except ImportError:
    GoogleSearch = None

try:
    from googlesearch import search as gsearch
except ImportError:
    gsearch = None

try:
    from app.skills.browser_ops import google_search_scrape
except ImportError:
    try:
        from browser_ops import google_search_scrape
    except ImportError:
        google_search_scrape = None

def _search_places_serpapi(query: str, location: str, limit: int = 5):
    """Tier 1: SerpApi (Requires Key)"""
    api_key = os.environ.get("SERPAPI_API_KEY")
    if not api_key or not GoogleSearch:
        return None

    try:
        # Standard Google Local Search
        params = {
            "engine": "google_local",
            "q": f"{query} in {location}",
            "api_key": api_key,
            "num": limit
        }

        search = GoogleSearch(params)
        results = search.get_dict()

        local_results = results.get("local_results", [])
        places = []
        for r in local_results:
            places.append({
                "name": r.get("title"),
                "address": r.get("address", ""),
                "link": r.get("website") or r.get("links", {}).get("website", ""),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "phone": r.get("phone")
            })
        return places
    except Exception as e:
        print(f"SerpApi Error: {e}")
        return None

def _search_places_google(query: str, location: str, limit: int = 5):
    """Tier 2: Google Search (Unofficial)"""
    if not gsearch:
        return None

    full_query = f"{query} in {location}"
    places = []
    try:
        # advanced=True returns objects with title, url, description
        results = gsearch(full_query, num_results=limit, advanced=True)
        for r in results:
            places.append({
                "name": r.title,
                "address": r.description[:100] + "...", # Best guess
                "link": r.url,
                "snippet": r.description
            })
        return places
    except Exception as e:
        print(f"GoogleSearch Error: {e}")
        return None

def _search_places_ddg(query: str, location: str, limit: int = 5):
    """Tier 3: DuckDuckGo (Simulated)"""
    full_query = f"{query} in {location}"
    results = []

    try:
        with DDGS() as ddgs:
            # Try HTML backend first as it might be less blocked than API
            try:
                ddg_results = list(ddgs.text(full_query, max_results=limit * 2, backend='html'))
            except Exception:
                # Fallback to default
                ddg_results = list(ddgs.text(full_query, max_results=limit * 2))

            for r in ddg_results:
                title = r.get('title', '')
                url = r.get('href', '')
                snippet = r.get('body', '')

                if url and title:
                    results.append({
                        "name": title,
                        "address": snippet[:100] + "...",
                        "link": url,
                        "snippet": snippet
                    })
    except Exception as e:
        print(f"DDG Error: {e}")
        return None

    return results[:limit]

def search_places(query: str, location: str, limit: int = 5):
    """
    Search for places using Multi-Tiered Strategy.
    """
    # 1. SerpApi
    if os.environ.get("SERPAPI_API_KEY"):
        print("Using SerpApi...")
        results = _search_places_serpapi(query, location, limit)
        if results:
            return {
                "success": True,
                "source": "serpapi",
                "count": len(results),
                "places": results
            }

    # 2. Google Search
    print("Using Google Search (fallback)...")
    results = _search_places_google(query, location, limit)
    if results:
        return {
            "success": True,
            "source": "google_search",
            "count": len(results),
            "places": results
        }

    # 3. DuckDuckGo
    print("Using DuckDuckGo (tertiary)...")
    results = _search_places_ddg(query, location, limit)
    if results:
         return {
            "success": True,
            "source": "duckduckgo",
            "count": len(results),
            "places": results
        }

    # 4. Playwright Scraper (Hard Fallback)
    print("Using Playwright Scraper (Hard Fallback)...")
    if google_search_scrape:
        full_query = f"{query} in {location}"
        scrape_results = google_search_scrape(full_query, limit)
        if scrape_results:
            # Map scrape results to place format
            places = []
            for r in scrape_results:
                places.append({
                    "name": r.get('title'),
                    "address": r.get('snippet', '')[:100],
                    "link": r.get('url'),
                    "snippet": r.get('snippet'),
                    "phone": "N/A" # Scraper can't easily get phone from results page
                })

            return {
                "success": True,
                "source": "playwright_scraper",
                "count": len(places),
                "places": places
            }

    return {"success": False, "error": "No results found. Try using broader terms, a different location, or the 'google_search' tool directly."}

def register_google_maps_skills(TOOLS, tool_decorator):
    """Register Google Maps skills"""

    @tool_decorator("search_places", "Find places/businesses near a location")
    def _search_places(query: str, location: str, limit: int = 5):
        return search_places(query, location, limit)

    TOOLS["search_places"] = {"func": _search_places, "description": "Find places near location"}

    return TOOLS
