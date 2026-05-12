import gspread
import os
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def get_sheets_client():
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
    if not creds_path or not os.path.exists(creds_path):
        logger.error(f"Google Sheets: Credentials not found at {creds_path}")
        return None

    return gspread.service_account(filename=creds_path)

def get_master_sheet(tenant_config: Dict[str, Any]):
    """Get the master sheet for a tenant."""
    client = get_sheets_client()
    if not client:
        return None

    sheet_id = tenant_config.get("google_sheets", {}).get("master_sheet_id")
    if not sheet_id:
        logger.error("Master sheet ID not configured in tenant")
        return None

    try:
        return client.open_by_key(sheet_id)
    except Exception as e:
        logger.error(f"Failed to open master sheet: {e}")
        return None

async def append_to_sheet(sheet_name: str, rows: List[List[Any]]):
    """
    Append rows to a Google Sheet.
    :param sheet_name: Name of the Google Sheet.
    :param rows: List of rows to append (each row is a list of values).
    """
    try:
        client = get_sheets_client()
        if not client:
            return "❌ error: Google Sheets credentials not configured."
        
        sheet = client.open(sheet_name).sheet1
        sheet.append_rows(rows)
        logger.info(f"Sheets: Appended {len(rows)} rows to {sheet_name}")
        return f"✅ successfully appended {len(rows)} rows to '{sheet_name}'."
    except Exception as e:
        logger.error(f"Sheets Error: {e}")
        return f"❌ error appending to sheet: {str(e)}"

async def create_new_sheet(sheet_name: str):
    """Create a new Google Sheet."""
    try:
        client = get_sheets_client()
        if not client:
            return "❌ error: Google Sheets credentials not configured."

        sheet = client.create(sheet_name)
        # Share with personal email if needed? For now just create.
        return f"✅ successfully created new sheet: '{sheet_name}' (ID: {sheet.id})"
    except Exception as e:
        logger.error(f"Sheets Error: {e}")
        return f"❌ error creating sheet: {str(e)}"

