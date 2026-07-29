"""
Lead Enrichment — Free Owner/Email/Phone Extraction
====================================================
Completely free enrichment that extracts owner names, emails, and phone numbers
from business websites using:
1. Direct website scraping (free)
2. Google Gemini AI extraction (free via GOOGLE_API_KEY)
3. DuckDuckGo search enrichment (free, no API key needed)
4. Multiple regex patterns on rendered page content
5. Apollo.io fallback (free tier, 10+ credits/month) — only used when free methods fail

No paid APIs required. Zero cost per lead.
"""

import re
import asyncio
import logging
import json
import os
import httpx
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Regex patterns ──────────────────────────────────────────────────
OWNER_PATTERNS = [
    r'([A-Z][a-z]+ [A-Z][a-z]+)\s*[,–\-—]\s*(?:Owner|CEO|President|Founder|Director|Proprietor|Manager|Principal)',
    r'(?:Owner|CEO|President|Founder|Director|Proprietor|Manager|Principal)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)',
    r'(?:owned|founded|run|operated|managed)\s+by\s+([A-Z][a-z]+ [A-Z][a-z]+)',
    r'([A-Z][a-z]+ [A-Z][a-z]+)\s+(?:owns|founded|runs|operates|manages)\s',
    r'(?:Meet|Introducing|Welcome)\s+(?:our\s+)?(?:founder|CEO|owner|president)[,:]\s+([A-Z][a-z]+ [A-Z][a-z]+)',
]
EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b')
PHONE_PATTERN = re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
NON_DIGIT_RE = re.compile(r'\D')
FAKE_PHONE_PATTERNS = [
    r'^(\d)\1{9}$', r'^1234567890$', r'^0123456789$', r'^9876543210$',
    r'^555\d{7}$', r'^000\d{7}$',
]
CATCHALL_EMAIL_PREFIXES = [
    'info', 'contact', 'hello', 'support', 'noreply', 'no-reply',
    'admin', 'webmaster', 'sales', 'marketing', 'team', 'careers',
    'jobs', 'hr', 'billing', 'accounts', 'office', 'mail',
    'enquiries', 'inquiries', 'enquiry', 'inquiry',
]
CONTACT_PATHS = ['/contact', '/contact-us', '/about', '/about-us', '/team', '/our-team']


async def enrich_lead(url: str, business_name: str = "", existing_phone: str = "", existing_email: str = "") -> dict:
    """
    7-layer enrichment pipeline. All free or cheap.
    Only calls Apollo if everything else fails (preserves free credits).
    """
    result = {
        "owner": "", "email": existing_email or "", "phone": existing_phone or "",
        "confidence_score": 0, "sources_used": [], "enriched": False,
    }
    if not url:
        return result

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.hostname or ""
    base_url = f"{parsed.scheme}://{domain}" if parsed.scheme else f"https://{domain}"

    # ── Step 1-4: Scrape homepage + /about + /contact pages ──
    all_text = ""
    pages_scraped = []

    page = await _scrape(base_url)
    if page:
        all_text += page + "\n"
        pages_scraped.append("homepage")

    for path in CONTACT_PATHS:
        p = await _scrape(base_url.rstrip("/") + path)
        if p and len(p) > 50:
            all_text += p + "\n"
            pages_scraped.append(path.strip("/"))

    result["sources_used"] = pages_scraped

    if all_text:
        o = _extract_owner(all_text)
        if o: result["owner"] = o; result["confidence_score"] += 30
        e = _extract_email(all_text) if not result["email"] else ""
        if e: result["email"] = e; result["confidence_score"] += 30
        p = _extract_phone(all_text) if not result["phone"] else ""
        if p: result["phone"] = p; result["confidence_score"] += 20

    # ── Step 5: DuckDuckGo search for missing owner/email ──
    if not result["owner"] or not result["email"]:
        sq = business_name or domain.replace("www.", "").split(".")[0]
        ddg = await _search_ddg(sq, domain)
        if ddg:
            if not result["owner"] and ddg.get("owner"):
                result["owner"] = ddg["owner"]; result["confidence_score"] += 20
            if not result["email"] and ddg.get("email"):
                result["email"] = ddg["email"]; result["confidence_score"] += 20
            if not result["phone"] and ddg.get("phone"):
                result["phone"] = ddg["phone"]; result["confidence_score"] += 15
            result["sources_used"].append("duckduckgo_search")

    # ── Step 6: Gemini AI extraction (free) ──
    if (not result["owner"] or not result["email"]) and all_text and len(all_text) > 200:
        ai = await _ai_extract(all_text)
        if ai:
            if not result["owner"] and ai.get("owner"):
                result["owner"] = ai["owner"]; result["confidence_score"] += 25
            if not result["email"] and ai.get("email"):
                result["email"] = ai["email"]; result["confidence_score"] += 25
            if not result["phone"] and ai.get("phone"):
                result["phone"] = ai["phone"]; result["confidence_score"] += 15
            result["sources_used"].append("ai_extraction")

    # ── Step 7: Apollo fallback (only when still missing email) ──
    if not result["email"] and os.getenv("APOLLO_API_KEY"):
        ap = _apollo(company_domain=domain, company_name=business_name or domain.split(".")[0])
        if ap.get("email"):
            result["email"] = ap["email"]; result["confidence_score"] += 35
            result["sources_used"].append("apollo_fallback")
        if not result["phone"] and ap.get("phone"):
            result["phone"] = ap["phone"]; result["confidence_score"] += 15

    result["enriched"] = bool(result["owner"] or result["email"])
    result["confidence_score"] = min(result["confidence_score"], 100)
    return result


