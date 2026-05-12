# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Configuration Loader
Loads industry-specific configs from Niche_Verticals/<vertical>/
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERTICALS_DIR = os.path.join(BASE_DIR, "Niche_Verticals")
AVAILABLE_VERTICALS = ["Automotive", "High_End_Fitness", "Real_Estate", "Construction"]


def load_vertical(vertical_name: str) -> dict:
    """
    Load all config files for a given vertical.
    Returns dict with keys: queries, scoring_rules, email_templates, meta
    """
    vertical_dir = os.path.join(VERTICALS_DIR, vertical_name)

    if not os.path.isdir(vertical_dir):
        raise ValueError(
            f"Vertical '{vertical_name}' not found. "
            f"Available: {AVAILABLE_VERTICALS}"
        )

    config = {"vertical_name": vertical_name}

    for filename in ["queries.json", "scoring_rules.json", "email_templates.json"]:
        filepath = os.path.join(vertical_dir, filename)
        key = filename.replace(".json", "")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                config[key] = json.load(f)
            logger.info(f"Loaded {filename} for {vertical_name}")
        else:
            config[key] = {}
            logger.warning(f"Missing {filename} for {vertical_name}")

    return config


def list_verticals() -> list:
    """List all available verticals."""
    if not os.path.isdir(VERTICALS_DIR):
        return []
    return [
        d for d in os.listdir(VERTICALS_DIR)
        if os.path.isdir(os.path.join(VERTICALS_DIR, d))
    ]


def get_scoring_prompt(scoring_rules: dict, business_name: str, url: str, content: str) -> str:
    """
    Build a Universal Lead Scoring prompt using CLV-based rules.
    This replaces niche-specific keywords with value-based assessment.
    """
    industry = scoring_rules.get("industry", "high-ticket services")
    ideal_traits = scoring_rules.get("ideal_traits", [])
    disqualifiers = scoring_rules.get("disqualifiers", [])
    clv_range = scoring_rules.get("clv_range", "$5,000 - $50,000+")

    traits_str = "\n".join(f"   - {t}" for t in ideal_traits) if ideal_traits else "   - High-ticket services"
    disq_str = "\n".join(f"   - {d}" for d in disqualifiers) if disqualifiers else "   - Low-budget/commodity services"

    return f"""
You are an expert lead qualification analyst for OROVA, an AI Lead Generation Agency.
We serve {industry} businesses with AI-powered lead generation and qualification.

UNIVERSAL CLV-BASED SCORING (Not keyword-based):
Score leads on their potential Customer Lifetime Value (CLV), estimated at {clv_range}.

PROSPECT:
Name: {business_name}
URL: {url}
Content: {content[:3000]}

IDEAL TRAITS (Score Higher):
{traits_str}

DISQUALIFIERS (Score Lower):
{disq_str}

TASK:
1. Identify their primary services.
2. Estimate their target market (Luxury/Premium/Mid/Budget).
3. Estimate CLV potential on a 0-10 scale (10 = perfect high-CLV fit).
4. Write a 1-sentence "Icebreaker" observation for outreach.

Return ONLY JSON:
{{
    "primary_service": "string",
    "market_tier": "Luxury/Premium/Mid/Budget",
    "estimated_clv": "$XX,XXX",
    "qualification_score": 8,
    "qualification_reason": "Why this score",
    "icebreaker": "Specific observation about their business"
}}
"""


if __name__ == "__main__":
    print("Available Verticals:", list_verticals())
    for v in list_verticals():
        cfg = load_vertical(v)
        print(f"\n{v}:")
        print(f"  Queries: {len(cfg.get('queries', {}).get('search_queries', []))}")
        print(f"  Scoring Rules: {'✓' if cfg.get('scoring_rules') else '✗'}")
        print(f"  Email Templates: {'✓' if cfg.get('email_templates') else '✗'}")
