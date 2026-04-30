# -*- coding: utf-8 -*-
"""
SEO Audit Skill for OROVA Moltbot
Based on 'seo-audit' from Awesome-OpenClaw Skills.
Automates Technical and On-Page checks.
"""
import asyncio
import json
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.skills.browser_ops import BrowsingAgent
import nest_asyncio
nest_asyncio.apply()

class SEOAuditor:
    """
    Performs a deep SEO audit of a target website.
    """
    def __init__(self):
        pass

    async def audit_site_async(self, url: str) -> dict:
        """
        Run a full SEO audit.
        checks: Title, Meta, H1, Load Time (Simulated), Mobile Viewport, Console Errors.
        """
        report = {
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "score": 0,
            "technical": {},
            "on_page": {},
            "recommendations": []
        }
        
        async with BrowsingAgent(headless=True) as agent:
            await agent.launch()
            page = agent.page
            
            # Start timer
            start_time = datetime.now()
            
            try:
                response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                status = response.status if response else 0
                load_time = (datetime.now() - start_time).total_seconds()
            except Exception as e:
                return {"error": f"Failed to load site: {e}"}

            # Technical Checks
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            
            # On-Page Checks
            title = await page.title()
            
            evaluation = await page.evaluate('''() => {
                const h1s = Array.from(document.querySelectorAll('h1')).map(el => el.innerText);
                const metas = document.querySelector('meta[name="description"]');
                const metaDesc = metas ? metas.content : "";
                const images = Array.from(document.querySelectorAll('img'));
                const imagesWithoutAlt = images.filter(img => !img.alt).length;
                const canonical = document.querySelector('link[rel="canonical"]')?.href || "";
                const viewport = document.querySelector('meta[name="viewport"]')?.content || "";
                
                return {
                    h1_count: h1s.length,
                    h1_text: h1s[0] || "",
                    meta_length: metaDesc.length,
                    meta_desc: metaDesc,
                    img_count: images.length,
                    missing_alt: imagesWithoutAlt,
                    canonical: canonical,
                    viewport: viewport
                };
            }''')
            
            # Scoring & Logic
            score = 100
            recs = []
            
            # Speed
            report["technical"]["load_time_seconds"] = round(load_time, 2)
            if load_time > 3:
                score -= 10
                recs.append("Site load time is slow (> 3s). Optimize images and scripts.")
            
            # Mobile
            report["technical"]["viewport"] = evaluation["viewport"]
            if "width=device-width" not in evaluation["viewport"]:
                score -= 20
                recs.append("CRITICAL: Mobile viewport tag missing.")
            
            # SSL
            if not url.startswith("https"):
                score -= 20
                recs.append("CRITICAL: Site is not using HTTPS.")
            
            # Title
            report["on_page"]["title"] = title
            if len(title) < 10 or len(title) > 60:
                score -= 5
                recs.append("Title tag length is not optimal (10-60 chars).")
                
            # Meta Description
            report["on_page"]["meta_desc"] = evaluation["meta_desc"]
            if evaluation["meta_length"] < 50 or evaluation["meta_length"] > 160:
                score -= 5
                recs.append("Meta description missing or improper length.")
                
            # H1
            report["on_page"]["h1_count"] = evaluation["h1_count"]
            if evaluation["h1_count"] != 1:
                score -= 10
                recs.append(f"Found {evaluation['h1_count']} H1 tags. There should be exactly one.")
            
            # Images
            if evaluation["missing_alt"] > 0:
                score -= 5
                recs.append(f"{evaluation['missing_alt']} images are missing ALT text.")
                
            report["score"] = max(0, score)
            report["recommendations"] = recs
            
            return report

def run_seo_audit(url: str):
    """Synchronous wrapper for SEO Audit"""
    auditor = SEOAuditor()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        import nest_asyncio
        nest_asyncio.apply()
        return loop.run_until_complete(auditor.audit_site_async(url))
        
    return loop.run_until_complete(auditor.audit_site_async(url))

if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(json.dumps(run_seo_audit(url), indent=2))
