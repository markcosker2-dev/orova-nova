"""
Email Template Generator for Personalized Cold Outreach
Uses Jinja2 to generate hyper-personalized cold emails based on company research.
Perfect for Meta Lead Gen agency targeting premium B2B.
"""
import logging
from jinja2 import Template
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── EMAIL TEMPLATES ────────────────────────────────────────────────────

COLD_EMAIL_TEMPLATES = {
    "premium_b2b_pain_focused": """Subject: {{ company_short }} – Quick question about {{ pain_point }}

Hi {{ contact_first_name }},

I noticed {{ company_short }} has been scaling {{ industry }} solutions, and I'm guessing you're managing pain around {{ pain_point }}.

We work with {{ industry }} leaders like [similar company] to {{ solution_benefit }}. The typical result? {{ result_metric }}.

Quick question: Are you open to a 15-minute call to explore if we could do the same for {{ company_short }}?

Best,
{{ sender_name }}
{{ sender_title }}
{{ sender_company }}
{{ sender_phone }}""",

    "referral_angle": """Subject: {{ contact_first_name }}, {{ mutual_connection }} suggested I reach out

Hi {{ contact_first_name }},

{{ mutual_connection }} mentioned you're leading {{ department }} at {{ company_short }}. Since you two have worked together on {{ context }}, I thought you'd value this.

We've been helping {{ industry }} companies with {{ pain_point }}. [{{ recent_client }} saw {{ result_metric }} in 90 days.]

Would a quick 15-min call make sense?

{{ sender_name }}""",

    "problem_agitate_solve": """Subject: {{ company_short }} + {{ pain_point }} = Opportunity?

Hi {{ contact_first_name }},

Here's what I'm seeing in {{ industry }}:
- Companies spending {{ spend_estimate }} on {{ current_solution }}
- But still struggling with {{ pain_point }}
- Missing {{ lost_opportunity }}

We've fixed this for {{ similar_company }}. They now {{ result }}.

Worth exploring if we could do the same?

{{ sender_name }}
{{ sender_company }}""",

    "social_proof_heavy": """Subject: {{ company_short }} + {{ similar_company }} = Same problem, different results

Hi {{ contact_first_name }},

{{ similar_company }} was in your exact position 6 months ago:
- {{ pain_point }} → {{ solution }}
- {{ metric1 }} → {{ metric1_result }}
- {{ metric2 }} → {{ metric2_result }}

We're now working with 15+ {{ industry }} leaders. Curious if {{ company_short }} wants in?

{{ sender_name }}""",
}

def generate_email(template_type: str = "premium_b2b_pain_focused", **context) -> dict:
    """
    Generate personalized cold email using Jinja2 templating.
    
    Args:
        template_type: Which template to use (see COLD_EMAIL_TEMPLATES)
        **context: Variables to fill in (contact_first_name, company_short, pain_point, etc.)
    
    Returns:
        dict with subject and body
    """
    template_str = COLD_EMAIL_TEMPLATES.get(template_type)
    if not template_str:
        logger.error(f"[EmailGen] Unknown template: {template_type}")
        return {"error": f"Unknown template: {template_type}"}
    
    try:
        template = Template(template_str)
        rendered = template.render(**context)
        
        # Split subject and body
        lines = rendered.strip().split("\n\n", 1)
        subject = lines[0].replace("Subject: ", "").strip() if len(lines) > 0 else "No Subject"
        body = lines[1] if len(lines) > 1 else rendered
        
        return {
            "subject": subject,
            "body": body.strip(),
            "template_used": template_type,
            "generated_at": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"[EmailGen] Template render failed: {e}")
        return {"error": str(e)}

def generate_follow_up_sequence(contact_name: str, company: str, pain_point: str, 
                                 num_emails: int = 3, days_between: int = 3) -> list:
    """
    Generate a follow-up email sequence for cold outreach.
    
    Sequence strategy:
    - Email 1: Initial pain-focused hook
    - Email 2: Social proof / case study angle (if no response)
    - Email 3: Final soft close / offer alternative contact
    
    Args:
        contact_name: Prospect first name
        company: Company name
        pain_point: Main pain to address
        num_emails: How many follow-ups (1-5)
        days_between: Days between each email
    
    Returns:
        List of email dicts with timing
    """
    sequence = []
    
    email1 = generate_email(
        template_type="premium_b2b_pain_focused",
        contact_first_name=contact_name,
        company_short=company,
        pain_point=pain_point,
        solution_benefit="streamline and automate processes",
        result_metric="30-40% efficiency gain",
        sender_name="Mark",
        sender_title="Lead Gen Strategist",
        sender_company="Your Agency",
        sender_phone="Your Phone"
    )
    sequence.append({
        "sequence_number": 1,
        "days_after_initial": 0,
        "type": "pain_focused",
        **email1
    })
    
    if num_emails >= 2:
        email2 = generate_email(
            template_type="social_proof_heavy",
            contact_first_name=contact_name,
            company_short=company,
            similar_company="Similar company in your space",
            pain_point=pain_point,
            solution="Our solution",
            metric1="Cost",
            metric1_result="Down 30%",
            metric2="Speed",
            metric2_result="Up 40%",
            industry="Industry",
            sender_name="Mark"
        )
        sequence.append({
            "sequence_number": 2,
            "days_after_initial": days_between,
            "type": "social_proof",
            **email2
        })
    
    if num_emails >= 3:
        email3 = {
            "sequence_number": 3,
            "days_after_initial": days_between * 2,
            "type": "soft_close",
            "subject": f"{contact_name}, quick follow-up on {{ company }}",
            "body": f"""Hi {contact_name},

Not sure if my last emails got buried in your inbox. No worries—I know you're busy.

Quick question: Would you prefer a call or a quick email about how we've helped {{ industry }} companies with {pain_point}?

Either way, I'll stop after this. 😊

{{ sender_name }}""",
            "template_used": "custom_soft_close"
        }
        sequence.append(email3)
    
    return sequence
