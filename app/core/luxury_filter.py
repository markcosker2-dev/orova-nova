# -*- coding: utf-8 -*-
"""
OROVA Luxury Filter — Planner-Critic-Executor Loop
====================================================
Every sub-agent output is evaluated against the OROVA Luxury Filter
before execution. One failure = rewrite. Three failures = CRITICAL EXCEPTION.

This module implements Nova's internal critique protocol from the MSI.
"""

import logging
import re
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# LUXURY FILTER RULES (from MSI)
# ═══════════════════════════════════════════════════════════════════════════════

# Greeting checks
REJECTED_GREETINGS = [
    r"^hi\s+\w+",
    r"^hello\s+\w+",
    r"^hey\s+\w+",
    r"^dear\s+\w+",
    r"^hello\s+there",
    r"^hi\s+there",
    r"^good\s+(morning|afternoon|evening)",
]

# Punctuation checks
REJECTED_PUNCTUATION = [
    "!",   # Exclamation marks — never
]

REJECTED_EMOJIS_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251]+",
    flags=re.UNICODE
)

# Value proposition language
REJECTED_WORDS = [
    "cheap", "affordable", "quick", "easy", "help you",
    "help your", "helping you", "we help", "we can help",
    "budget-friendly", "low-cost", "discount", "free trial",
    "no-brainer", "game-changer", "revolutionary",
]

# Opening line checks
REJECTED_OPENINGS = [
    "i hope this email finds you well",
    "i hope this finds you well",
    "i came across your website",
    "i came across your company",
    "my name is",
    "i'm reaching out because",
    "i am reaching out because",
    "i wanted to reach out",
    "just wanted to check in",
    "i hope you're doing well",
    "hope you're having a great",
    "hope all is well",
]

# CTA checks
REJECTED_CTAS = [
    "hope to hear from you soon",
    "looking forward to hearing from you",
    "don't hesitate to reach out",
    "feel free to reach out",
    "let me know if you have any questions",
    "looking forward to connecting",
]

# Closing checks
REJECTED_CLOSINGS = [
    "best regards",
    "warm regards",
    "kind regards",
    "cheers",
    "warmly",
    "all the best",
    "sincerely yours",
    "yours truly",
    "with gratitude",
]

# Vocabulary overrides (mandatory replacements)
VOCABULARY_OVERRIDES = {
    "help": "facilitate",
    "quick chat": "strategic alignment",
    "results": "quantifiable outcomes",
    "get leads": "source qualified pipeline",
    "follow up": "complete the loop",
    "follow-up": "loop completion",
    "check in": "conduct a pulse review",
    "checking in": "conducting a pulse review",
    "interested?": "is this a priority in your current cycle?",
}


