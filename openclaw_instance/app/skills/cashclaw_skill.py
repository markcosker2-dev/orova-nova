"""
CashClaw Skills - Business Operations Integration
Connects OpenClaw agent with CashClaw's monetization capabilities.
"""

import logging
from typing import Dict, Any
from app.core.cashclaw_bridge import CashClawBridge

logger = logging.getLogger(__name__)

# Initialize CashClaw bridge (will be set during agent startup)
cashclaw_bridge = None

def set_cashclaw_bridge(bridge: CashClawBridge):
    """Set the CashClaw bridge instance."""
    global cashclaw_bridge
    cashclaw_bridge = bridge

async def seo_audit(params: Dict[str, Any]) -> str:
    """Execute SEO audit via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("seo_audit", params)

    if result["status"] == "success":
        return f"✅ SEO Audit Complete\nURL: {result.get('url', 'N/A')}\nReport: {result.get('output_file', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ SEO Audit Failed: {result.get('message', 'Unknown error')}"

async def lead_generation(params: Dict[str, Any]) -> str:
    """Execute lead generation via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("generate_leads", params)

    if result["status"] == "success":
        return f"✅ Lead Generation Complete\nICP: {result.get('icp', 'N/A')}\nCount: {result.get('count', 0)}\nFile: {result.get('output_file', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Lead Generation Failed: {result.get('message', 'Unknown error')}"

async def content_creation(params: Dict[str, Any]) -> str:
    """Execute content creation via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("write_content", params)

    if result["status"] == "success":
        return f"✅ Content Created\nType: {result.get('type', 'N/A')}\nTopic: {result.get('topic', 'N/A')}\nWords: {result.get('word_count', 0)}\nFile: {result.get('output_file', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Content Creation Failed: {result.get('message', 'Unknown error')}"

async def email_outreach(params: Dict[str, Any]) -> str:
    """Execute email outreach via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("send_outreach", params)

    if result["status"] == "success":
        return f"✅ Email Outreach Initiated\nICP: {result.get('icp', 'N/A')}\nSequence: {result.get('sequence_length', 0)} emails\n{result.get('message', '')}"
    else:
        return f"❌ Email Outreach Failed: {result.get('message', 'Unknown error')}"

async def competitor_analysis(params: Dict[str, Any]) -> str:
    """Execute competitor analysis via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("analyze_competitors", params)

    if result["status"] == "success":
        return f"✅ Competitor Analysis Complete\nTarget: {result.get('target_url', 'N/A')}\nReport: {result.get('output_file', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Competitor Analysis Failed: {result.get('message', 'Unknown error')}"

async def data_scraping(params: Dict[str, Any]) -> str:
    """Execute data scraping via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("scrape_data", params)

    if result["status"] == "success":
        return f"✅ Data Scraping Complete\nSource: {result.get('source_url', 'N/A')}\nRecords: {result.get('count', 0)}\nFile: {result.get('output_file', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Data Scraping Failed: {result.get('message', 'Unknown error')}"

async def landing_page(params: Dict[str, Any]) -> str:
    """Execute landing page creation via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("create_landing_page", params)

    if result["status"] == "success":
        return f"✅ Landing Page Created\nProduct: {result.get('product', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Landing Page Creation Failed: {result.get('message', 'Unknown error')}"

async def reputation_audit(params: Dict[str, Any]) -> str:
    """Execute reputation audit via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("audit_reputation", params)

    if result["status"] == "success":
        return f"✅ Reputation Audit Complete\nBrand: {result.get('brand', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Reputation Audit Failed: {result.get('message', 'Unknown error')}"

async def proposal_generation(params: Dict[str, Any]) -> str:
    """Generate business proposal via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("generate_proposal", params)

    if result["status"] == "success":
        return f"✅ Professional Proposal Generated\nClient: {params.get('client_data', {}).get('name', 'N/A')}\nFile: {result.get('filename', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Proposal Generation Failed: {result.get('message', 'Unknown error')}"

async def invoice_creation(params: Dict[str, Any]) -> str:
    """Create invoice via CashClaw."""
    if not cashclaw_bridge:
        return "❌ CashClaw bridge not initialized"

    result = await cashclaw_bridge.execute_business_skill("create_invoice", params)

    if result["status"] == "success":
        return f"✅ Invoice Created and Sent\nMission ID: {params.get('mission_id', 'N/A')}\n{result.get('message', '')}"
    else:
        return f"❌ Invoice Creation Failed: {result.get('message', 'Unknown error')}"