async def enrich_leads_batch(leads: list) -> list:
    """Enrich multiple leads in parallel (max 3 at once)."""
    # Fan-out cap owned by app/core/hardening.CONCURRENCY_LIMITS.
    from app.core.hardening import concurrency_limit
    sem = asyncio.Semaphore(concurrency_limit("lead_enrich_batch"))

    async def _one(lead):
        async with sem:
            r = await enrich_lead(
                lead.get("url", ""),
                lead.get("business", lead.get("title", "")),
                lead.get("phone", ""),
                lead.get("email", ""),
            )
            if r.get("owner") and not lead.get("owner"): lead["owner"] = r["owner"]
            if r.get("email") and not lead.get("email"): lead["email"] = r["email"]
            if r.get("phone") and not lead.get("phone"): lead["phone"] = r["phone"]
            lead["_enriched"] = r["enriched"]
            lead["_confidence"] = r["confidence_score"]
            return lead

    return await asyncio.gather(*[_one(l) for l in leads if l.get("url")])


# ── LinkedIn Free Enrichment ────────────────────────────────────────

LINKEDIN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


async def _search_linkedin_profile(business_name: str, owner_name: str = "", domain: str = "") -> str:
    """Search DuckDuckGo for a LinkedIn profile URL. Free, no API key needed."""
    query_parts = [business_name]
    if owner_name:
        query_parts.append(owner_name)
    query_parts.append("site:linkedin.com/in")
    query = "+".join(query_parts)

    try:
        async with httpx.AsyncClient(headers=LINKEDIN_HEADERS, follow_redirects=True, timeout=12.0) as c:
            r = await c.get(f"https://html.duckduckgo.com/html/?q={query}")
            if r.status_code != 200:
                return ""
            # Extract LinkedIn profile URLs from results
            urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?', r.text)
            if urls:
                return urls[0].split("?")[0]
    except Exception as e:
        logger.warning(f"[LINKEDIN] DDG search failed: {e}")
    return ""


async def _scrape_linkedin_public(profile_url: str) -> dict:
    """
    Scrape public LinkedIn profile for free. Only extracts data visible without login.
    Returns: {title, location, summary, current_company, connections_count}
    """
    if not profile_url:
        return {}

    try:
        async with httpx.AsyncClient(headers=LINKEDIN_HEADERS, follow_redirects=True, timeout=12.0) as c:
            r = await c.get(profile_url)
            if r.status_code != 200:
                return {}

            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            result = {}

            # Extract title/role from meta or page text
            title_tag = soup.find("meta", {"property": "og:title"})
            if title_tag:
                result["title"] = title_tag.get("content", "").strip()

            desc_tag = soup.find("meta", {"property": "og:description"})
            if desc_tag:
                desc = desc_tag.get("content", "").strip()
                # Parse "John Doe - CEO at Company - Location | LinkedIn" pattern
                if " - " in desc:
                    parts = desc.split(" - ")
                    if len(parts) >= 2:
                        result["title"] = parts[1].strip()
                    if len(parts) >= 3:
                        result["location"] = parts[2].strip().replace("| LinkedIn", "").strip()

            # Try to extract from JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if data.get("jobTitle"):
                            result["title"] = data["jobTitle"]
                        if data.get("worksFor", {}).get("name"):
                            result["current_company"] = data["worksFor"]["name"]
                        if data.get("description"):
                            result["summary"] = data["description"][:300]
                except: pass

            return result
    except Exception as e:
        logger.warning(f"[LINKEDIN] Profile scrape failed: {e}")
        return {}


async def enrich_with_linkedin(business_name: str, owner_name: str = "", domain: str = "") -> dict:
    """
    Free LinkedIn enrichment: search DDG for profile URL → scrape public data.
    Returns: {linkedin_url, title, location, current_company, summary}
    """
    result = {"linkedin_url": "", "title": "", "location": "", "current_company": "", "summary": ""}

    profile_url = await _search_linkedin_profile(business_name, owner_name, domain)
    if not profile_url:
        return result

    result["linkedin_url"] = profile_url
    profile_data = await _scrape_linkedin_public(profile_url)
    result.update({k: v for k, v in profile_data.items() if v})

    if result.get("title") or result.get("current_company"):
        logger.info(f"[LINKEDIN] Enriched: {business_name} → {result.get('title', 'N/A')} at {result.get('current_company', 'N/A')}")
    else:
        logger.info(f"[LINKEDIN] Found profile URL but limited public data: {profile_url}")

    return result


