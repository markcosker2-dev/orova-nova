# -*- coding: utf-8 -*-
"""
OROVA Copywriting Skill — Marketing Psychology Frameworks
Inspired by OpenClaw Master Skills: copywriting + marketing-psychology

Generates high-converting copy using proven frameworks:
AIDA, PAS, Before-After-Bridge, Story-Brand, 4Ps
"""

import asyncio
import logging
from typing import Optional
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

_ai_client: Optional[UnifiedAIClient] = None

def _get_ai() -> UnifiedAIClient:
    global _ai_client
    if _ai_client is None:
        _ai_client = UnifiedAIClient()
    return _ai_client

FRAMEWORKS = {
    "aida": {
        "name": "AIDA (Attention-Interest-Desire-Action)",
        "structure": ["Attention", "Interest", "Desire", "Action"],
        "prompt_template": (
            "Write a {content_type} for {company} using the AIDA framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Target audience: {audience}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. ATTENTION: Open with a hook that stops them scrolling. Use a shocking stat, bold claim, or pattern interrupt.\n"
            "2. INTEREST: Explain the problem they face. Make them feel seen and understood.\n"
            "3. DESIRE: Paint the transformation. Show results, case studies, and social proof.\n"
            "4. ACTION: Clear, single CTA with urgency. Make it impossible to say no.\n\n"
            "RULES:\n"
            "- Write like Alex Hormozi, not a corporate drone\n"
            "- Max 150 words for emails, 250 words for landing pages\n"
            "- Every sentence must earn its place\n"
            "- Use specific numbers, not vague promises"
        )
    },
    "pas": {
        "name": "PAS (Problem-Agitate-Solve)",
        "structure": ["Problem", "Agitate", "Solve"],
        "prompt_template": (
            "Write a {content_type} for {company} using the PAS framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Target audience: {audience}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. PROBLEM: Identify the EXACT pain point. Be specific. 'You're leaving money on the table because...' \n"
            "2. AGITATE: Twist the knife. Show what happens if they do nothing. Make the status quo painful.\n"
            "3. SOLVE: Present OROVA as the inevitable solution. Include proof, guarantee, and CTA.\n\n"
            "RULES:\n"
            "- Start with the pain, not the product\n"
            "- Use 'you' language, not 'we' language\n"
            "- Include at least one concrete result (number, percentage, timeframe)"
        )
    },
    "bab": {
        "name": "Before-After-Bridge",
        "structure": ["Before", "After", "Bridge"],
        "prompt_template": (
            "Write a {content_type} for {company} using the Before-After-Bridge framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Target audience: {audience}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. BEFORE: Paint their current reality. The frustration, wasted time, lost revenue.\n"
            "2. AFTER: Show the dream state. What life looks like with OROVA. Leads flowing, calendar full, revenue up.\n"
            "3. BRIDGE: Show exactly how to get from Before to After. OROVA is the bridge. CTA.\n\n"
            "RULES:\n"
            "- Make 'Before' emotionally resonant\n"
            "- Make 'After' specific and measurable\n"
            "- Bridge must be simple (3 steps max)"
        )
    },
    "story_brand": {
        "name": "StoryBrand (Hero's Journey)",
        "structure": ["Hero", "Problem", "Guide", "Plan", "CTA", "Success", "Failure"],
        "prompt_template": (
            "Write a {content_type} for {company} using the StoryBrand framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Target audience: {audience}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE (Hero's Journey):\n"
            "1. HERO: The prospect is the hero, not us. Acknowledge their goals.\n"
            "2. PROBLEM: External (no leads), Internal (frustrated), Philosophical (they deserve better).\n"
            "3. GUIDE: OROVA as the wise guide (Yoda, not Luke). Show empathy + authority.\n"
            "4. PLAN: 3 simple steps to work with us.\n"
            "5. CTA: Direct ('Book a call') or transitional ('Download the guide').\n"
            "6. SUCCESS: What winning looks like.\n"
            "7. FAILURE: What they risk by not acting.\n\n"
            "RULES:\n"
            "- The prospect is always the hero\n"
            "- Position OROVA as the guide with the plan\n"
            "- Keep the plan to exactly 3 steps"
        )
    },
    "4ps": {
        "name": "4Ps (Promise-Picture-Proof-Push)",
        "structure": ["Promise", "Picture", "Proof", "Push"],
        "prompt_template": (
            "Write a {content_type} for {company} using the 4Ps framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Target audience: {audience}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. PROMISE: Bold, specific promise. '3x your leads in 60 days.'\n"
            "2. PICTURE: Help them visualize the result. 'Imagine opening your inbox to 15 qualified leads every morning.'\n"
            "3. PROOF: Testimonials, case studies, data. 'We did this for XYZ Company.'\n"
            "4. PUSH: Urgency + CTA. 'We only take 3 new clients per month. Book your slot.'\n\n"
            "RULES:\n"
            "- Promise must be measurable\n"
            "- Picture must be vivid and sensory\n"
            "- Proof must be specific (names, numbers, timeframes)\n"
            "- Push must include scarcity or urgency"
        )
    },
    "sales_problem_first": {
        "name": "Problem-First Sales (Sales Guide)",
        "structure": ["Observation", "Pain-Point", "Value-Prop", "CTA"],
        "prompt_template": (
            "Write a {content_type} for {company} using the Problem-First framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. HOOK: Specific observation about their company or recent news.\n"
            "2. PROBLEM: Ask how they currently handle [pain point]. Mention that similar teams struggle with [specific challenge].\n"
            "3. VALUE: Briefly explain how {offer} solves exactly that.\n"
            "4. ASK: Clear, low-friction next step (e.g., 15-min call).\n\n"
            "PERSONALIZATION CHECKLIST (MUST PASS):\n"
            "- Reference something specific about the prospect's company.\n"
            "- Pain point must be tailored, not generic.\n"
            "- Under 100 words.\n"
            "- Exactly one clear CTA.\n"
            "- Correct names and company details."
        )
    },
    "sales_social_proof": {
        "name": "Social Proof Sales (Sales Guide)",
        "structure": ["Similar-Company", "Outcome", "Soft-Ask"],
        "prompt_template": (
            "Write a {content_type} for {company} using the Social Proof framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. HOOK: Mention a similar company dealing with [pain point].\n"
            "2. PROOF: We helped them [specific outcome/metric] in [timeframe].\n"
            "3. ASK: If [pain point] is on your radar, might be worth a quick chat? 15 mins this week?\n\n"
            "RULES:\n"
            "- Conversational, not corporate.\n"
            "- Curious, not pushy.\n"
            "- Personalization over volume."
        )
    },
    "sales_straight_pitch": {
        "name": "Straight Pitch Sales (Sales Guide)",
        "structure": ["Company-Help", "Proof", "Direct-Ask"],
        "prompt_template": (
            "Write a {content_type} for {company} using the Straight Pitch framework.\n\n"
            "CONTEXT:\n"
            "- Company: {company}\n"
            "- Industry: {industry}\n"
            "- Offer: {offer}\n\n"
            "STRUCTURE:\n"
            "1. HOOK: Your company helps {industry} with [problem].\n"
            "2. PROOF: We work with [3-4 similar companies]. Typical results: [outcome].\n"
            "3. ASK: Direct ask for a call or calendar link.\n\n"
            "RULES:\n"
            "- Keep it short. Busy people skim.\n"
            "- Pitch outcomes, not features."
        )
    }
}