class GoogleSheetsCommandCenter:
    """OROVA Google Sheets Command Center with HUNT, WAR-ROOM, and CASH tabs."""

    def __init__(self, tenant_config: Dict[str, Any]):
        self.tenant = tenant_config
        self.sheet = get_master_sheet(tenant_config)
        self.tabs = tenant_config.get("google_sheets", {}).get("tabs", {})

    async def initialize_dashboard(self) -> str:
        """Initialize the three dashboard tabs if they don't exist."""
        if not self.sheet:
            return "❌ Master sheet not accessible"

        try:
            # Check if tabs exist, create if needed
            existing_sheets = [ws.title for ws in self.sheet.worksheets()]

            for tab_name, tab_title in self.tabs.items():
                if tab_title not in existing_sheets:
                    self.sheet.add_worksheet(title=tab_title, rows=1000, cols=20)
                    logger.info(f"Created tab: {tab_title}")

                    # Initialize headers based on tab type
                    if tab_name == "hunt":
                        self._init_hunt_tab(tab_title)
                    elif tab_name == "war_room":
                        self._init_war_room_tab(tab_title)
                    elif tab_name == "cash":
                        self._init_cash_tab(tab_title)

            return "✅ Dashboard initialized successfully"
        except Exception as e:
            logger.error(f"Failed to initialize dashboard: {e}")
            return f"❌ Failed to initialize dashboard: {str(e)}"

    def _init_hunt_tab(self, tab_title: str):
        """Initialize HUNT tab for lead scraping results."""
        worksheet = self.sheet.worksheet(tab_title)
        headers = [
            ["Name", "Business", "Email", "Phone", "Website", "HAWK Score", "Luxury Alignment", "Source", "Date Added", "Status"]
        ]
        worksheet.update('A1:J1', headers)

    def _init_war_room_tab(self, tab_title: str):
        """Initialize WAR-ROOM tab for Meta Ads performance."""
        worksheet = self.sheet.worksheet(tab_title)
        headers = [
            ["Date", "Campaign", "Spend ($)", "Impressions", "Clicks", "CTR (%)", "Leads", "Cost per Lead ($)", "ROAS", "Status"]
        ]
        worksheet.update('A1:J1', headers)

    def _init_cash_tab(self, tab_title: str):
        """Initialize CASH tab for invoice status."""
        worksheet = self.sheet.worksheet(tab_title)
        headers = [
            ["Client", "Invoice #", "Amount ($)", "Status", "Due Date", "Payment Method", "Wise Transfer ID", "Date Paid"]
        ]
        worksheet.update('A1:H1', headers)

    async def add_lead_to_hunt(self, lead_data: Dict[str, Any]) -> str:
        """Add a qualified lead to the HUNT tab."""
        if not self.sheet:
            return "❌ Master sheet not accessible"

        try:
            worksheet = self.sheet.worksheet(self.tabs.get("hunt", "HUNT"))
            luxury_score = lead_data.get("luxury_alignment_score", 0)

            # Only add leads with score > 85
            if luxury_score <= 85:
                return f"⚠️ Lead score {luxury_score} below threshold (85+), not added"

            row = [
                lead_data.get("name", ""),
                lead_data.get("business", ""),
                lead_data.get("email", ""),
                lead_data.get("phone", ""),
                lead_data.get("website", ""),
                lead_data.get("hawk_score", ""),
                luxury_score,
                lead_data.get("source", ""),
                lead_data.get("date_added", ""),
                "New"
            ]

            worksheet.append_row(row)
            return f"✅ Lead added to HUNT tab: {lead_data.get('name', 'Unknown')}"
        except Exception as e:
            logger.error(f"Failed to add lead to HUNT: {e}")
            return f"❌ Failed to add lead: {str(e)}"

    async def update_war_room_performance(self, performance_data: Dict[str, Any]) -> str:
        """Update Meta Ads performance in WAR-ROOM tab."""
        if not self.sheet:
            return "❌ Master sheet not accessible"

        try:
            worksheet = self.sheet.worksheet(self.tabs.get("war_room", "WAR-ROOM"))

            row = [
                performance_data.get("date", ""),
                performance_data.get("campaign", ""),
                performance_data.get("spend", 0),
                performance_data.get("impressions", 0),
                performance_data.get("clicks", 0),
                performance_data.get("ctr", 0),
                performance_data.get("leads", 0),
                performance_data.get("cost_per_lead", 0),
                performance_data.get("roas", 0),
                performance_data.get("status", "Active")
            ]

            worksheet.append_row(row)

            # Check ROAS safety threshold
            roas = performance_data.get("roas", 0)
            if roas < 2.0:
                return f"🚨 ROAS {roas} below 2.0 threshold - campaign paused"
            else:
                return f"✅ Performance updated in WAR-ROOM: ROAS {roas}"
        except Exception as e:
            logger.error(f"Failed to update WAR-ROOM: {e}")
            return f"❌ Failed to update performance: {str(e)}"

    async def check_remote_control(self) -> Optional[Dict[str, Any]]:
        """Check for remote control commands from Google Sheets."""
        if not self.sheet:
            return None

        try:
            worksheet = self.sheet.worksheet(self.tabs.get("hunt", "HUNT"))

            # Check the "Status" column for "Approved" entries
            records = worksheet.get_all_records()

            for i, record in enumerate(records, start=2):  # Start from row 2 (after headers)
                if record.get("Status") == "Approved":
                    # Mark as processed
                    worksheet.update_cell(i, 10, "Processed")  # Column J is Status

                    return {
                        "action": "trigger_hawk_outreach",
                        "lead": {
                            "name": record.get("Name", ""),
                            "email": record.get("Email", ""),
                            "business": record.get("Business", ""),
                            "hawk_score": record.get("HAWK Score", "")
                        }
                    }

            return None
        except Exception as e:
            logger.error(f"Failed to check remote control: {e}")
            return None

    async def update_invoice_status(self, invoice_data: Dict[str, Any]) -> str:
        """Update invoice status in CASH tab."""
        if not self.sheet:
            return "❌ Master sheet not accessible"

        try:
            worksheet = self.sheet.worksheet(self.tabs.get("cash", "CASH"))

            row = [
                invoice_data.get("client", ""),
                invoice_data.get("invoice_number", ""),
                invoice_data.get("amount", 0),
                invoice_data.get("status", "Pending"),
                invoice_data.get("due_date", ""),
                "Wise Transfer",
                invoice_data.get("wise_transfer_id", ""),
                invoice_data.get("date_paid", "")
            ]

            worksheet.append_row(row)
            return f"✅ Invoice updated in CASH tab: {invoice_data.get('invoice_number', '')}"
        except Exception as e:
            logger.error(f"Failed to update CASH tab: {e}")
            return f"❌ Failed to update invoice: {str(e)}"