# ── Helpers ──────────────────────────────────────────────────────────

async def _scrape(url: str) -> str:
    try:
        h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(headers=h, follow_redirects=True, timeout=15.0) as c:
            r = await c.get(url)
            if r.status_code != 200: return ""
            s = BeautifulSoup(r.text, "html.parser")
            for t in s(["script", "style", "nav", "footer", "header", "noscript"]): t.decompose()
            return re.sub(r'\s+', ' ', s.get_text(separator=" ", strip=True))[:8000]
    except: return ""


def _extract_owner(t: str) -> str:
    for p in OWNER_PATTERNS:
        for m in re.findall(p, t):
            c = m.strip()
            if _valid_name(c): return c
    return ""


def _valid_name(n: str) -> bool:
    if not n or len(n) < 5 or len(n) > 50: return False
    parts = n.split()
    if len(parts) < 2 or len(parts) > 4: return False
    if not all(re.match(r"^[A-Za-z'\-\.]+$", p) for p in parts): return False
    if not all(p[0].isupper() for p in parts if p): return False
    stop = {"and","the","for","with","from","our","your","their","its","all","about","contact",
            "read","more","learn","click","here","view","get","started","sign","up","log","in",
            "see","find","out","call","now","free","quote","request","book","schedule"}
    if any(p.lower() in stop for p in parts): return False
    return True


def _extract_email(t: str) -> str:
    for e in EMAIL_PATTERN.findall(t):
        el = e.lower().strip()
        if any(x in el for x in ["example.com","test.com","domain.com","yourdomain","sample"]): continue
        if el.split("@")[0] in CATCHALL_EMAIL_PREFIXES: continue
        return el
    return ""


def _extract_phone(t: str) -> str:
    seen = set()
    for ph in PHONE_PATTERN.findall(t):
        d = NON_DIGIT_RE.sub('', ph)
        if len(d) == 11 and d.startswith('1'): d = d[1:]
        elif len(d) != 10: continue
        if d in seen: continue
        seen.add(d)
        if any(re.match(p, d) for p in FAKE_PHONE_PATTERNS): continue
        if len(set(d)) == 1: continue
        if d in ["1234567890","0123456789","9876543210"]: continue
        return f"+1{d}"
    return ""


async def _search_ddg(query: str, domain: str) -> dict:
    r = {"owner":"","email":"","phone":""}
    for q in [f"{query} owner CEO", f"{query} email contact", f"site:{domain} owner"]:
        try:
            h = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(headers=h, follow_redirects=True, timeout=10.0) as c:
                resp = await c.get(f"https://html.duckduckgo.com/html/?q={q.replace(' ', '+')}")
                if resp.status_code != 200: continue
                s = BeautifulSoup(resp.text, "html.parser")
                for el in s.select(".result__snippet, .snippet, .result__body"):
                    t = el.get_text(separator=" ", strip=True)
                    if not r["owner"]: r["owner"] = _extract_owner(t)
                    if not r["email"]: r["email"] = _extract_email(t)
                    if not r["phone"]: r["phone"] = _extract_phone(t)
            if r["owner"] and r["email"]: break
        except: continue
    return r


async def _ai_extract(text: str) -> dict:
    try:
        from app.core.ai_client import UnifiedAIClient
        ai = UnifiedAIClient()
        resp = await ai.extract(f"""Extract from this business website text. Return ONLY JSON:
{{"owner":"owner/CEO name or empty","email":"email or empty","phone":"phone digits or empty"}}

Text:
{text[:4000]}

JSON:""")
        if not resp: return {}
        j = re.search(r'\{.*\}', resp, re.DOTALL)
        if j:
            d = json.loads(j.group(0))
            return {"owner": d.get("owner",""), "email": d.get("email",""), "phone": d.get("phone","")}
    except: pass
    return {}


def _apollo(company_domain: str = None, company_name: str = None) -> dict:
    """Apollo fallback — only called when free methods fail (preserves credits)."""
    key = os.getenv("APOLLO_API_KEY")
    if not key: return {"email":"","phone":""}
    try:
        import requests
        p = {"api_key": key}
        if company_domain: p["domain"] = company_domain
        if company_name: p["organization_name"] = company_name
        r = requests.post("https://api.apollo.io/v1/contacts/search", json=p,
                          headers={"Content-Type":"application/json"}, timeout=10)
        if r.status_code != 200: return {"email":"","phone":""}
        contacts = r.json().get("contacts", [])
        if not contacts: return {"email":"","phone":""}
        c = contacts[0]
        nums = c.get("phone_numbers") or []
        return {"email": c.get("email","") or "", "phone": nums[0] if nums else ""}
    except: return {"email":"","phone":""}


__all__ = ["enrich_lead", "enrich_leads_batch"]