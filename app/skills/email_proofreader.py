import logging
import json
import os
import re
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)


def _send_telegram_alert(message: str):
    """Send alert to Telegram when proofreader fails."""
    try:
        import requests
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("PERSONAL_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
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
    Checks: grammar, tone, personalization, spam triggers, CAN-SPAM compliance.
    Returns:
        dict containing:
            "verdict": "pass", "rewrite", or "reject"
            "score": float (0-100)
            "fixes": str (explanation of fixes)
            "improved_subject": str (revised subject line if rewrite/pass)
            "improved_body": str (revised body text if rewrite/pass)
    """
    logger.info(f"[PROOFREADER] Quality checking email to {to}")
    
    prompt = f"""
    You are an expert copywriter and email compliance officer. 
    Proofread and evaluate the following cold outreach email.
    
    RECIPIENT INFO:
    Email address: {to}
    Recipient Context: {recipient_context}
    
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
        _send_telegram_alert(alert_msg)
        return {
            "verdict": "reject",
            "score": 0.0,
            "fixes": f"BLOCKED: Proofreader failed — email not sent. {e}",
            "improved_subject": subject,
            "improved_body": body
        }
