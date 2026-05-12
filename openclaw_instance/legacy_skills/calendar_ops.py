# -*- coding: utf-8 -*-
import os
import requests
from typing import Dict, Any

def book_appointment(args: Dict[str, Any]) -> Dict[str, Any]:
    name = args.get("name", "Unknown Lead")
    time = args.get("time", "TBD")
    phone = args.get("phone", "Unknown")
    
    cal_key = os.getenv("CAL_API_KEY")
    event_id = os.getenv("CAL_EVENT_TYPE_ID")
    
    success = False
    
    # 1. Booking
    if cal_key and event_id:
        try:
            url = f"https://api.cal.com/v1/bookings?apiKey={cal_key}"
            payload = {
                "eventTypeId": int(event_id),
                "start": time,
                "responses": {
                    "name": name,
                    "email": "sms-booking@placeholder.com",
                    "location": {"value": "phone", "optionValue": phone}
                },
                "metadata": {"source": "Moltbot_Director"},
                "timeZone": "America/Los_Angeles"
            }
            r = requests.post(url, json=payload)
            if r.status_code in [200, 201]:
                success = True
        except Exception as e:
            print(f"Booking Error: {e}")

    # 2. Telegram Alert (Robust)
    if success:
        formatted_message = f"""🎯 **BOOM.** New Booking!
👤 **Lead:** {name}
📞 **Phone:** {phone}
📅 **Time:** {time}"""
        
        try:
            # We need to run the async notifier from this sync function
            import asyncio
            from .notifier import send_alert
            
            # Check if we are already in an event loop
            try:
                loop = asyncio.get_running_loop()
                # If we are in a loop (e.g. called from FastAPI/Telegram), create a task
                loop.create_task(send_alert(formatted_message))
            except RuntimeError:
                # If no loop (e.g. called from sync script), run it
                asyncio.run(send_alert(formatted_message))
                
        except Exception as e:
            print(f"Notifier Error: {e}")
            
    return {"success": success}
