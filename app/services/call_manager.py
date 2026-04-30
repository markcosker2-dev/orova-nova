import os
import logging
from retell import Retell
from app.core.ai_client import UnifiedAIClient

logger = logging.getLogger(__name__)

# Initialize Clients
retell = Retell(api_key=os.getenv("RETELL_API_KEY"))
ai = UnifiedAIClient()

# 1. The "Planner" - Writes the Script
async def draft_reminder_call(prospect_name, meeting_time, meeting_topic):
    """
    Uses Kimi to write a personalized script for the call.
    """
    system_prompt = (
        "You are an expert sales script writer. Write a short, natural, 1-2 sentence "
        "opening line for a phone call reminding a prospect about a meeting."
        "Do not include 'Hey [Name]', just the body of the message."
    )
    
    user_prompt = f"Prospect: {prospect_name}\nTime: {meeting_time}\nTopic: {meeting_topic}"
    
    # Ask Kimi/Brain to write the script
    response = await ai.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ])
    
    return response.content

# 2. The "Executor" - Triggers Retell
async def execute_call(phone_number, prospect_name, script_content):
    """
    Injects the script into Retell and dials the phone.
    """
    try:
        agent_id = os.getenv("RETELL_AGENT_ID") # The "Blank Agent" ID
        # Wait, the user's snippet uses retell-sdk. Let's make sure it's correct.
        # override_agent_id is correct for Retell.
        
        call_response = retell.call.create_phone_call(
            to_number=phone_number,
            override_agent_id=agent_id,
            retell_llm_dynamic_variables={
                "prospect_name": prospect_name,
                "custom_script": script_content,
                "call_context": "Meeting reminder call. Be polite and professional."
            }
        )
        return call_response.call_id
    except Exception as e:
        logger.error(f"Retell Call Failed: {e}")
        return None