# ═══════════════════════════════════════════════════════════════════════════════
# CRITIQUE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class LuxuryFilter:
    """
    Nova's internal Critic. Evaluates all outbound content against the
    OROVA Luxury Filter before execution.
    """

    @staticmethod
    def critique(text: str, content_type: str = "email") -> Dict:
        """
        Evaluate text against the Luxury Filter checklist.

        Args:
            text: The content to evaluate
            content_type: "email", "proposal", "call_script", "report"

        Returns:
            Dict with:
                - score (float): 0.0 - 10.0
                - approved (bool): True if score >= 9.5
                - violations (list): List of violation descriptions
                - suggestions (list): Specific revision notes
        """
        violations = []
        suggestions = []
        score = 10.0

        text_lower = text.lower().strip()
        lines = text.strip().split("\n")
        first_line = lines[0].strip().lower() if lines else ""

        # ── Greeting Check ────────────────────────────────────────
        if content_type == "email":
            for pattern in REJECTED_GREETINGS:
                if re.match(pattern, first_line, re.IGNORECASE):
                    violations.append(f"Rejected greeting: '{lines[0].strip()}'")
                    suggestions.append(
                        "Use direct, peer-level greeting: '[Name]—' (em-dash, no warmth theater)"
                    )
                    score -= 2.0
                    break

        # ── Punctuation Check ─────────────────────────────────────
        exclamation_count = text.count("!")
        if exclamation_count > 0:
            violations.append(f"Exclamation marks detected: {exclamation_count} instances")
            suggestions.append("Replace all '!' with periods. OROVA never uses exclamation marks.")
            score -= min(exclamation_count * 0.5, 2.0)

        # ── Emoji Check ───────────────────────────────────────────
        emojis = REJECTED_EMOJIS_PATTERN.findall(text)
        if emojis and content_type in ("email", "proposal"):
            violations.append(f"Emojis detected in {content_type}: {len(emojis)} instances")
            suggestions.append("Remove all emojis from client-facing content.")
            score -= 1.0

        # ── Value Proposition Language ────────────────────────────
        for word in REJECTED_WORDS:
            if word in text_lower:
                violations.append(f"Rejected value prop language: '{word}'")
                suggestions.append(
                    f"Replace '{word}' with premium language (ROI, precision, efficiency, architect, facilitate)"
                )
                score -= 0.5

        # ── Opening Line Check ────────────────────────────────────
        if content_type == "email":
            for opening in REJECTED_OPENINGS:
                if opening in text_lower[:200]:
                    violations.append(f"Rejected opening: '{opening}'")
                    suggestions.append(
                        "Use a timeline hook with a specific result and timeframe. "
                        "Example: 'We sourced 14 qualified renovation consultations for a "
                        "Dallas firm in 30 days—no agency fees, no shared leads.'"
                    )
                    score -= 2.0
                    break

        # ── CTA Check ─────────────────────────────────────────────
        if content_type == "email":
            for cta in REJECTED_CTAS:
                if cta in text_lower:
                    violations.append(f"Rejected CTA: '{cta}'")
                    suggestions.append(
                        "Use one specific, direct CTA: "
                        "'My calendar is open [Day] at [Time] for a brief technical alignment.'"
                    )
                    score -= 1.5
                    break

        # ── Closing Check ─────────────────────────────────────────
        last_lines = "\n".join(lines[-3:]).lower() if len(lines) >= 3 else text_lower
        for closing in REJECTED_CLOSINGS:
            if closing in last_lines:
                violations.append(f"Rejected closing: '{closing}'")
                suggestions.append("Use '— OROVA' or simply the sender's name + title.")
                score -= 1.0
                break

        # ── Word Count Check (emails only) ────────────────────────
        if content_type == "email":
            word_count = len(text.split())
            if word_count > 125:
                violations.append(f"Email too long: {word_count} words (max 125)")
                suggestions.append(f"Cut {word_count - 125} words. Be more concise.")
                score -= 1.0

        # ── Multiple CTAs Check ───────────────────────────────────
        if content_type == "email":
            cta_indicators = [
                "calendar", "schedule", "book", "call me", "reply",
                "click here", "sign up", "register", "visit"
            ]
            cta_count = sum(1 for c in cta_indicators if c in text_lower)
            if cta_count > 2:
                violations.append(f"Multiple CTAs detected: {cta_count} call-to-action indicators")
                suggestions.append("Use exactly ONE CTA per message. Remove all others.")
                score -= 1.0

        # Clamp score
        score = max(0.0, min(10.0, score))

        return {
            "score": round(score, 1),
            "approved": score >= 9.5,
            "violations": violations,
            "suggestions": suggestions,
            "content_type": content_type,
        }

    @staticmethod
    def apply_vocabulary(text: str) -> str:
        """
        Apply mandatory vocabulary overrides from the MSI.
        Case-insensitive replacement preserving sentence flow.
        """
        result = text
        for old, new in VOCABULARY_OVERRIDES.items():
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            result = pattern.sub(new, result)
        return result

    @staticmethod
    def format_critique_report(critique_result: Dict) -> str:
        """Format a critique result as a human-readable report."""
        score = critique_result["score"]
        approved = critique_result["approved"]

        report = f"{'✅ APPROVED' if approved else '❌ REJECTED'} — Elite Score: {score}/10.0\n"

        if critique_result["violations"]:
            report += "\nViolations:\n"
            for v in critique_result["violations"]:
                report += f"  • {v}\n"

        if critique_result["suggestions"]:
            report += "\nRevision Notes:\n"
            for s in critique_result["suggestions"]:
                report += f"  → {s}\n"

        return report


