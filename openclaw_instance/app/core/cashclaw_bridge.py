"""
CashClaw Bridge - Python integration with Node.js CashClaw business layer
Connects OROVA's Python agent with CashClaw's monetization capabilities.
"""

import os
import json
import subprocess
import logging
from typing import Dict, Any, Optional, List
from app.core.cashclaw import CashClaw

logger = logging.getLogger(__name__)

class CashClawBridge:
    """
    Bridge between Python OpenClaw agent and Node.js CashClaw CLI.
    Enables business operations, invoicing, and marketplace integration.
    """

    def __init__(self, tenant_config: Dict[str, Any]):
        self.tenant = tenant_config
        self.cashclaw = CashClaw(tenant_config)

    async def execute_business_skill(self, skill_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a CashClaw business skill via CLI bridge.
        Returns structured response for agent processing.
        """
        try:
            # Map skill names to CashClaw commands
            skill_commands = {
                "seo_audit": self._run_seo_audit,
                "generate_leads": self._run_lead_generation,
                "write_content": self._run_content_creation,
                "send_outreach": self._run_email_outreach,
                "analyze_competitors": self._run_competitor_analysis,
                "scrape_data": self._run_data_scraping,
                "create_landing_page": self._run_landing_page,
                "audit_reputation": self._run_reputation_audit,
                "generate_proposal": self._run_proposal_generation,
                "create_invoice": self._run_invoice_creation
            }

            if skill_name not in skill_commands:
                return {"status": "error", "message": f"Unknown skill: {skill_name}"}

            return await skill_commands[skill_name](params)

        except Exception as e:
            logger.error(f"CashClaw bridge error for {skill_name}: {e}")
            return {"status": "error", "message": str(e)}

    async def _run_seo_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SEO audit via CashClaw CLI."""
        url = params.get("url", "")
        if not url:
            return {"status": "error", "message": "URL required for SEO audit"}

        try:
            # Run CashClaw SEO audit
            result = subprocess.run([
                "cashclaw", "audit", "--url", url, "--tier", "standard",
                "--output", f"audit_{url.replace('https://', '').replace('/', '_')}.md"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "seo_audit",
                    "url": url,
                    "output_file": f"audit_{url.replace('https://', '').replace('/', '_')}.md",
                    "message": "SEO audit completed successfully"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"SEO audit failed: {str(e)}"}

    async def _run_lead_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute lead generation via CashClaw CLI."""
        icp = params.get("icp", "")
        count = params.get("count", 25)

        if not icp:
            return {"status": "error", "message": "ICP (Ideal Customer Profile) required"}

        try:
            result = subprocess.run([
                "cashclaw", "leads", "--icp", icp, "--count", str(count),
                "--output", f"leads_{icp.replace(' ', '_')}_{count}.json"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "lead_generation",
                    "icp": icp,
                    "count": count,
                    "output_file": f"leads_{icp.replace(' ', '_')}_{count}.json",
                    "message": f"Generated {count} leads for {icp}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Lead generation failed: {str(e)}"}

    async def _run_content_creation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute content creation via CashClaw CLI."""
        content_type = params.get("type", "blog")
        topic = params.get("topic", "")
        word_count = params.get("word_count", 1500)

        if not topic:
            return {"status": "error", "message": "Topic required for content creation"}

        try:
            result = subprocess.run([
                "cashclaw", "content",
                "--type", content_type,
                "--words", str(word_count),
                "--keyword", topic,
                "--output", f"content_{content_type}_{topic.replace(' ', '_')}.md"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "content_creation",
                    "type": content_type,
                    "topic": topic,
                    "word_count": word_count,
                    "output_file": f"content_{content_type}_{topic.replace(' ', '_')}.md",
                    "message": f"Created {word_count}-word {content_type} about {topic}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Content creation failed: {str(e)}"}

    async def _run_email_outreach(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute email outreach via CashClaw CLI."""
        icp = params.get("icp", "")
        sequence_length = params.get("sequence_length", 3)

        if not icp:
            return {"status": "error", "message": "ICP required for email outreach"}

        try:
            result = subprocess.run([
                "cashclaw", "outreach",
                "--icp", icp,
                "--sequence", str(sequence_length),
                "--tier", "basic"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "email_outreach",
                    "icp": icp,
                    "sequence_length": sequence_length,
                    "message": f"Initiated {sequence_length}-sequence outreach to {icp}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Email outreach failed: {str(e)}"}

    async def _run_competitor_analysis(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute competitor analysis via CashClaw CLI."""
        target_url = params.get("target_url", "")

        if not target_url:
            return {"status": "error", "message": "Target URL required for competitor analysis"}

        try:
            result = subprocess.run([
                "cashclaw", "compete",
                "--target", target_url,
                "--tier", "basic",
                "--output", f"competitor_analysis_{target_url.replace('https://', '').replace('/', '_')}.md"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "competitor_analysis",
                    "target_url": target_url,
                    "output_file": f"competitor_analysis_{target_url.replace('https://', '').replace('/', '_')}.md",
                    "message": f"Completed competitor analysis for {target_url}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Competitor analysis failed: {str(e)}"}

    async def _run_data_scraping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data scraping via CashClaw CLI."""
        source_url = params.get("source_url", "")
        count = params.get("count", 50)

        if not source_url:
            return {"status": "error", "message": "Source URL required for data scraping"}

        try:
            result = subprocess.run([
                "cashclaw", "scrape",
                "--source", source_url,
                "--count", str(count),
                "--output", f"scraped_data_{source_url.replace('https://', '').replace('/', '_')}.csv"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "data_scraping",
                    "source_url": source_url,
                    "count": count,
                    "output_file": f"scraped_data_{source_url.replace('https://', '').replace('/', '_')}.csv",
                    "message": f"Scraped {count} records from {source_url}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Data scraping failed: {str(e)}"}

    async def _run_landing_page(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute landing page creation via CashClaw CLI."""
        product = params.get("product", "")

        if not product:
            return {"status": "error", "message": "Product description required for landing page"}

        try:
            result = subprocess.run([
                "cashclaw", "landing",
                "--product", product,
                "--tier", "standard"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "landing_page",
                    "product": product,
                    "message": f"Created landing page for {product}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Landing page creation failed: {str(e)}"}

    async def _run_reputation_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute reputation audit via CashClaw CLI."""
        brand = params.get("brand", "")

        if not brand:
            return {"status": "error", "message": "Brand name required for reputation audit"}

        try:
            result = subprocess.run([
                "cashclaw", "reputation",
                "--brand", brand,
                "--tier", "basic"
            ], capture_output=True, text=True, cwd=os.getcwd())

            if result.returncode == 0:
                return {
                    "status": "success",
                    "skill": "reputation_audit",
                    "brand": brand,
                    "message": f"Completed reputation audit for {brand}"
                }
            else:
                return {"status": "error", "message": result.stderr}

        except Exception as e:
            return {"status": "error", "message": f"Reputation audit failed: {str(e)}"}

    async def _run_proposal_generation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate business proposal using CashClaw."""
        client_data = params.get("client_data", {})
        return self.cashclaw.generate_mission_proposal(client_data)

    async def _run_invoice_creation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create invoice using CashClaw."""
        invoice_data = params.get("invoice_data", {})
        return self.cashclaw.confirm_payment(invoice_data.get("mission_id", ""))

    async def get_available_services(self) -> List[Dict[str, Any]]:
        """Get list of available CashClaw services."""
        return [
            {
                "name": "seo_audit",
                "description": "Complete SEO audit with actionable recommendations",
                "pricing": {"standard": 29, "pro": 59}
            },
            {
                "name": "lead_generation",
                "description": "Generate qualified leads based on ICP",
                "pricing": {"25_leads": 9, "50_leads": 15, "100_leads": 25}
            },
            {
                "name": "content_creation",
                "description": "Write high-quality blog posts, newsletters, or copy",
                "pricing": {"500w": 5, "1500w": 12}
            },
            {
                "name": "email_outreach",
                "description": "Execute multi-touch email sequences",
                "pricing": {"3_sequence": 9, "7_sequence": 19}
            },
            {
                "name": "competitor_analysis",
                "description": "Deep competitor intelligence and positioning",
                "pricing": {"1_competitor": 19, "5_competitors": 35}
            },
            {
                "name": "data_scraping",
                "description": "Extract structured data from websites",
                "pricing": {"50_records": 9, "500_records": 19}
            }
        ]

    async def get_marketplace_status(self) -> Dict[str, Any]:
        """Check HYRVE AI marketplace connection status."""
        try:
            result = subprocess.run([
                "cashclaw", "hyrve", "status"
            ], capture_output=True, text=True, cwd=os.getcwd())

            return {
                "status": "success" if result.returncode == 0 else "error",
                "message": result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
            }
        except Exception as e:
            return {"status": "error", "message": f"Marketplace check failed: {str(e)}"}