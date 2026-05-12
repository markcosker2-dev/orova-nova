import os
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Try modern SDK first, fallback to raw requests
try:
    from retell import Retell
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    logger.warning("retell-sdk not installed. Using raw requests fallback.")


def to_e164(raw_number: str) -> Optional[str]:
    """
    Convert any US phone number format to strict E.164.
    Handles all common formats.
    Returns None if the number cannot be normalised to a valid US number.
    """
    if not raw_number:
        return None

    # Strip everything except digits and leading +
    cleaned = re.sub(r"[^\d+]", "", raw_number.strip())

    # Already E.164 with country code
    if cleaned.startswith("+"):
        digits_only = cleaned[1:]
        if len(digits_only) == 11 and digits_only.startswith("1"):
            return cleaned  # Valid US E.164
        if len(digits_only) == 10:
            return "+" + "1" + digits_only  # Missing +1, add it
        logger.warning(f"[PHONE] Unrecognised format: {raw_number}")
        return None

    # Strip leading 1 if present and then add +1
    if cleaned.startswith("1") and len(cleaned) == 11:
        return "+" + cleaned

    # 10 digit US number without country code
    if len(cleaned) == 10:
        return "+1" + cleaned

    logger.warning(f"[PHONE] Cannot normalise to E.164: {raw_number!r}")
    return None


def _is_calling_hours() -> bool:
    """
    Check if current time is within calling hours: Mon-Fri 9am-5pm ET.
    """
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return 9 <= now.hour < 17  # 9am to 5pm


async def trigger_retell_call(phone: str, context: Dict[str, str]) -> Dict[str, Any]:
    """
    Trigger an outbound phone call via Retell.AI with calling hours enforcement.
    
    Args:
        phone: Phone number in any format (will be normalized to E.164)
        context: Dict with keys like 'business_name', 'contact_name', 'icebreaker', 'offer_gap'
    
    Returns:
        Dict with 'success' (bool), 'call_id' (str), and 'error' (str if failed)
    """
    api_key = os.getenv("RETELL_API_KEY")
    agent_id = os.getenv("RETELL_AGENT_ID")
    from_number = os.getenv("RETELL_FROM_NUMBER")

    # Pre-flight checks
    if not api_key:
        return {"success": False, "error": "RETELL_API_KEY not set in .env"}
    if not agent_id:
        return {"success": False, "error": "RETELL_AGENT_ID not set in .env"}
    if not from_number:
        return {"success": False, "error": "RETELL_FROM_NUMBER not set in .env"}

    # Calling hours enforcement
    if not _is_calling_hours():
        return {"success": False, "error": "Outside calling hours (Mon-Fri 9am-5pm ET)"}

    # Validate and normalise phone number to E.164 before calling
    phone_e164 = to_e164(phone)
    if not phone_e164:
        logger.warning(
            f"[CALLER] Skipping call — phone '{phone}' could not be formatted to E.164"
        )
        return {
            "success": False,
            "error": f"Phone number '{phone}' could not be formatted to E.164",
        }

    # Also validate from_number
    from_e164 = to_e164(from_number)
    if not from_e164:
        logger.error(
            f"[CALLER] RETELL_FROM_NUMBER '{from_number}' is not valid E.164."
        )
        return {
            "success": False,
            "error": f"RETELL_FROM_NUMBER is not valid E.164: {from_number}",
        }

    # Build dynamic variables for the Retell agent's script
    dynamic_vars = {
        "business_name": context.get("business_name", "your company"),
        "contact_name": context.get("contact_name", ""),
        "icebreaker": context.get("icebreaker", ""),
        "offer_gap": context.get("offer_gap", ""),
        "caller_name": "Mark",
        "company_name": "OROVA",
    }

    # --- METHOD 1: Modern retell-sdk ---
    if HAS_SDK:
        try:
            client = Retell(api_key=api_key)
            
            # Explicit V2 only
            if not hasattr(client.call, "create_phone_call"):
                raise AttributeError(
                    "retell.call.create_phone_call not found. "
                    "Update retell-sdk: pip install retell-sdk>=4.0.0"
                )

            call_response = client.call.create_phone_call(
                from_number=from_e164,
                to_number=phone_e164,
                agent_id=agent_id,
                retell_llm_dynamic_variables=dynamic_vars,
            )
            call_id = call_response.call_id
            logger.info(f"✅ Retell call created via SDK: {call_id}")
            return {"success": True, "call_id": call_id, "method": "sdk"}
        except AttributeError as e:
            logger.error(f"[CALLER] SDK version error: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"SDK call failed: {e}")
            return {"success": False, "error": str(e)}

    # If NO SDK installed at all, fallback to raw API (V2)
    try:
        url = "https://api.retellai.com/v2/create-phone-call"
        payload = {
            "from_number": from_e164,
            "to_number": phone_e164,
            "agent_id": agent_id,
            "retell_llm_dynamic_variables": dynamic_vars,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp_json = resp.json() if resp.content else {}

        if resp.status_code == 201:
            call_id = resp_json.get("call_id", "unknown")
            logger.info(f"✅ Retell call created via API: {call_id}")
            return {"success": True, "call_id": call_id, "method": "api"}
        else:
            error_msg = f"Retell API error {resp.status_code}: {resp.text}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    except Exception as e:
        logger.error(f"Retell call completely failed: {e}")
        return {"success": False, "error": str(e)}


def get_call_status(call_id: str) -> Optional[Dict]:
    """Check the status of an existing Retell call."""
    api_key = os.getenv("RETELL_API_KEY")
    if not api_key:
        return None

    if HAS_SDK:
        try:
            client = Retell(api_key=api_key)
            call = client.call.retrieve(call_id)
            return {
                "call_id": call.call_id,
                "status": call.call_status,
                "duration": getattr(call, "duration_ms", 0),
                "transcript": getattr(call, "transcript", ""),
            }
        except Exception as e:
            logger.error(f"Failed to retrieve call status: {e}")
            return None

    # Raw API fallback
    try:
        resp = requests.get(
            f"https://api.retellai.com/v2/get-call/{call_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None