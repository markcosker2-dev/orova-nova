"""
Lead Validation & Scoring for Meta Lead Gen Agency
Validates email/phone before cold outreach and scores leads for prioritization.
"""
import re
import logging
from email_validator import validate_email, EmailNotValidError
import phonenumbers

logger = logging.getLogger(__name__)

def validate_email_address(email: str) -> dict:
    """Validate email format and deliverability."""
    try:
        valid = validate_email(email)
        return {"valid": True, "email": valid.email, "normalized": str(valid)}
    except EmailNotValidError as e:
        logger.warning(f"[Validator] Invalid email {email}: {e}")
        return {"valid": False, "email": email, "reason": str(e)}

def validate_phone_number(phone: str, country_code: str = "US") -> dict:
    """Validate and normalize international phone number."""
    try:
        parsed = phonenumbers.parse(phone, country_code)
        if phonenumbers.is_valid_number(parsed):
            formatted = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            return {"valid": True, "phone": formatted, "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)}
        else:
            return {"valid": False, "phone": phone, "reason": "Invalid format for region"}
    except phonenumbers.NumberParseException as e:
        logger.warning(f"[Validator] Invalid phone {phone}: {e}")
        return {"valid": False, "phone": phone, "reason": str(e)}

def validate_contact(email: str = None, phone: str = None, country: str = "US") -> dict:
    """
    Validate both email and phone. Returns combined result.
    Use before sending cold outreach to ensure contact validity.
    """
    result = {"email_valid": False, "phone_valid": False, "contact_valid": False}
    
    if email:
        email_result = validate_email_address(email)
        result["email_valid"] = email_result["valid"]
        result["email_normalized"] = email_result.get("email")
    
    if phone:
        phone_result = validate_phone_number(phone, country)
        result["phone_valid"] = phone_result["valid"]
        result["phone_formatted"] = phone_result.get("phone")
    
    # Lead is "valid to contact" if at least one channel is valid
    result["contact_valid"] = result["email_valid"] or result["phone_valid"]
    return result


# ─── LEAD SCORING ───────────────────────────────────────────────────────
# Simple rule-based + ML-ready scoring for lead prioritization

def score_lead(company_name: str, company_size: str = "unknown", industry: str = "unknown", 
               response_signals: dict = None, contact_type: str = "unknown") -> dict:
    """
    Score a lead 0-100 based on engagement likelihood.
    
    Scoring factors:
    - Company size: larger = higher score
    - Industry match: aligned with your services = +points
    - Response history: past engagement = +points
    - Contact type: Decision maker > IC = higher
    
    Args:
        company_name: Business name
        company_size: "1-10", "11-50", "51-250", "250+"
        industry: Business vertical
        response_signals: dict with keys like "email_opens", "clicks", "prev_responses"
        contact_type: "decision_maker", "influencer", "individual_contributor"
    
    Returns:
        dict with score (0-100), breakdown, and recommendation
    """
    score = 50  # Base score
    breakdown = {}
    
    # Company size scoring
    size_scores = {
        "1-10": 30,
        "11-50": 60,
        "51-250": 75,
        "250+": 85,
    }
    size_score = size_scores.get(company_size, 50)
    score += (size_score - 50) * 0.3
    breakdown["company_size"] = size_score
    
    # Industry alignment (premium B2B verticals)
    high_value_industries = [
        "technology", "saas", "fintech", "healthcare", "real_estate", 
        "insurance", "e-commerce", "logistics", "manufacturing", "construction"
    ]
    if industry.lower() in high_value_industries:
        score += 15
        breakdown["industry_alignment"] = 15
    else:
        breakdown["industry_alignment"] = 0
    
    # Response signals (if available)
    if response_signals:
        if response_signals.get("email_opens", 0) > 0:
            score += 10
        if response_signals.get("clicks", 0) > 0:
            score += 15
        if response_signals.get("prev_responses", 0) > 0:
            score += 20
        breakdown["response_signals"] = response_signals.get("email_opens", 0) * 2
    else:
        breakdown["response_signals"] = 0
    
    # Contact type
    contact_scores = {
        "decision_maker": 20,
        "influencer": 10,
        "individual_contributor": 5,
        "unknown": 0,
    }
    contact_score = contact_scores.get(contact_type, 0)
    score += contact_score
    breakdown["contact_type"] = contact_score
    
    # Normalize to 0-100
    score = min(100, max(0, score))
    
    # Recommendation
    if score >= 80:
        recommendation = "🔥 HOT LEAD — Call immediately"
    elif score >= 60:
        recommendation = "⭐ WARM LEAD — Email first, then call"
    elif score >= 40:
        recommendation = "📧 COLD LEAD — Email sequence, monitor response"
    else:
        recommendation = "❓ LOW PRIORITY — Add to nurture list"
    
    return {
        "score": int(score),
        "breakdown": breakdown,
        "recommendation": recommendation,
        "company": company_name
    }
