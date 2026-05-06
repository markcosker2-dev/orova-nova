import os
import logging
from composio import Composio, App

logger = logging.getLogger(__name__)

# Initialize Composio Client
composio_client = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

async def get_composio_tools(apps: list = None):
    """
    Returns a list of tools from Composio for the specified apps.
    Default apps: Gmail, Google Sheets, Slack, Salesforce.
    """
    if not apps:
        apps = [App.GMAIL, App.GOOGLESHEETS, App.SLACK]
    
    try:
        # In new composio, it might be composio_client.tools.get() but we don't strictly need to return tools here 
        # since we just execute actions directly via Nova's planner mapping.
        # But for completion:
        return composio_client.get_tools(apps=apps)
    except Exception as e:
        logger.error(f"💥 Composio Tool Fetch failed: {e}")
        return []

async def execute_composio_action(action_name: str, params: dict):
    """Executes a specific action via Composio."""
    try:
        # Using the new client execution method
        result = composio_client.execute_action(action=action_name, params=params)
        return result
    except Exception as e:
        logger.error(f"💥 Composio Execution failed: {e}")
        return {"error": str(e)}
