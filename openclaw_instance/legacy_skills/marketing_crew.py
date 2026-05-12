# -*- coding: utf-8 -*-
"""
Marketing Crew: Autonomous Marketing Department
Agent 1: The Analyst (Extracts Tone/Pain Points)
Agent 2: The Closer (Writes Cold Emails)
Agent 3: The Tech (DNS/Deliverability Checks)
"""

import os
import json
import dns.resolver
from typing import Dict, Any
from loguru import logger

# Adjust imports based on where they are
try:
    from app.skills.browser_ops import research_lead
    from app.mikebot import OpenRouterClient, FREE_MODELS
except ImportError:
    # Fallback for running from different cwd
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from app.skills.browser_ops import research_lead
    from app.mikebot import OpenRouterClient, FREE_MODELS

# Constants
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

def check_sender_reputation(domain: str) -> dict:
    """
    Check DNS records (SPF, DKIM, DMARC) for a sender domain.
    Returns:
        dict: {
            "success": bool,
            "spf": bool,
            "dmarc": bool,
            "message": str
        }
    """
    logger.info(f"Checking DNS reputation for: {domain}")

    results = {
        "success": True,
        "spf": False,
        "dmarc": False,
        "message": ""
    }

    messages = []

    # 1. SPF Check
    try:
        answers = dns.resolver.resolve(domain, 'TXT')
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=spf1'):
                results['spf'] = True
                break
        if not results['spf']:
            messages.append("Missing SPF record")
    except Exception as e:
        messages.append(f"SPF Check failed: {e}")

    # 2. DMARC Check
    try:
        answers = dns.resolver.resolve(f"_dmarc.{domain}", 'TXT')
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith('v=DMARC1'):
                results['dmarc'] = True
                break
        if not results['dmarc']:
            messages.append("Missing DMARC record")
    except dns.resolver.NXDOMAIN:
         messages.append("Missing DMARC record (NXDOMAIN)")
    except Exception as e:
        messages.append(f"DMARC Check failed: {e}")

    if messages:
        results['success'] = False
        results['message'] = "; ".join(messages)
        logger.warning(f"DNS Reputation Check Failed for {domain}: {results['message']}")
    else:
        results['message'] = "SPF and DMARC checks passed"
        logger.success(f"DNS Reputation Check Passed for {domain}")

    return results

class MarketingCrew:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            # Try to load from .env if not present (simple check)
            pass

        if not self.api_key:
            print("Warning: MarketingCrew missing API KEY. AI features will fail.")
            self.client = None
        else:
            self.client = OpenRouterClient(self.api_key)

    def _chat(self, system_prompt: str, user_prompt: str) -> str:
        """Helper to chat with the model"""
        if not self.client:
            return "Error: No API Key configured."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Try to use the default model or fallback
        model = DEFAULT_MODEL

        # Ensure model is valid or pick first available free one
        valid_models = list(FREE_MODELS.values())
        if model not in valid_models and valid_models:
             model = valid_models[0]

        try:
            return self.client.chat(messages, model, temperature=0.7)
        except Exception as e:
            return f"AI Error: {str(e)}"

    def run_pitch_generation(self, url: str) -> Dict[str, Any]:
        """
        Run the full marketing crew pipeline:
        1. Analyst: Research URL & Extract Insights
        2. Closer: Write Pitch
        """
        print(f"🚀 Marketing Crew: Analyzing {url}...")

        # 1. Analyst: Gather Data
        print("   [Analyst] Researching website...")
        research_data = research_lead(url)
        if not research_data.get("success"):
            return {"success": False, "error": f"Research failed: {research_data.get('error')}"}

        business_info = research_data.get("business_info", {})
        about_text = business_info.get("about_text", "")
        desc = business_info.get("description", "")
        name = business_info.get("name", "the business")

        # Fallback if scraping got little text
        if len(about_text) < 50 and research_data.get("data", {}).get("content"):
             about_text = research_data.get("data", {}).get("content", "")[:2000]

        raw_text = f"Title: {name}\nDescription: {desc}\nAbout: {about_text[:3000]}"

        # 2. Analyst: Analyze Tone & Pain Points
        print("   [Analyst] Extracting Brand Tone & Pain Points...")
        analyst_system = """You are 'The Analyst', a marketing expert.
Your job is to analyze website content and extract:
1. Brand Tone (e.g. professional, playful, luxury, rugged)
2. Potential Pain Points (what problems might they have?)
3. Key Selling Points (what makes them unique?)

Output concise text."""

        analyst_prompt = f"Analyze this business content:\n\n{raw_text}"

        analysis_raw = self._chat(analyst_system, analyst_prompt)

        # 3. Closer: Write Email
        print("   [Closer] Writing Cold Email...")
        closer_system = """You are 'The Closer', a world-class copywriter.
Write a cold email to this business.
Your goal: Sell 'Automated Lead Generation' services (OROVA).
Constraints:
- Use the Brand Tone identified by the Analyst.
- Address the Pain Points identified.
- Keep it under 150 words.
- No fluff. Direct and valuable.
- Sign off: "Best, MikeBot"
"""

        closer_prompt = f"""
Business Name: {name}
Analyst Insights:
{analysis_raw}

Write the email.
"""

        email_draft = self._chat(closer_system, closer_prompt)

        return {
            "success": True,
            "business_name": name,
            "analyst_insights": analysis_raw,
            "email_draft": email_draft,
            "url": url
        }
