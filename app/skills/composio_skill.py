import os
import logging
from composio_openai import ComposioToolSet, App

logger = logging.getLogger(__name__)

# Initialize Composio Toolset
toolset = ComposioToolSet(api_key=os.getenv("COMPOSIO_API_KEY"))

async def get_composio_tools(apps: list = None):
    """
    Returns a list of tools from Composio for the specified apps.
    Default apps: Gmail, Google Sheets, Slack, Salesforce.
    """
    if not apps:
        apps = [App.GMAIL, App.GOOGLESHEETS, App.SLACK]
    
    try:
        tools = toolset.get_tools(apps=apps)
        return tools
    except Exception as e:
        logger.error(f"💥 Composio Tool Fetch failed: {e}")
        return []

async def execute_composio_action(action_name: str, params: dict):
    """Executes a specific action via Composio."""
    try:
        result = toolset.execute_action(action=action_name, params=params)
        return result
    except Exception as e:
        logger.error(f"💥 Composio Execution failed: {e}")
        return {"error": str(e)}
