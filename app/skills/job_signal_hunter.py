"""
Job Signal Hunter - Hawk's Hiring Intent Detection
Uses python-jobspy to scan job postings as a proxy for company hiring signals.
This is a strong intent signal: if they're hiring, they have money and a problem.
"""

import logging
from typing import List, Dict, Any

try:
    from jobspy import scrape_jobs
except ImportError:
    # python-jobspy removed from the Render deps 2026-07-22 (it pulled pandas+numpy).
    # This skill only runs via the bypassed AI-OS planner; it degrades gracefully.
    scrape_jobs = None

logger = logging.getLogger(__name__)


def hunt_hiring_signals(
    job_title: str = "Sales Manager",
    location: str = "United States",
    days_back: int = 7,
    max_results: int = 25,
    company_keywords: List[str] = None
) -> Dict[str, Any]:
    """
    Scan for companies actively hiring in a target role.
    
    Args:
        job_title: Target role (e.g., "VP of Sales", "Marketing Manager")
        location: Geographic filter
        days_back: Only include jobs posted in last N days
        max_results: Max job postings to return
        company_keywords: Optional filter (e.g., ["saas", "fintech"])
    
    Returns:
        {
            "success": bool,
            "signals_found": int,
            "companies": [
                {
                    "company": "TechCorp",
                    "job_title": "VP of Sales",
                    "posting_date": "2024-05-01",
                    "salary_min": 150000,
                    "salary_max": 200000,
                    "company_url": "https://techcorp.com",
                    "job_url": "https://linkedin.com/job/12345",
                    "description_snippet": "..."
                },
                ...
            ],
            "pitch": "I saw you're actively hiring for [role]—our AI closes deals while you find the right person."
        }
    """
    if scrape_jobs is None:
        return {
            "success": False,
            "signals_found": 0,
            "companies": [],
            "error": "job scanning unavailable (python-jobspy not installed on this deploy)",
        }
    try:
        logger.info(f"[JobSpy] Hunting signals: {job_title} in {location}")
        
        # Scrape job postings
        jobs = scrape_jobs(
            site_name=["linkedin", "indeed", "glassdoor"],
            search_term=job_title,
            location=location,
            results_wanted=max_results,
            hours_old=days_back * 24,  # Convert days to hours
            linkedin_fetch_description=True
        )
        
        if not jobs or len(jobs) == 0:
            logger.warning(f"[JobSpy] No jobs found for {job_title}")
            return {
                "success": False,
                "signals_found": 0,
                "companies": [],
                "error": f"No hiring signals for {job_title} in {location}"
            }
        
        # Extract signals
        signals = []
        for job in jobs:
            company = {
                "company": job.get("company"),
                "job_title": job.get("job_title"),
                "posting_date": job.get("date_posted"),
                "salary_min": job.get("min_amount"),
                "salary_max": job.get("max_amount"),
                "company_url": job.get("company_url"),
                "job_url": job.get("job_url"),
                "description_snippet": (job.get("description", "")[:200] + "...") if job.get("description") else None
            }
            signals.append(company)
            logger.info(f"[JobSpy] Signal: {company['company']} hiring for {company['job_title']}")
        
        return {
            "success": True,
            "signals_found": len(signals),
            "companies": signals,
            "pitch": f"I noticed {len(signals)} companies actively hiring for {job_title}—our AI can help them close those roles faster.",
        }
    
    except Exception as e:
        logger.error(f"[JobSpy] Error: {e}")
        return {
            "success": False,
            "signals_found": 0,
            "companies": [],
            "error": str(e)
        }


def generate_hiring_outreach(company: Dict[str, Any], agency_name: str = "OROVA") -> str:
    """
    Generate an outreach email leveraging the hiring signal.
    
    Args:
        company: Company dict from hunt_hiring_signals
        agency_name: Your agency name
    
    Returns:
        Email body as string
    """
    return f"""Hi {company.get('company')},

I noticed you're actively hiring for {company.get('job_title')}. 

While you're building your team, companies like yours often struggle with lead generation and sales velocity in the interim.

What if your new hire had a pipeline of 50+ qualified leads waiting on day one?

Our AI handles cold outreach, call routing, and lead qualification 24/7. No setup required—we integrate with your Salesforce or Pipedrive in minutes.

Ready to try it? I can show you a custom demo for your {company.get('job_title')} role within 24 hours.

Best,
{agency_name} Team
"""
