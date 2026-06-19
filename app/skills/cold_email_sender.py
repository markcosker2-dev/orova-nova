"""
app/skills/cold_email_sender.py — AgentMail Cold Email Sender
Sends personalized cold outreach via AgentMail SDK (no SMTP).
Tracks thread_id per lead for reply chaining.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime
from typing import Optional

import agentmail

from app.config import settings
from app.core.ai_client import chat_json
from app.core.business_hours import require_business_hours
from app.core.rate_limiter import limiters

log = logging.getLogger("cold_email_sender")

# ── Templates ─────────────────────────────────────────────────────────────────

DEFAULT_SUBJECT = "Quick question about {business_name}'s growth"

DEFAULT_BODY = """Hi {owner_name},

I came across {business_name} and noticed you're doing great work{category_line}.

I help local businesses like yours consistently book more clients through targeted outreach — without spending a fortune on ads.

Would you be open to a quick 15-minute call this week to see if there's a fit?

Best,
{from_name}
"""

PERSONALIZATION_PROMPT = """Write a brief personalized cold outreach email for this business.
Under 100 words. Sound human, not robotic. No "I hope this email finds you well."

Business: {business_name}
Category: {category}
Location: {address}
Website: {website}
Rating: {rating} stars
Sender: {from_name}

Return JSON only:
{{"subject": "<under 60 chars>", "body": "<under 100 words, plain text>"}}"""


# ── AgentMail client singleton ────────────────────────────────────────────────

_am_client: Optional[agentmail.AsyncAgentMail] = None


def get_agentmail_client() -> agentmail.AsyncAgentMail:
    global _am_client
    if _am_client is None:
        if not settings.agentmail_api_key:
            raise RuntimeError("AGENTMAIL_API_KEY not set in .env")
        _am_client = agentmail.AsyncAgentMail(api_key=settings.agentmail_api_key)
    return _am_client


# ── AI personalization ────────────────────────────────────────────────────────

async def generate_personalized_email(lead) -> tuple[str, str]:
    """Generate subject + body for a lead. Falls back to template on error."""
    try:
        prompt = PERSONALIZATION_PROMPT.format(
            business_name=lead.business_name or "your business",
            category=lead.category or "local services",
            address=lead.address or "your area",
            website=lead.website or "\u2014",
            rating=lead.rating or "\u2014",
            from_name=settings.agentmail_from_name,
        )
        result = await chat_json(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        subject = result.get("subject", "").strip()
        body = result.get("body", "").strip()
        if subject and body:
            return subject, body
    except Exception as exc:
        log.warning("LLM personalization failed for %s: %s", lead.business_name, exc)

    # Fallback to template
    cat_line = f" in the {lead.category} space" if lead.category else ""
    return (
        DEFAULT_SUBJECT.format(business_name=lead.business_name),
        DEFAULT_BODY.format(
            owner_name=lead.owner_name or "there",
            business_name=lead.business_name,
            category_line=cat_line,
            from_name=settings.agentmail_from_name,
        ),
    )


# ── Single send ───────────────────────────────────────────────────────────────

@require_business_hours
async def send_outreach(lead, personalize: bool = True) -> bool:
    """
    Send cold outreach to a single lead via AgentMail.
    Stores the returned thread_id on the lead for reply chaining.
    Returns True on success, False on failure, None if outside business hours.
    """
    if not lead.email:
        log.warning("No email for %s \u2014 skipping", lead.business_name)
        return False

    if not settings.agentmail_api_key or not settings.agentmail_inbox_id:
        log.error("AgentMail not configured \u2014 set AGENTMAIL_API_KEY and AGENTMAIL_INBOX_ID")
        return False

    # Email verification before send
    try:
        from app.skills.email_verifier import verify_email
        v = await verify_email(lead.email)
        if not v["deliverable"]:
            log.info("Skipping undeliverable email: %s", lead.email)
            return False
    except Exception as exc:
        log.warning("Email verify error for %s: %s", lead.email, exc)

    if personalize:
        subject, body = await generate_personalized_email(lead)
    else:
        cat_line = f" in the {lead.category} space" if lead.category else ""
        subject = DEFAULT_SUBJECT.format(business_name=lead.business_name)
        body = DEFAULT_BODY.format(
            owner_name=lead.owner_name or "there",
            business_name=lead.business_name,
            category_line=cat_line,
            from_name=settings.agentmail_from_name,
        )

    # Rate limit before sending
    await limiters.acquire("agentmail_send", timeout_s=60)

    try:
        client = get_agentmail_client()
        response = await client.inboxes.messages.send(
            settings.agentmail_inbox_id,
            to=lead.email,
            subject=subject,
            text=body,
        )
        log.info(
            "AgentMail sent to %s \u2014 thread_id=%s",
            lead.email, response.thread_id,
        )

        # Persist thread_id so follow-ups can reply in-thread
        from app.core.database import get_session_factory, LeadModel
        from sqlalchemy import update

        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                update(LeadModel)
                .where(LeadModel.email == lead.email)
                .values(
                    outreach_status="sent",
                    last_contacted_at=datetime.utcnow(),
                    notes=f"agentmail_thread:{response.thread_id}",
                )
            )
            await session.commit()

        return True

    except Exception as exc:
        log.error("AgentMail send error for %s: %s", lead.email, exc, exc_info=True)
        return False


# ── Batch send ────────────────────────────────────────────────────────────────

async def send_outreach_batch(leads: list, concurrency: int = 3) -> dict:
    """
    Send outreach to a batch of leads with rate limiting.
    AgentMail handles deliverability \u2014 concurrency of 3 is safe.
    """
    sem = asyncio.Semaphore(concurrency)
    sent = skipped = failed = 0

    async def _bounded(lead) -> None:
        nonlocal sent, skipped, failed
        async with sem:
            if not lead.email:
                skipped += 1
                return
            # Human-like delay between sends
            await asyncio.sleep(random.uniform(3, 10))
            result = await send_outreach(lead)
            if result is True:
                sent += 1
            elif result is None:
                skipped += 1   # outside business hours
            else:
                failed += 1

    await asyncio.gather(*[_bounded(l) for l in leads])
    stats = {"sent": sent, "failed": failed, "skipped": skipped, "total": len(leads)}
    log.info("Outreach batch complete: %s", stats)
    return stats