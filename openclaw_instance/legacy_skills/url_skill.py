# -*- coding: utf-8 -*-
"""
URL Shortener Skill for MarkBot
Create short links using free services
"""

import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Local storage for shortened URLs (acts as our own shortener)
URLS_FILE = Path(__file__).parent.parent / "shortened_urls.json"


def _load_urls():
    """Load saved URLs"""
    if URLS_FILE.exists():
        try:
            with open(URLS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_urls(urls: dict):
    """Save URLs"""
    with open(URLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(urls, f, indent=2)


def shorten_url(url: str, custom_alias: str = None):
    """Create a shortened URL using TinyURL (free, no API key needed)
    
    Args:
        url: The long URL to shorten
        custom_alias: Optional custom short name
    """
    try:
        import requests
        
        # Use TinyURL's free API (no key required)
        api_url = f"https://tinyurl.com/api-create.php?url={url}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            short_url = response.text.strip()
            
            # Save to local storage
            urls = _load_urls()
            url_id = custom_alias or hashlib.md5(url.encode()).hexdigest()[:8]
            urls[url_id] = {
                "original": url,
                "short": short_url,
                "created": datetime.now().isoformat(),
                "clicks": 0
            }
            _save_urls(urls)
            
            return {
                "success": True,
                "original_url": url,
                "short_url": short_url,
                "alias": url_id
            }
        else:
            return {"success": False, "error": f"TinyURL API error: {response.status_code}"}
            
    except ImportError:
        return {"success": False, "error": "requests library not installed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_urls(limit: int = 20):
    """List all saved shortened URLs"""
    urls = _load_urls()
    
    items = []
    for alias, data in list(urls.items())[:limit]:
        items.append({
            "alias": alias,
            "short": data.get("short"),
            "original": data.get("original", "")[:50] + "..." if len(data.get("original", "")) > 50 else data.get("original", ""),
            "created": data.get("created", "")[:10]
        })
    
    return {
        "success": True,
        "total": len(urls),
        "urls": items
    }


def get_url(alias: str):
    """Get the original URL for an alias"""
    urls = _load_urls()
    
    if alias in urls:
        return {
            "success": True,
            "alias": alias,
            "short_url": urls[alias].get("short"),
            "original_url": urls[alias].get("original")
        }
    
    return {"success": False, "error": f"Alias '{alias}' not found"}


def register_url_skills(TOOLS, tool_decorator):
    """Register URL Shortener tools"""
    
    @tool_decorator("shorten_url", "Create a shortened URL")
    def _shorten_url(**kwargs):
        url = kwargs.get('url') or kwargs.get('link')
        alias = kwargs.get('alias') or kwargs.get('name') or kwargs.get('custom')
        
        if not url:
            return {"success": False, "error": "Missing 'url' parameter"}
        
        # Ensure URL has protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        return shorten_url(url, alias)
    
    @tool_decorator("list_urls", "List all shortened URLs")
    def _list_urls(**kwargs):
        limit = kwargs.get('limit') or 20
        try:
            limit = int(limit)
        except:
            limit = 20
        return list_urls(limit)
    
    @tool_decorator("get_url", "Get original URL from alias")
    def _get_url(**kwargs):
        alias = kwargs.get('alias') or kwargs.get('name') or kwargs.get('id')
        if not alias:
            return {"success": False, "error": "Missing 'alias' parameter"}
        return get_url(alias)
    
    TOOLS["shorten_url"] = {"func": _shorten_url, "description": "Create shortened URL"}
    TOOLS["list_urls"] = {"func": _list_urls, "description": "List shortened URLs"}
    TOOLS["get_url"] = {"func": _get_url, "description": "Get original URL from alias"}
    
    return TOOLS
