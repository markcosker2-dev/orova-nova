"""
Apollo.io Email Enrichment - Safe B2B Data Lookup
Uses Apollo's free tier to enrich leads without LinkedIn scraping risks.
Requires: APOLLO_API_KEY environment variable.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def enrich_lead_apollo(
    company_name: str = None,
    company_domain: str = None,
    person_name: str = None,
    person_title: str = None,
    person_email: str = None,
) -> Dict[str, Any]:
    """
    Look up B2B contact info via Apollo.io (no LinkedIn scraping).
    
    Args:
        company_name: Company legal name
        company_domain: Company domain (e.g., "techcorp.com")
        person_name: First & last name
        person_title: Job title
        person_email: Email (if already known, verify it)
    
    Returns:
        {
            "success": bool,
            "email": "john@techcorp.com",
            "direct_phone": "+1-555-1234",
            "verified": bool,
            "confidence": 0.95,
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "data_sources": ["email_verified", "company_directory"],
            "raw_response": {...}
        }
    """
    api_key = os.getenv("APOLLO_API_KEY")
    if not api_key:
        logger.error("[Apollo] APOLLO_API_KEY not set")
        return {"success": False, "error": "API key missing"}
    
    try:
        # Build search query
        query = {}
        if person_name:
            query["person_name"] = person_name
        if person_title:
            query["person_title"] = person_title
        if company_name:
            query["organization_name"] = company_name
        if company_domain:
            query["domain"] = company_domain
        if person_email:
            query["email"] = person_email
        
        # Apollo Contacts endpoint
        url = "https://api.apollo.io/v1/contacts/search"
        headers = {"Content-Type": "application/json"}
        payload = {
            **query,
            "api_key": api_key,
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            logger.warning(f"[Apollo] Status {resp.status_code}: {resp.text[:200]}")
            return {"success": False, "error": f"API returned {resp.status_code}"}
        
        data = resp.json()
        contacts = data.get("contacts", [])
        
        if not contacts:
            logger.info(f"[Apollo] No enrichment found for {company_name or company_domain}")
            return {
                "success": False,
                "error": "No contacts found",
                "searched_for": query
            }
        
        # Extract best match
        contact = contacts[0]
        enriched = {
            "success": True,
            "email": contact.get("email"),
            "direct_phone": contact.get("phone_numbers", [None])[0] if contact.get("phone_numbers") else None,
            "verified": contact.get("verified_email", False),
            "confidence": contact.get("email_confidence", 0),
            "linkedin_url": contact.get("linkedin_url"),
            "person_name": contact.get("name"),
            "person_title": contact.get("title"),
            "company_name": contact.get("organization_name"),
            "company_domain": contact.get("website_url"),
            "data_sources": contact.get("data_sources", []),
            "raw_response": contact
        }
        
        email = enriched['email'] or ''
        local, _, domain = email.partition('@')
        logger.info(f"[Apollo] Enriched: {enriched['person_name']} ({local[:1]}***@{domain})")
        return enriched
    
    except Exception as e:
        logger.error(f"[Apollo] Exception: {e}")
        return {"success": False, "error": str(e)}


def bulk_enrich_leads(leads: list[Dict[str, str]]) -> Dict[str, Any]:
    """
    Enrich multiple leads at once.
    
    Args:
        leads: List of {"company_name": "...", "person_name": "...", etc}
    
    Returns:
        {
            "success": bool,
            "enriched": int,
            "failed": int,
            "leads": [enriched_lead1, enriched_lead2, ...]
        }
    """
    enriched = []
    failed = 0
    
    for lead in leads:
        result = enrich_lead_apollo(
            company_name=lead.get("company_name"),
            company_domain=lead.get("company_domain"),
            person_name=lead.get("person_name"),
            person_title=lead.get("person_title"),
            person_email=lead.get("person_email"),
        )
        
        if result["success"]:
            enriched.append(result)
        else:
            failed += 1
    
    return {
        "success": failed < len(leads),
        "enriched": len(enriched),
        "failed": failed,
        "leads": enriched
    }
