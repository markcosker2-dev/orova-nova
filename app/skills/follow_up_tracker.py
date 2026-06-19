"""
app/skills/follow_up_tracker.py — AgentMail Follow-Up Sequences
Sends follow-ups as replies inside the original AgentMail thread.
Sequence: Day 3 → Day 7 → Day 14 → archive
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import select, update

from app.config import settings
from app.core.business_hours import is_business_hours
from app.core.database import LeadModel, get_session_factory

log = logging.getLogger("follow_up_tracker")

FOLLOW_UP_SCHEDULE = [3, 7, 14]
MAX_FOLLOW_UPS = len(FOLLOW_UP_SCHEDULE)

FOLLOW_UP_BODIES = [
    """Hi {owner_name},

Just bumping this in case it got buried. Are you currently looking to bring in more clients for {business_name}?

{from_name}""",

    """Hi {owner_name},

I reached out last week about helping {business_name} get more clients. If now isn't a good time, no worries — just let me know.

But if you'd like to explore what's possible, a 15-minute call is all it takes.

{from_name}""",

    """Hi {owner_name},

This will be my last follow-up — I don't want to clog your inbox.

If growing {business_name}'s client base becomes a priority down the road, feel free to reach out anytime.

Wishing you a great month ahead.

{from_name}""",
]


def _extract_thread_id(lead: LeadModel) -> str | None:
    """Pull AgentMail thread_id stored in lead.notes field."""
    if not lead.notes:
        return None
    for part in lead.notes.split(";"):
        if part.strip().startswith("agentmail_thread:"):
            return part.strip().split(":", 1)[1]
    return None


async def get_leads_due_for_followup() -> list[LeadModel]:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(LeadModel).where(
                LeadModel.outreach_status == "sent",
                LeadModel.follow_up_count < MAX_FOLLOW_UPS,
                LeadModel.email.isnot(None),
                LeadModel.last_contacted_at.isnot(None),
            )
        )
        all_leads = result.scalars().all()

    due = []
    now = datetime.utcnow()
    for lead in all_leads:
        days_to_wait = FOLLOW_UP_SCHEDULE[lead.follow_up_count]
        next_send = lead.last_contacted_at + timedelta(days=days_to_wait)
        if now >= next_send:
            due.append(lead)

    log.info("Found %d leads due for follow-up", len(due))
    return due


async def send_follow_up(lead: LeadModel) -> bool:
    """
    Send the next follow-up as a reply in the original AgentMail thread.
    Falls back to a fresh send if no thread_id is stored.
    """
    if not is_business_hours():
        return False

    if not settings.agentmail_api_key or not settings.agentmail_inbox_id:
        log.error("AgentMail not configured")
        return False

    count = lead.follow_up_count
    if count >= MAX_FOLLOW_UPS:
        return False

    body = FOLLOW_UP_BODIES[count].format(
        owner_name=lead.owner_name or "there",
        business_name=lead.business_name,
        from_name=settings.agentmail_from_name,
    )

    try:
        import agentmail as am
        client = am.AsyncAgentMail(api_key=settings.agentmail_api_key)
        thread_id = _extract_thread_id(lead)

        if thread_id:
            # Get the last message_id in the thread to reply to
            thread = await client.inboxes.threads.get(
                settings.agentmail_inbox_id,
                thread_id,
            )
            last_msg_id = thread.last_message_id
            await client.inboxes.messages.reply(
                settings.agentmail_inbox_id,
                last_msg_id,
                text=body,
            )
            log.info(
                "Follow-up %d/%d replied in thread %s for %s",
                count + 1, MAX_FOLLOW_UPS, thread_id, lead.business_name,
            )
        else:
            # No thread_id — send fresh
            log.warning(
                "No thread_id for %s — sending fresh follow-up", lead.business_name
            )
            subject = f"Re: Growing {lead.business_name}"
            await client.inboxes.messages.send(
                settings.agentmail_inbox_id,
                to=lead.email,
                subject=subject,
                text=body,
            )

        # Update lead status
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(
                update(LeadModel)
                .where(LeadModel.id == lead.id)
                .values(
                    follow_up_count=count + 1,
                    last_contacted_at=datetime.utcnow(),
                    outreach_status=(
                        "archived" if count + 1 >= MAX_FOLLOW_UPS else "sent"
                    ),
                )
            )
            await session.commit()

        return True

    except Exception as exc:
        log.error("Follow-up error for %s: %s", lead.business_name, exc, exc_info=True)
        return False


async def run_follow_up_lane() -> dict:
    due = await get_leads_due_for_followup()
    if not due:
        return {"sent": 0, "skipped": 0, "total": 0}

    sem = asyncio.Semaphore(2)
    sent = skipped = 0

    async def _bounded(lead: LeadModel) -> None:
        nonlocal sent, skipped
        async with sem:
            await asyncio.sleep(random.uniform(3, 10))
            if await send_follow_up(lead):
                sent += 1
            else:
                skipped += 1

    await asyncio.gather(*[_bounded(l) for l in due])
    stats = {"sent": sent, "skipped": skipped, "total": len(due)}
    log.info("Follow-up lane complete: %s", stats)
    return stats