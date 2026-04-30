# -*- coding: utf-8 -*-
"""
OROVA Instagram Skill for Nova (OpenClaw)
Allows Nova to generate Instagram content via Telegram commands.
"""

import os
import json
import logging
import sys

# Add parent path for Core_Engine imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logger = logging.getLogger(__name__)


async def create_instagram_post(topic: str, post_type: str = "Single Image") -> str:
    """Generate an Instagram post for OROVA."""
    try:
        from Core_Engine.instagram_agent import InstagramAgent
        agent = InstagramAgent()
        result = agent.generate_post(topic, post_type)

        if "error" in result:
            return f"❌ Error: {result['error']}"

        # Save to queue
        filepath = agent.save_content(result)

        caption = result.get("caption", "")
        hashtags = " ".join(result.get("hashtags", [])[:10])
        visual = result.get("visual_prompt", "")

        return (
            f"📸 **Instagram Post Ready**\n\n"
            f"**Type:** {post_type}\n"
            f"**Caption:**\n{caption}\n\n"
            f"**Hashtags:** {hashtags}\n\n"
            f"**Visual Direction:** {visual}\n\n"
            f"📁 Saved to: `{filepath}`"
        )
    except Exception as e:
        logger.error(f"Instagram post error: {e}")
        return f"❌ Failed: {e}"


async def create_content_calendar(vertical: str = "high-ticket services") -> str:
    """Generate a weekly Instagram content calendar."""
    try:
        from Core_Engine.instagram_agent import InstagramAgent
        agent = InstagramAgent()
        calendar = agent.generate_weekly_calendar(vertical)

        if isinstance(calendar, dict) and "error" in calendar:
            return f"❌ Error: {calendar['error']}"

        filepath = agent.save_content(calendar, "weekly_calendar.json")

        summary_lines = []
        for day in calendar[:7]:
            emoji = {"Reel": "🎬", "Carousel": "📑", "Single Image": "🖼️", "Story Series": "📱"}.get(
                day.get("post_type", ""), "📌"
            )
            summary_lines.append(
                f"{emoji} **{day.get('day', '?')}** — {day.get('content_category', '?')} "
                f"({day.get('post_type', '?')}) at {day.get('post_time', '?')}"
            )

        return (
            f"📅 **OROVA Content Calendar**\n\n"
            + "\n".join(summary_lines) +
            f"\n\n📁 Full calendar saved to: `{filepath}`"
        )
    except Exception as e:
        logger.error(f"Calendar error: {e}")
        return f"❌ Failed: {e}"
