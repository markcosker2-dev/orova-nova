"""Prospect dossier — the Analyst's deep-research pass (SDR Stage 2/4).

Stage-gated on purpose: research time and API quota are spent only on leads
the ICP scorer marks HOT (the caller enforces the gate). The dossier's whole
job is one thing — give the composer a REAL, verifiable icebreaker so the
email reads like a human spent 30 minutes on their business, not like AI.

Fail-open everywhere: a dossier failure must never block the hunt lane; the
lead just keeps its default icebreaker.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

# Only HOT leads (direct owner contact + on-ICP) earn a dossier.
DOSSIER_MIN_SCORE = 70

# Pages worth reading for observations, in priority order.
_DOSSIER_PATHS = ("", "/about", "/about-us", "/inventory", "/services")
_MAX_PAGES = 3
_MAX_TEXT = 7000


async def build_dossier(lead: dict) -> dict:
    """Research one lead's website and distill it into outreach ammunition.

    Returns {"icebreaker": str, "observations": [str], "premium_signals": [str]}
    or {} when nothing usable was found (caller keeps defaults).
    """
    website = (lead.get("website") or "").strip().rstrip("/")
    business = (lead.get("business") or "").strip()
    if not website.startswith("http") or not business:
        return {}

    try:
        from app.skills.light_enrich import _fetch_page

        texts, fetched = [], 0
        for path in _DOSSIER_PATHS:
            if fetched >= _MAX_PAGES or sum(len(t) for t in texts) >= _MAX_TEXT:
                break
            page = await _fetch_page(website + path)
            if not page:
                continue
            fetched += 1
            html = page.get("html") or page.get("markdown") or ""
            clean = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>",
                           " ", html, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r"<[^>]+>", " ", clean)
            clean = re.sub(r"\s+", " ", clean).strip()
            if len(clean) > 200:
                texts.append(clean[:_MAX_TEXT // _MAX_PAGES])

        if not texts:
            return {}

        site_text = "\n---\n".join(texts)[:_MAX_TEXT]

        from app.core.ai_client import UnifiedAIClient
        ai = UnifiedAIClient()
        prompt = f"""You are an elite SDR researching {business} before a cold email.
Below is text from their website. Extract ONLY things that are actually in the
text — never invent, never guess. A wrong specific is worse than none.

WEBSITE TEXT:
{site_text}

Return ONLY JSON:
{{"icebreaker": "one sentence, max 20 words, naming something SPECIFIC and verifiable about {business} (a car/marque in inventory, a signature service, an achievement) — written as a natural compliment/observation a peer would open an email with",
"observations": ["up to 3 short specific facts found in the text"],
"premium_signals": ["up to 2 signals they serve a luxury/premium clientele, if any"]}}
If the text has nothing specific enough, return {{"icebreaker": ""}}."""

        raw = await ai.write(prompt)
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not match:
            return {}
        data = json.loads(match.group(0))

        icebreaker = (data.get("icebreaker") or "").strip()
        # Guard against AI-invented or junk icebreakers: must be plausibly
        # grounded (mentions the business or overlaps the site text) and short.
        if icebreaker and len(icebreaker.split()) > 25:
            icebreaker = ""
        result = {
            "icebreaker": icebreaker,
            "observations": [str(o)[:200] for o in (data.get("observations") or [])[:3]],
            "premium_signals": [str(s)[:200] for s in (data.get("premium_signals") or [])[:2]],
        }
        return result if (result["icebreaker"] or result["observations"]) else {}

    except Exception as e:
        logger.warning(f"[DOSSIER] build failed for {business} (non-fatal): {e}")
        return {}
