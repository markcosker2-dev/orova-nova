# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Instagram Content Creator Agent
Generates social media content for OROVA's brand across verticals.
"""

import os
import json
import logging
import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class InstagramAgent:
    """
    AI-powered Instagram content creator for OROVA.
    Generates captions, hashtags, content calendars, and image prompts.
    """

    def __init__(self, api_key: str = None):
        self.client = None
        self.model_id = 'gemini-2.5-flash'
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
                logger.info("Instagram Agent: AI Ready (google.genai)")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

        # Output directory
        self.output_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "content_queue"
        )
        Path(self.output_dir).mkdir(exist_ok=True)

    def generate_weekly_calendar(self, vertical: str = "general") -> dict:
        """Generate a 7-day content calendar for OROVA."""
        if not self.client:
            return {"error": "AI model not available"}

        prompt = f"""
You are the social media strategist for OROVA, an AI-powered lead generation agency.
OROVA helps high-ticket service businesses ({vertical}) get more clients using AI.

Create a 7-day Instagram content calendar starting from tomorrow.

BRAND VOICE:
- Premium, tech-forward, results-driven
- Speak to business OWNERS, not consumers
- Show the "behind the scenes" of AI automation
- Mix of educational, social proof, and personality content

CONTENT MIX (per week):
- 2x Educational (tips, insights, industry knowledge)
- 2x Social Proof (results, testimonials, case studies)
- 1x Behind the Scenes (OROVA's tech, team, process)
- 1x Engagement (polls, questions, controversial takes)
- 1x Aspirational (luxury lifestyle, success mindset)

For EACH day, provide:
1. Post type (Reel, Carousel, Single Image, Story Series)
2. Caption (under 150 words, with a hook in the first line)
3. Hashtag set (15-20 relevant hashtags)
4. Image/visual description for AI generation
5. Best posting time (PST)

Return as JSON array with 7 objects:
[
  {{
    "day": "Monday",
    "date": "2026-02-16",
    "post_type": "Reel",
    "caption": "...",
    "hashtags": ["#tag1", "#tag2"],
    "visual_prompt": "Description for AI image generation",
    "post_time": "10:00 AM PST",
    "content_category": "Educational"
  }}
]
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_id, contents=prompt
            )
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Calendar generation failed: {e}")
            return {"error": str(e)}

    def generate_post(self, topic: str, post_type: str = "Single Image",
                      vertical: str = "general") -> dict:
        """Generate a single Instagram post."""
        if not self.client:
            return {"error": "AI model not available"}

        prompt = f"""
Create an Instagram {post_type} post for OROVA about: "{topic}"

OROVA is an AI-powered lead generation agency serving {vertical} businesses.

REQUIREMENTS:
- Hook in the first line (pattern interrupt)
- Caption under 150 words
- 15-20 relevant hashtags
- Visual description for AI image/video generation
- Call-to-action at the end

Return JSON:
{{
    "caption": "Full caption with hook and CTA",
    "hashtags": ["#hashtag1", "#hashtag2"],
    "visual_prompt": "Description for AI image generation",
    "post_type": "{post_type}",
    "carousel_slides": ["slide 1 text", "slide 2 text"] if carousel else null
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_id, contents=prompt
            )
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"Post generation failed: {e}")
            return {"error": str(e)}

    def generate_hashtag_strategy(self, vertical: str = "general") -> dict:
        """Generate optimized hashtag sets per content category."""
        if not self.client:
            return {"error": "AI model not available"}

        prompt = f"""
Create a comprehensive hashtag strategy for OROVA targeting {vertical} businesses.

Provide 4 hashtag sets (each 15-20 tags):
1. "brand" - OROVA's brand-specific hashtags
2. "industry" - {vertical} industry hashtags
3. "growth" - Business growth / lead gen hashtags
4. "ai_tech" - AI / automation / tech hashtags

Mix of:
- High volume (500K+ posts) for reach
- Medium volume (50K-500K) for discovery
- Low volume / niche (under 50K) for targeting

Return JSON:
{{
    "brand": ["#OROVA", "#OROVAagency", ...],
    "industry": ["#...", ...],
    "growth": ["#...", ...],
    "ai_tech": ["#...", ...]
}}
"""
        try:
            response = self.client.models.generate_content(
                model=self.model_id, contents=prompt
            )
            text = response.text.replace('```json', '').replace('```', '').strip()
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    def save_content(self, content: dict, filename: str = None):
        """Save generated content to the queue."""
        if filename is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"content_{timestamp}.json"

        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)

        logger.info(f"Content saved: {filepath}")
        return filepath

    def preview_calendar(self, calendar: list):
        """Pretty-print a content calendar."""
        if isinstance(calendar, dict) and "error" in calendar:
            print(f"❌ Error: {calendar['error']}")
            return

        print("\n" + "="*60)
        print("📅 OROVA INSTAGRAM CONTENT CALENDAR")
        print("="*60)

        for day in calendar:
            print(f"\n📌 {day.get('day', '?')} ({day.get('date', '?')})")
            print(f"   Type: {day.get('post_type', '?')} | {day.get('content_category', '?')}")
            print(f"   Time: {day.get('post_time', '?')}")
            caption = day.get('caption', '')[:100]
            print(f"   Caption: {caption}...")
            tags = day.get('hashtags', [])[:5]
            print(f"   Tags: {' '.join(tags)}...")
            print(f"   Visual: {day.get('visual_prompt', '')[:80]}...")


if __name__ == "__main__":
    import sys

    agent = InstagramAgent()
    mode = sys.argv[1] if len(sys.argv) > 1 else "calendar"
    vertical = sys.argv[2] if len(sys.argv) > 2 else "high-ticket services"

    print(f"\n📸 OROVA Instagram Agent — Mode: {mode}\n")

    if mode == "calendar":
        calendar = agent.generate_weekly_calendar(vertical)
        agent.preview_calendar(calendar)
        agent.save_content(calendar, "weekly_calendar.json")

    elif mode == "post":
        topic = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "Why AI cold calling outperforms human SDRs"
        post = agent.generate_post(topic, vertical=vertical)
        print(json.dumps(post, indent=2))
        agent.save_content(post)

    elif mode == "hashtags":
        strategy = agent.generate_hashtag_strategy(vertical)
        print(json.dumps(strategy, indent=2))
        agent.save_content(strategy, "hashtag_strategy.json")

    else:
        print("Usage:")
        print("  python instagram_agent.py calendar [vertical]")
        print("  python instagram_agent.py post <topic>")
        print("  python instagram_agent.py hashtags [vertical]")
