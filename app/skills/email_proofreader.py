import logging
import json
import os
import re
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)


async def _send_telegram_alert(message: str):
    """Send alert to Telegram when proofreader fails."""
    try:
        import httpx
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={"chat_id": chat_id, "text": message}, timeout=10.0)
            if resp.status_code != 200:
                # Sanitize: strip token from any error body before logging
                body = resp.text.replace(token, "***") if token else resp.text
                logger.error(f"Telegram sendMessage failed ({resp.status_code}): {body[:300]}")
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")

async def proofread_email(
    to: str,
    subject: str,
    body: str,
    recipient_context: str = ""
) -> dict:
    """
    Runs outbound emails through an AI proofreading rubric.
    Checks: grammar, tone, personalization, spam triggers, CAN-SPAM compliance, brand consistency.
    Returns:
        dict containing:
            "verdict": "pass", "rewrite", or "reject"
            "score": float (0-100)
            "fixes": str (explanation of fixes)
            "improved_subject": str (revised subject line if rewrite/pass)
            "improved_body": str (revised body text if rewrite/pass)
    """
    logger.info(f"[PROOFREADER] Quality checking email to {to}")
    
    # ── Load business context for brand consistency check ──
    brand_context = ""
    try:
        _ctx_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "business_context.json")
        with open(_ctx_path, "r") as _f:
            _biz = json.load(_f)
        _co = _biz.get("company", {})
        _services = _biz.get("services", [])
        _icp = _biz.get("icp", {})
        _rules = _biz.get("email_rules", {})
        _vp = _biz.get("value_propositions", {})
        brand_context = f"""
BRAND CONTEXT (use to verify brand consistency):
- Company: {_co.get('name', 'OROVA')} — {_co.get('description', 'Marketing agency')}
- Services: {', '.join(s.get('name','') for s in _services)}
- Target: {_icp.get('region', 'West Coast US')}
- NEVER state or imply a price. No dollar figure, no range, no "starts at", no
  retainer, no trial, no discount, and never the word "free". The owner has not
  set an offer; there is nothing to quote. If the draft contains one, REMOVE it
  and deflect the question to Mark — do not "improve" the wording of a number.
- Primary Verticals: {', '.join(_icp.get('primary_verticals', []))}
- Value Prop: {_vp.get('primary', '')}
- Email Tone: {_rules.get('tone', 'Casual and friendly')}
- Sender: {_rules.get('sender_identity', "Nova — real person on Mark's team")}
- Signature: {_rules.get('signature', 'Nova @ OROVA')}
- Max Words: {_rules.get('max_words', 75)}
- Framework: {_rules.get('framework', 'Hook-Value-Ask')}
"""
    except Exception as e:
        logger.warning(f"[PROOFREADER] Could not load business_context.json: {e}")
        brand_context = "BRAND CONTEXT: OROVA is a marketing agency specializing in Meta Ads + lead qualification. Sender is Nova. Signature: Nova @ OROVA. Tone: casual and friendly."
    
    prompt = f"""
    You are an expert copywriter and email compliance officer. 
    Proofread and evaluate the following cold outreach email.
    
    RECIPIENT INFO:
    Email address: {to}
    Recipient Context: {recipient_context}
    
    {brand_context}
    
    EMAIL DRAFT:
    Subject: {subject}
    Body:
    {body}
    
    EVALUATION RUBRIC:
    1. Grammar & Clarity: Check for typos, awkward phrasing, clear value prop.
    2. Personalization: Does it feel generic or customized to the context?
    3. Spam Trigger Words: Avoid words like "free", "guaranteed", "make money", excessive punctuation.
    4. Compliance: Ensure it follows CAN-SPAM (has clear business identity, no deceptive subjects).
    5. Tone: Professional, value-driven, and non-intrusive.
    6. Brand Consistency: Does the email accurately represent OROVA? Check:
       - Sender identity matches (Nova, not Mark, unless booking a call)
       - Signature matches the brand standard
       - Value proposition is accurate (Meta Ads + lead qualification, NOT generic "AI sales" or "$20/month")
       - Target region is West Coast US
       - Tone is casual and friendly, not corporate or salesy
       - Email follows Hook-Value-Ask framework
       - Email is under 75 words
    
    VERDICT LOGIC:
    - PASS: Score >= 80 and passes all critical checks. Needs no edits.
    - REWRITE: Score between 50 and 79. Has minor issues, but can be auto-corrected. Provide the improved version.
    - REJECT: Score < 50 or is highly spammy, deceptive, or offensive. Cannot be auto-saved.
    
    Return a JSON response with the following keys:
    - "verdict": "pass" | "rewrite" | "reject"
    - "score": <numeric score 0 to 100>
    - "fixes": "<bullet list of issues found or 'None'>"
    - "improved_subject": "<improved subject line if rewrite/pass, otherwise keep original>"
    - "improved_body": "<improved email body text if rewrite/pass, otherwise keep original>"
    
    Format the output strictly as a JSON object. Return ONLY the JSON object. Do not include markdown code block formatting (like ```json).
    """

    try:
        ai = UnifiedAIClient()
        response_str = await ai.extract(prompt)
        # Clean up any potential markdown wraps
        response_str = response_str.strip()
        response_str = response_str.replace("```json", "").replace("```", "").strip()
        
        # Try to parse JSON directly first
        try:
            result = json.loads(response_str)
        except json.JSONDecodeError:
            # Fall back: find the FIRST complete JSON object using balanced-brace matching
            import re
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_str, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
            else:
                raise json.JSONDecodeError("No JSON object found", response_str, 0)
        
        # Ensure keys exist
        result["verdict"] = result.get("verdict", "pass").lower()
        result["score"] = float(result.get("score", 85))
        result["fixes"] = result.get("fixes", "None")
        result["improved_subject"] = result.get("improved_subject", subject)
        result["improved_body"] = result.get("improved_body", body)
        
        logger.info(f"[PROOFREADER] Verdict: {result['verdict'].upper()} (Score: {result['score']})")
        return result
    except Exception as e:
        logger.error(f"[PROOFREADER] Evaluation failed: {e}", exc_info=True)
        # BLOCK the email — do not silently pass on failure
        alert_msg = f"⚠️ **PROOFREADER BLOCKED**\nTo: {to}\nSubject: {subject}\nReason: {e}\n*Email was NOT sent.*"
        await _send_telegram_alert(alert_msg)
        return {
            "verdict": "reject",
            "score": 0.0,
            "fixes": f"BLOCKED: Proofreader failed — email not sent. {e}",
            "improved_subject": subject,
            "improved_body": body
        }
