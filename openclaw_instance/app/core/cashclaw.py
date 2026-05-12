"""
CashClaw Business Layer - OROVA Revenue Engine
Handles invoicing, Wise payments, and mission audit trails.
No Stripe - uses Wise for Philippines-based operations.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from .hermes_state import HermesState

logger = logging.getLogger(__name__)

class CashClaw:
    """
    Revenue engine for OROVA missions.
    Handles professional proposals, Wise payments, and ROI tracking.
    """

    def __init__(self, tenant_config: Dict[str, Any]):
        self.tenant = tenant_config
        self.wise_details = tenant_config.get("wise_bank_details", {})

    def generate_mission_proposal(self, client_data: Dict[str, Any]) -> str:
        """
        Generate professional PDF proposal for a mission.
        Returns PDF file path.
        """
        filename = f"mission_proposal_{client_data['name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Header
        story.append(Paragraph("OROVA Mission Proposal", styles['Heading1']))
        story.append(Spacer(1, 12))

        # Client details
        story.append(Paragraph(f"Client: {client_data['name']}", styles['Heading2']))
        story.append(Paragraph(f"Niche: {self.tenant['niche']}", styles['Normal']))
        story.append(Spacer(1, 12))

        # Services
        story.append(Paragraph("Services Included:", styles['Heading3']))
        services = [
            "AI-Powered Lead Generation (24/7)",
            "Meta Ads Campaign Management",
            "Personalized Outreach Sequences",
            "Performance Analytics & ROI Tracking",
            "Dedicated Mission Control Dashboard"
        ]

        for service in services:
            story.append(Paragraph(f"• {service}", styles['Normal']))

        story.append(Spacer(1, 12))

        # Pricing
        story.append(Paragraph("Investment: $2,500/month", styles['Heading3']))
        story.append(Spacer(1, 12))

        # Manual Wire Transfer block
        story.append(Paragraph("Manual Wire Transfer", styles['Heading3']))
        story.append(Paragraph("Payment Terms: Monthly via Wise Transfer", styles['Normal']))
        story.append(Spacer(1, 6))

        # USD Details
        story.append(Paragraph("USD Bank Details (Wise):", styles['Normal']))
        story.append(Paragraph(f"Account Name: {self.wise_details.get('usd_name', 'OROVA Inc.')}", styles['Normal']))
        story.append(Paragraph(f"Account Number: {self.wise_details.get('usd_account', 'Contact OROVA for details')}", styles['Normal']))
        story.append(Paragraph(f"Routing Number: {self.wise_details.get('usd_routing', '021000021')}", styles['Normal']))
        story.append(Paragraph("Bank Name: Wise US Inc / JP Morgan Chase Bank", styles['Normal']))
        story.append(Paragraph("Address: 30 W 26th Street, New York, NY 10010", styles['Normal']))
        story.append(Spacer(1, 6))

        # EUR Details
        story.append(Paragraph("EUR Bank Details (Wise):", styles['Normal']))
        story.append(Paragraph(f"IBAN: {self.wise_details.get('eur_iban', 'Contact OROVA for details')}", styles['Normal']))
        story.append(Paragraph(f"BIC/SWIFT: {self.wise_details.get('eur_bic', 'TRWIBEBB')}", styles['Normal']))
        story.append(Paragraph("Bank Name: Wise Europe SA", styles['Normal']))
        story.append(Paragraph("Address: Rue du Trône 100 bte 3, 1050 Brussels, Belgium", styles['Normal']))
        story.append(Spacer(1, 12))

        # ROI Projection
        story.append(Paragraph("Expected ROI: 300-500%", styles['Heading3']))
        story.append(Paragraph("Based on historical performance across luxury niches", styles['Normal']))

        doc.build(story)
        return filename

    def calculate_roi(self, revenue: float, spend: float) -> Dict[str, Any]:
        """
        Calculate ROI metrics for mission audit trail.
        Formula: ROI = ((Revenue - Spend) / Spend) * 100
        """
        if spend == 0:
            return {"roi_percentage": 0, "net_profit": 0, "status": "invalid"}

        net_profit = revenue - spend
        roi_percentage = (net_profit / spend) * 100

        status = "profitable" if roi_percentage > 0 else "loss"

        return {
            "roi_percentage": round(roi_percentage, 2),
            "net_profit": round(net_profit, 2),
            "revenue": revenue,
            "spend": spend,
            "status": status
        }

    def generate_weekly_audit(self, mission_data: Dict[str, Any]) -> str:
        """
        Generate weekly mission audit trail PDF.
        Includes leads, Meta Ads ROAS, and proof of action.
        """
        filename = f"weekly_audit_{mission_data['client_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Header
        story.append(Paragraph("OROVA Weekly Mission Audit", styles['Heading1']))
        story.append(Paragraph(f"Client: {mission_data['client_name']}", styles['Heading2']))
        story.append(Paragraph(f"Week Ending: {datetime.now().strftime('%B %d, %Y')}", styles['Normal']))
        story.append(Spacer(1, 12))

        # Performance Summary
        story.append(Paragraph("Performance Summary:", styles['Heading3']))

        data = [
            ["Metric", "This Week", "Target"],
            ["Total Leads Generated", str(mission_data.get('leads_generated', 0)), "50+"],
            ["Qualified Leads", str(mission_data.get('qualified_leads', 0)), "15+"],
            ["Meta Ads Spend", f"${mission_data.get('meta_spend', 0)}", "$500"],
            ["Meta Ads CTR", f"{mission_data.get('meta_ctr', 0)}%", "2.5%+"],
            ["ROAS", f"{mission_data.get('roas', 0)}", "2.0+"]
        ]

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        story.append(table)
        story.append(Spacer(1, 12))

        # ROI Calculation
        revenue = mission_data.get('revenue', 0)
        spend = mission_data.get('meta_spend', 0) + mission_data.get('other_spend', 0)

        roi_data = self.calculate_roi(revenue, spend)

        story.append(Paragraph("ROI Analysis:", styles['Heading3']))
        story.append(Paragraph(f"Total Revenue: ${revenue}", styles['Normal']))
        story.append(Paragraph(f"Total Spend: ${spend}", styles['Normal']))
        story.append(Paragraph(f"Net Profit: ${roi_data['net_profit']}", styles['Normal']))
        story.append(Paragraph(f"ROI: {roi_data['roi_percentage']}%", styles['Normal']))
        story.append(Paragraph(f"Status: {roi_data['status'].upper()}", styles['Normal']))

        story.append(Spacer(1, 12))

        # Proof of Action
        story.append(Paragraph("Proof of Action This Week:", styles['Heading3']))
        actions = mission_data.get('proof_of_action', [])
        for action in actions:
            story.append(Paragraph(f"• {action}", styles['Normal']))

        story.append(Spacer(1, 12))

        # Strategic Reasoning Snippets
        story.append(Paragraph("AI Strategic Reasoning Snippets:", styles['Heading3']))
        state = HermesState()
        week_ago = datetime.now() - timedelta(days=7)
        week_ago_ts = week_ago.timestamp()

        # Query recent reasoning
        conn = state.conn
        cursor = conn.execute("""
            SELECT reasoning FROM messages
            WHERE reasoning IS NOT NULL AND reasoning != ''
            AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (week_ago_ts,))
        reasonings = cursor.fetchall()

        for i, (reasoning,) in enumerate(reasonings):
            lines = reasoning.split('\n')[:5]  # First 5 lines
            snippet = '\n'.join(lines)
            story.append(Paragraph(f"Snippet {i+1}:", styles['Heading4']))
            story.append(Paragraph(snippet, styles['Normal']))
            story.append(Spacer(1, 6))

        doc.build(story)
        return filename

    def confirm_payment(self, mission_id: str) -> bool:
        """
        Manual payment confirmation for Wise transfers.
        In production, this would integrate with Wise API for automated verification.
        """
        logger.info(f"Payment confirmed for mission {mission_id}")
        # TODO: Integrate with Wise API for automatic verification
        return True