async def write_cold_email(
    prospect: str,
    framework: str = "pas",
    industry: str = "business services",
    offer: str = "AI-powered lead generation"
) -> str:
    """Generate a cold email using a marketing psychology framework.
    
    When framework='auto', consults learned_strategies to pick the best
    performing framework (self-improvement loop integration).
    """
    # ── Self-improvement: Consult learned strategies ──
    if framework == "auto":
        try:
            loop = asyncio.get_event_loop()
            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    best = pool.submit(lambda: asyncio.run(_pick_best_copy_framework())).result()
            else:
                best = asyncio.run(_pick_best_copy_framework())
            if best:
                framework = best
                logger.info(f"[COPYWRITING] Auto-selected framework '{best}' from learned strategies")
        except Exception as e:
            logger.warning(f"[COPYWRITING] Could not consult learned_strategies: {e}")
    
    fw = FRAMEWORKS.get(framework, FRAMEWORKS["pas"])
    logger.info(f"[COPYWRITING] Generating cold email via {fw['name']} for {prospect}")

    prompt = fw["prompt_template"].format(
        content_type="cold outreach email",
        company=prospect,
        industry=industry,
        audience=f"decision makers at {industry} businesses",
        offer=offer
    )

    try:
        result = await _get_ai().write(prompt)

        report = f"# ✍️ Cold Email — {fw['name']}\n"
        report += f"**Target:** {prospect} ({industry})\n"
        report += f"**Framework:** {framework.upper()}\n"
        report += f"**Offer:** {offer}\n\n"
        report += f"---\n\n{result}\n\n---\n"
        report += f"📋 **Structure used:** {' → '.join(fw['structure'])}\n"
        return report
    except Exception as e:
        logger.error(f"[COPYWRITING] AI generation failed: {e}")
        return _template_fallback(fw, prospect, industry, offer)

