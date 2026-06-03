"""
OROVA Standalone Lead Hunt Runner
=================================
Runs the full find_leads_v2 pipeline end-to-end outside the web app.

Usage:
    py hunt_leads.py
    py hunt_leads.py "window tint Beverly Hills"
    py hunt_leads.py "luxury car dealer" "Los Angeles" 20

Requires env vars: FIRECRAWL_API_KEY, TAVILY_API_KEY, SERPAPI_API_KEY
(all optional — fallback sources still work without them).
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

ROOT   = Path(__file__).resolve().parent
OUT    = ROOT / "last_hunt.json"
sys.path.insert(0, str(ROOT))

load_dotenv()


def box(text):
    line = "-" * max(len(text) + 4, 56)
    top, mid, bot = f"+{line}+", f"|  {text}  |", f"+{line}+"
    return f"\n{top}\n{mid}\n{bot}\n"


def reducer(text, width=54):
    return text if len(text) <= width else text[:width - 3] + "…"


def bar(label, value=""):
    print(f"  {label:<25} {value}", flush=True)


def score_emoji(score):
    if score >= 75: return "[HOT] Hot lead - call today"
    if score >= 55: return "[WARM] Warm - email, then follow up"
    if score >= 35: return "[COLD] Cold - nurture sequence"
    return "[LOW] Low priority - keep in funnel"


async def main():
    query    = sys.argv[1] if len(sys.argv) > 1 else "automotive service california"
    location = sys.argv[2] if len(sys.argv) > 2 else ""
    count    = int(sys.argv[3]) if len(sys.argv) > 3 else 8

    full_query = f"{query} {location}".strip() if location else query

    print(box(reducer("OROVA Lead Hunt - " + full_query, 54)))

    from app.skills.lead_gen_v3 import find_leads_v3 as find_leads_v2

    print("  Step 1/3  Discovery")
    result = await find_leads_v2(
        count=count * 3,
        query=full_query,
    )

    leads  = result.get("leads", []) or []
    if not leads:
        print(f"  Error: No leads returned (check API keys or queries)")
        return

    total  = len(leads)
    qual   = len(leads)

    bar("Raw leads found",  total)
    bar("Qualified score >= 0", qual)
    bar("With owner name", result.get("with_owner_name", 0))
    bar("With email", result.get("with_email", 0))
    bar("With phone", result.get("with_phone", 0))
    print()

    print("  Step 2/3  Scoring")
    leads.sort(key=lambda l: l.get("score", 0) or 0, reverse=True)
    top = leads[:min(len(leads), 10)]
    print()

    print(f"  RESULTS - {len(top)} leads  (sorted by score)")
    print("  " + "-" * 54)
    for i, ld in enumerate(top, 1):
        biz     = ld.get("business") or ld.get("name", "Unknown")
        owner   = ld.get("owner") or ld.get("owner_name", "-")
        email   = ld.get("email", "-")
        phone   = ld.get("phone") or ld.get("phones", "-")
        website = ld.get("website") or ld.get("url", "-")
        score   = ld.get("score", 0)
        status  = ld.get("status", "New")
        print(f"\n  #{i}  {biz}")
        print(f"     score   {score:>3}/100   {score_emoji(score)}")
        print(f"     owner   {owner}")
        print(f"     email   {email}")
        print(f"     phone   {phone}")
        print(f"     website {reducer(website, 44)}")
        print(f"     status  {status}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, default=str)
    print(f"\n  Saved {len(leads)} leads → {OUT.name}\n")


if __name__ == "__main__":
    asyncio.run(main())