# ═══════════════════════════════════════════════════════════════════════════════
# AI-POWERED REWRITE (Critic Loop)
# ═══════════════════════════════════════════════════════════════════════════════

async def critique_and_rewrite(
    text: str,
    content_type: str = "email",
    ai_client=None,
    max_rewrites: int = 3,
    context: dict = None,
) -> Tuple[str, Dict]:
    """
    Full Planner-Critic-Executor loop.

    1. Critique the text
    2. If score < 9.5, ask AI to rewrite with revision notes
    3. Repeat up to max_rewrites times
    4. Return final text + final critique

    Args:
        text: Original content
        content_type: "email", "proposal", "call_script"
        ai_client: UnifiedAIClient instance for rewrites
        max_rewrites: Max rewrite attempts (default 3)
        context: Optional dict with lead_name, company, vertical, etc.

    Returns:
        Tuple of (final_text, final_critique_dict)
    """
    current_text = text
    final_critique = None

    for attempt in range(max_rewrites + 1):
        critique = LuxuryFilter.critique(current_text, content_type)
        final_critique = critique

        if critique["approved"]:
            logger.info(f"[LUXURY FILTER] Approved on attempt {attempt + 1} — Score: {critique['score']}/10")
            return current_text, critique

        if attempt >= max_rewrites:
            logger.warning(
                f"[LUXURY FILTER] FAILED after {max_rewrites} rewrites — "
                f"Score: {critique['score']}/10. Triggering CRITICAL EXCEPTION."
            )
            break

        # Ask AI to rewrite
        if ai_client:
            logger.info(
                f"[LUXURY FILTER] Rewrite {attempt + 1}/{max_rewrites} — "
                f"Score: {critique['score']}/10, Violations: {len(critique['violations'])}"
            )

            revision_notes = "\n".join(f"- {s}" for s in critique["suggestions"])
            violations = "\n".join(f"- {v}" for v in critique["violations"])

            rewrite_prompt = f"""You are Nova, Executive Director of OROVA. Rewrite this {content_type} to pass the OROVA Luxury Filter.

CURRENT {content_type.upper()} (REJECTED — Score {critique['score']}/10):
---
{current_text}
---

VIOLATIONS:
{violations}

REVISION NOTES:
{revision_notes}

MANDATORY RULES:
- Greeting: Use "[Name]—" (direct, peer-level, em-dash)
- No exclamation marks. No emojis. No "Hi/Hello/Dear".
- No "help", "affordable", "cheap", "easy", "quick chat"
- Opening must be a timeline hook with specific result + timeframe
- One CTA only: "My calendar is open [Day] at [Time] for a brief technical alignment."
- Closing: "— OROVA" or "— Nova, Executive Director, OROVA"
- Max 125 words for emails
- Use em-dashes (—) for emphasis

Return ONLY the rewritten {content_type}. No commentary."""

            try:
                rewritten = await ai_client.write(rewrite_prompt)
                if rewritten and len(rewritten.strip()) > 20:
                    current_text = rewritten.strip()
                else:
                    logger.warning("[LUXURY FILTER] AI returned empty rewrite")
            except Exception as e:
                logger.error(f"[LUXURY FILTER] Rewrite failed: {e}")
                break
        else:
            logger.warning("[LUXURY FILTER] No AI client for rewrites — cannot auto-fix")
            break

    # Apply vocabulary overrides as final pass
    current_text = LuxuryFilter.apply_vocabulary(current_text)

    return current_text, final_critique
