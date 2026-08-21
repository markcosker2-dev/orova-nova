# -*- coding: utf-8 -*-
"""
Follow-Up Sequence Skill for OROVA (Quill Agent)
Manages multi-step email cadences for nurturing prospects.
"""

import logging
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Sequence Templates ──────────────────────────────────────────
SEQUENCES = {
    "cold_intro": {
        "name": "Cold Intro Sequence",
        "steps": [
            {"day": 0, "subject": "Quick question about {company}", "template": "intro"},
            {"day": 2, "subject": "Re: Quick question about {company}", "template": "value_add"},
            {"day": 5, "subject": "Thought you'd want to see this, {first_name}", "template": "case_study"},
            {"day": 10, "subject": "[Last chance] Free {service} audit for {company}", "template": "breakup"},
        ]
    },
    "warm_followup": {
        "name": "Warm Follow-Up (Post-Reply)",
        "steps": [
            {"day": 0, "subject": "Great chatting, {first_name}", "template": "recap"},
            {"day": 3, "subject": "The proposal you asked about", "template": "proposal"},
            {"day": 7, "subject": "Checking in — any questions?", "template": "nudge"},
        ]
    },
    "re_engage": {
        "name": "Re-Engagement (Cold Leads)",
        "steps": [
            {"day": 0, "subject": "{first_name}, noticed something about {company}", "template": "new_hook"},
            {"day": 4, "subject": "Quick update on what we've been doing", "template": "social_proof"},
            {"day": 14, "subject": "Last one from me, {first_name}", "template": "breakup"},
        ]
    },
}

# ── Email Body Templates ────────────────────────────────────────
BODY_TEMPLATES = {
    "intro": """Hey {first_name},

I came across {company} while researching {industry} in {location} — impressive work.

At OROVA, we help businesses like yours generate more high-value clients through AI-powered marketing and outreach.

Would you be open to a quick 15-minute call this week? I'd love to share a few ideas specific to {company}.

— Mark Cosker, OROVA""",

    "value_add": """Hey {first_name},

Following up on my last note. I did a quick audit of {company}'s online presence and found a few areas where we could 2-3x your inbound leads:

• {insight_1}
• {insight_2}

I put together a free mini-report — want me to send it over?

— Mark""",

    "case_study": """Hey {first_name},

Quick story: One of our clients (similar to {company}) was stuck at {pain_point}. Within 60 days, we helped them:

✅ {result_1}
✅ {result_2}

I genuinely think we could do the same for {company}. Happy to walk you through it on a 15-minute call.

— Mark""",

    "breakup": """Hey {first_name},

I've reached out a couple times now, so I don't want to be a pest.

If you're not interested, no hard feelings at all. But if you ever want to explore how OROVA could help {company} grow, my door is always open.

Best of luck with everything.

— Mark""",

    "recap": """Hey {first_name},

Great connecting earlier! As discussed, here's a quick recap:

• What we do: {service_summary}
• What I'll send: {deliverable}
• Next step: {next_step}

Looking forward to helping {company} grow.

— Mark""",

    "proposal": """Hey {first_name},

As promised, here's the proposal for {company}:

{proposal_content}

Let me know if you have any questions. Happy to jump on a call to walk through it.

— Mark""",

    "nudge": """Hey {first_name},

Just checking in on the proposal I sent over. Any questions or thoughts?

No rush — just want to make sure it didn't get buried.

— Mark""",

    "new_hook": """Hey {first_name},

It's been a while since we connected. I was doing some research and noticed {new_insight} about {company}.

We've been refining our approach and I think we could help — interested in hearing more?

— Mark""",

    "social_proof": """Hey {first_name},

Quick update from our end — we recently helped {case_company} achieve:

✅ {case_result}

Your business crossed my mind because I think we could deliver similar results for {company}. Worth a quick chat?

— Mark""",
}


async def generate_sequence(prospect: dict, sequence_type: str = "cold_intro") -> dict:
    """
    Generate a complete follow-up email sequence for a prospect.

    Args:
        prospect: dict with keys: first_name, company, industry, location, email
        sequence_type: 'cold_intro', 'warm_followup', or 're_engage'

    Returns:
        dict with scheduled emails and their content
    """
    logger.info(f"[QUILL] Generating '{sequence_type}' sequence for {prospect.get('company', 'Unknown')}")

    seq = SEQUENCES.get(sequence_type)
    if not seq:
        return {"success": False, "error": f"Unknown sequence type: {sequence_type}. Use: {list(SEQUENCES.keys())}"}

    today = datetime.now()
    emails = []

    for step in seq["steps"]:
        send_date = today + timedelta(days=step["day"])
        body_template = BODY_TEMPLATES.get(step["template"], "")

        # Fill placeholders with prospect data
        filled_subject = step["subject"].format(**{k: prospect.get(k, f"[{k}]") for k in ["first_name", "company", "service"]})
        filled_body = body_template
        for key, val in prospect.items():
            filled_body = filled_body.replace("{" + key + "}", str(val))

        emails.append({
            "step": step["day"],
            "send_date": send_date.strftime("%Y-%m-%d"),
            "subject": filled_subject,
            "body": filled_body,
            "template": step["template"],
            "status": "scheduled",
        })

    result = {
        "success": True,
        "sequence": seq["name"],
        "prospect": prospect.get("company", "Unknown"),
        "email_count": len(emails),
        "emails": emails,
    }

    logger.info(f"[QUILL] Generated {len(emails)} emails for {prospect.get('company')}")
    return result


async def get_sequence_templates() -> dict:
    """List available follow-up sequence templates."""
    return {
        "success": True,
        "sequences": {k: {"name": v["name"], "steps": len(v["steps"]), "days_span": v["steps"][-1]["day"]} for k, v in SEQUENCES.items()}
    }
