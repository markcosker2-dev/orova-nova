# -*- coding: utf-8 -*-
"""
OROVA Core Engine — Universal AI Caller
Refactored from retell_caller.py. Dynamic context from vertical config.
"""

import os
import sys
import re
import pandas as pd
import requests
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UniversalAICaller:
    """Industry-agnostic Retell AI caller driven by vertical config."""

    def __init__(self, vertical_name: str):
        from Core_Engine.config import load_vertical
        self.vertical = load_vertical(vertical_name)
        self.vertical_name = vertical_name

        self.api_key = os.environ.get("RETELL_API_KEY", "")
        self.agent_id = os.environ.get("RETELL_AGENT_ID", "")
        self.base_url = "https://api.retellai.com/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Load leads from DB
        try:
            from Core_Engine.db_manager import get_leads_by_status
            # Default to fetching 'Qualified' leads, but allow CLI override
            self.leads_data = get_leads_by_status("Qualified", vertical_name)
            # Fallback to New if no qualified? No, strict flow.
            # Convert to DataFrame for compatibility with existing methods if needed,
            # but list of dicts is better.
            import pandas as pd
            self.leads = pd.DataFrame(self.leads_data) if self.leads_data else pd.DataFrame()
            
            logger.info(f"Loaded {len(self.leads)} Qualified leads from DB")
        except Exception as e:
            logger.error(f"DB Load failed: {e}")
            self.leads = pd.DataFrame()

    @staticmethod
    def clean_phone(phone: str) -> str:
        """Ensure E.164 format."""
        if not phone or phone == "N/A":
            return ""
        digits = re.sub(r'\D', '', str(phone))
        if len(digits) == 10:
            return f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return f"+{digits}" if not str(phone).startswith("+") else str(phone)

    def list_leads(self, min_score: int = 0):
        """Show leads and their scores."""
        if self.leads.empty:
            print("No leads loaded.")
            return

        print(f"\n{'='*60}")
        print(f"QUALIFIED LEADS — {self.vertical_name}")
        print(f"{'='*60}")

        for _, row in self.leads.iterrows():
            # Handle both JSON metadata and direct cols if any
            metadata = json.loads(row.get("metadata", "{}")) if isinstance(row.get("metadata"), str) else row.get("metadata", {})
            
            score = row.get("clv_score", 0)
            name = row.get("business_name", "Unknown")
            phone = row.get("phone", "N/A")
            tier = metadata.get("market_tier", "Unknown")
            clv = metadata.get("estimated_clv", "N/A")

            indicator = "[HOT]" if score >= 9 else "[GOOD]" if score >= 7 else "[WARM]" if score > 0 else "[COLD]"
            print(f"{indicator} [{score}] {name}")
            print(f"    Phone: {phone} | Tier: {tier} | CLV: {clv}")
            print()

    def call_lead(self, business_name: str) -> dict:
        """Make a personalized Retell AI call."""
        if self.leads.empty:
            return {"success": False, "error": "No leads loaded"}

        mask = self.leads["business_name"].str.lower().str.contains(
            business_name.lower(), na=False
        )
        matches = self.leads[mask]
        if matches.empty:
            return {"success": False, "error": f"Lead '{business_name}' not found"}

        lead = matches.iloc[0].to_dict()
        phone = self.clean_phone(lead.get("phone", ""))
        if not phone:
            return {"success": False, "error": "No phone number"}

        # Dynamic context from lead + vertical
        metadata = json.loads(lead.get("metadata", "{}")) if isinstance(lead.get("metadata"), str) else lead.get("metadata", {})
        
        context = {
            "business_name": lead.get("business_name", "there"),
            "icebreaker": metadata.get("icebreaker", ""),
            "service_type": metadata.get("primary_service", "services"),
            "market_tier": metadata.get("market_tier", "premium"),
            "vertical": self.vertical_name
        }

        print(f"\n{'='*60}")
        print(f"CALLING: {lead.get('business_name')}")
        print(f"Phone: {phone}")
        print(f"Icebreaker: {context['icebreaker'][:80]}...")
        print(f"{'='*60}")

        payload = {
            "agent_id": self.agent_id,
            "customer_number": phone,
            "retell_llm_dynamic_variables": context
        }

        try:
            resp = requests.post(
                f"{self.base_url}/create-phone-call",
                headers=self.headers,
                json=payload
            )
            if resp.status_code == 201:
                result = resp.json()
                call_id = result.get("call_id")
                logger.info(f"Call initiated! ID: {call_id}")
                
                # Update DB status
                from Core_Engine.db_manager import update_lead_status
                update_lead_status(lead.get("id"), "Contacted", f"Call ID: {call_id}")
                
                return {"success": True, "call_id": call_id}
            else:
                return {"success": False, "error": f"API {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def call_hot_leads(self, min_score: int = 8):
        """Call all leads above a score threshold with human approval."""
        # Use clv_score from DB
        hot = self.leads[self.leads["clv_score"] >= min_score]
        if hot.empty:
            print(f"No leads with score >= {min_score}")
            return

        print(f"\nFound {len(hot)} hot leads to call...")
        for _, row in hot.iterrows():
            name = row.get("business_name", "Unknown")
            confirm = input(f"\nCall {name}? (y/n): ").strip().lower()
            if confirm == "y":
                result = self.call_lead(name)
                if result.get("success"):
                    print(f"  ✅ Call ID: {result['call_id']}")
                else:
                    print(f"  ❌ {result['error']}")


if __name__ == "__main__":
    from Core_Engine.db_manager import init_db
    init_db()
    
    vertical = sys.argv[1] if len(sys.argv) > 1 else "Automotive"
    caller = UniversalAICaller(vertical)

    if len(sys.argv) < 3:
        caller.list_leads()
    elif sys.argv[2] == "hot":
        caller.call_hot_leads()
    elif sys.argv[2] == "call" and len(sys.argv) >= 4:
        caller.call_lead(" ".join(sys.argv[3:]))
    else:
        print(f"Usage: python -m Core_Engine.ai_caller {vertical} [list|hot|call <name>]")
