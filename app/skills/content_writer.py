import logging

logger = logging.getLogger(__name__)


async def write_content(topic: str, content_type: str = "email") -> str:
    """
    Generate marketing content for OROVA.
    Inspired by awesome-claude-skills/content-research-writer.
    
    Types: email, blog, newsletter, social, script
    """
    logger.info(f"[CONTENT WRITER] Writing {content_type} about: {topic}")

    templates = {
        "email": _email_template(topic),
        "blog": _blog_template(topic),
        "newsletter": _newsletter_template(topic),
        "social": _social_template(topic),
        "script": _script_template(topic),
    }

    content = templates.get(content_type, templates["email"])
    return content


async def optimize_post(text: str, platform: str = "twitter") -> str:
    """
    Optimize a post for a specific social platform.
    Inspired by awesome-claude-skills/twitter-algorithm-optimizer.
    
    Platforms: twitter, linkedin, instagram, facebook
    """
    logger.info(f"[CONTENT WRITER] Optimizing for {platform}")

    tips = {
        "twitter": {
            "max_chars": 280,
            "tips": [
                "Keep under 280 chars",
                "Use 1-2 hashtags max",
                "Start with a hook (question or bold statement)",
                "Add a call-to-action",
                "Use line breaks for readability",
            ],
            "format": "hook"
        },
        "linkedin": {
            "max_chars": 3000,
            "tips": [
                "Start with a compelling first line (visible in feed)",
                "Use short paragraphs (1-2 sentences)",
                "Add relevant hashtags at the end (3-5)",
                "Include a personal story or insight",
                "End with a question to drive engagement",
            ],
            "format": "story"
        },
        "instagram": {
            "max_chars": 2200,
            "tips": [
                "First line is crucial (shown in feed preview)",
                "Use emojis strategically",
                "Include 20-30 hashtags in first comment",
                "Add a clear CTA",
                "Use carousel posts for higher engagement",
            ],
            "format": "visual"
        },
        "facebook": {
            "max_chars": 63206,
            "tips": [
                "Shorter posts perform better (under 80 chars ideal)",
                "Ask questions to boost engagement",
                "Use images or video",
                "Post during peak hours",
            ],
            "format": "conversational"
        }
    }

    platform_info = tips.get(platform, tips["twitter"])

    result = f"# Post Optimization for {platform.title()}\n\n"
    result += f"## Original Text\n{text}\n\n"
    result += f"## Platform Tips ({platform.title()})\n"
    for tip in platform_info["tips"]:
        result += f"- {tip}\n"
    result += f"\n## Character Count: {len(text)}/{platform_info['max_chars']}\n"

    if len(text) > platform_info["max_chars"]:
        result += f"\n[!] WARNING: Text exceeds {platform.title()} limit by {len(text) - platform_info['max_chars']} chars.\n"
        result += f"Suggested trim: {text[:platform_info['max_chars']]}...\n"
    else:
        result += f"[OK] Text is within {platform.title()} limits.\n"

    result += f"\n## Suggested Format: {platform_info['format']}\n"
    return result


def _email_template(topic):
    return f"""# Cold Outreach Email Draft

**Subject Line Options:**
1. Quick question about {topic}
2. {topic} - thought you'd want to see this
3. Can we help with {topic}?

**Body:**
Hi [Name],

I noticed [specific observation about their business]. At OROVA, we specialize in {topic} and have helped businesses like yours [specific benefit].

Would you be open to a 15-minute call this week?

Best,
Mark Cosker
OROVA

**Notes:** Personalize the [bracketed] sections for each lead."""


def _blog_template(topic):
    return f"""# Blog Post Outline: {topic}

## Title Ideas:
1. The Ultimate Guide to {topic} in 2025
2. How {topic} Is Changing the Game
3. 5 Things You Need to Know About {topic}

## Structure:
- **Hook** (2-3 sentences): Start with a surprising stat or question
- **Problem** (1 paragraph): What pain point does this address?
- **Solution** (3-5 paragraphs): Your insights and expertise
- **Case Study** (1-2 paragraphs): Real example or social proof
- **CTA** (1 paragraph): What should the reader do next?

## SEO Keywords to Include:
- {topic}
- {topic} services
- best {topic}
- {topic} near me

Draft the full article based on this outline."""


def _newsletter_template(topic):
    return f"""# Newsletter Draft: {topic}

**Subject:** This week at OROVA: {topic}

## Sections:
1. **Featured Story**: {topic} - key insights
2. **Tip of the Week**: Actionable advice related to {topic}
3. **Client Spotlight**: Success story
4. **What's Coming**: Preview of upcoming content

Keep each section to 2-3 sentences max. Use bullet points."""


def _social_template(topic):
    return f"""# Social Media Post Drafts: {topic}

## Twitter/X (280 chars):
{topic} is transforming how businesses grow. Here's what smart companies are doing differently. [Thread]

## LinkedIn:
I've been thinking about {topic} a lot lately.

Here's what I've learned working with dozens of businesses:

1. [Insight 1]
2. [Insight 2]
3. [Insight 3]

What's your experience with {topic}?

## Instagram Caption:
The future of {topic} is here. Swipe to see how we're helping businesses level up. 

#OROVA #{topic.replace(' ', '')} #BusinessGrowth"""


def _script_template(topic):
    return f"""# Sales Call Script: {topic}

## Opening (10 seconds):
"Hey [Name], it's Mark from OROVA. Got a minute?"

## Hook (15 seconds):
"I was looking at your [website/social] and noticed [observation]. We help businesses like yours with {topic}."

## Value Prop (20 seconds):
"We've helped [X] companies increase [metric] by [result]. I think we could do the same for you."

## Ask (10 seconds):
"Would you be open to me sending over a quick proposal?"

## Objection Handlers:
- "Not interested" -> "Totally get it. Mind if I ask what your current approach to {topic} is?"
- "Send me info" -> "Absolutely. What email should I use? I'll send a one-pager."
- "Already have someone" -> "Nice. Out of curiosity, are they getting you [specific result]?"

## Close:
"Great talking to you. I'll follow up [day]. Have a good one." """