async def write_ad_copy(
    offer: str,
    platform: str = "facebook",
    industry: str = "business services",
    framework: str = "aida"
) -> str:
    """Generate ad copy for a specific platform."""
    fw = FRAMEWORKS.get(framework, FRAMEWORKS["aida"])
    logger.info(f"[COPYWRITING] Generating {platform} ad via {fw['name']}")

    platform_rules = {
        "facebook": "Max 125 chars for primary text. Include emoji. Hook in first line.",
        "google": "Headline max 30 chars. Description max 90 chars. Include keywords.",
        "linkedin": "Professional tone. Max 150 words. Include industry-specific language.",
        "instagram": "Visual-first. Caption max 125 chars before 'more'. Use 5-10 hashtags.",
    }

    prompt = fw["prompt_template"].format(
        content_type=f"{platform} ad copy",
        company="OROVA",
        industry=industry,
        audience=f"business owners in {industry}",
        offer=offer
    )
    prompt += f"\n\nPLATFORM RULES ({platform.upper()}):\n{platform_rules.get(platform, 'Standard ad copy rules apply.')}"

    try:
        result = await _get_ai().write(prompt)

        report = f"# 📢 {platform.upper()} Ad Copy — {fw['name']}\n"
        report += f"**Offer:** {offer}\n"
        report += f"**Platform:** {platform}\n\n"
        report += f"---\n\n{result}\n"
        return report
    except Exception as e:
        return f"⚠️ Ad copy generation failed: {str(e)}"

def _template_fallback(fw, prospect, industry, offer):
    return (
        f"# ✍️ Cold Email Template — {fw['name']}\n"
        f"**Target:** {prospect} ({industry})\n\n"
        f"---\n\n"
        f"**Subject:** Quick question about {prospect}\n\n"
        f"Hi there,\n\n"
        f"I noticed {prospect} is doing great work in {industry}. "
        f"We specialize in {offer} and have helped similar businesses see 3-5x growth.\n\n"
        f"Would a 15-minute call this week make sense?\n\n"
        f"— Mark, CEO of OROVA\n\n"
        f"---\n"
        f"⚠️ AI unavailable — using template fallback\n"
    )


async def _pick_best_copy_framework() -> str:
    """Query learned_strategies for the best email framework with high confidence."""
    try:
        from app.core.database import DatabaseManager
        row = await DatabaseManager.fetchone(
            """SELECT strategy_value FROM learned_strategies
               WHERE strategy_type = 'email_framework'
                 AND win_rate > 0.15
                 AND confidence = 'high'
                 AND active = 1
               ORDER BY win_rate DESC
               LIMIT 1"""
        )
        if row:
            return row["strategy_value"]
    except Exception as e:
        logger.warning(f"[COPYWRITING] _pick_best_copy_framework failed: {e}")
    return None


async def list_frameworks() -> str:
    report = "# ✍️ Available Copywriting Frameworks\n\n"
    for key, fw in FRAMEWORKS.items():
        report += f"- **`{key}`** — {fw['name']}: {' → '.join(fw['structure'])}\n"
    return report

async def handle_sales_objection(objection: str, prospect_name: str = "there") -> str:
    logger.info(f"[COPYWRITING] Handling objection: {objection}")
    
    prompt = (
        f"Generate a strategic sales response to this objection: '{objection}'\n\n"
        "RULES (SALES GUIDE):\n"
        "- If they ask for PRICE: Do not answer with a price. Steer toward a call to understand their setup.\n"
        "- If they ask for INFO: Do not send a generic PDF. Ask what specifically they are curious about.\n"
        "- If they say 'Not right now': Find out when to check back and what would need to change.\n"
        "- Tone: Conversational, curious, helpful, not pushy.\n"
        "- Max 50 words."
    )
    
    try:
        response = await _get_ai().write(prompt)
        return f"Hi {prospect_name},\n\n{response}"
    except Exception as e:
        return f"Error generating response: {e}"
