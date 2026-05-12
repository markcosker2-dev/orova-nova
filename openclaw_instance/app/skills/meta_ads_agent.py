# -*- coding: utf-8 -*-
"""
app/skills/meta_ads_agent.py
OROVA Autonomous Media Buyer — Meta Graph API integration.

STRICT CONSTRAINTS (zero hallucination policy):
  - ALL data comes from Meta API responses only. No invented metrics.
  - Budget actions execute ONLY via explicit API calls. No fabricated numbers.
  - Every PAUSE action is logged with the exact metric that triggered it.
  - Gemini is used ONLY for ad copy generation, never for performance data.

API version: Meta Marketing API v19.0 (current as of Q1 2026)
SDK: facebook-business (install: pip install facebook-business)
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from app.core.database import DatabaseManager

logger = logging.getLogger("orova.meta_ads")

# Meta API version — update quarterly
META_API_VERSION = "v19.0"
META_GRAPH_BASE  = f"https://graph.facebook.com/{META_API_VERSION}"

# KPI thresholds for autonomous PAUSE decisions
# These are OROVA defaults — each client config can override them
DEFAULT_KPI_THRESHOLDS = {
    "max_cpl":         150.0,   # Pause if cost-per-lead exceeds $150
    "min_roas":          2.0,   # Pause if ROAS drops below 2.0x
    "min_spend_before_decision": 50.0,  # Don't pause until $50+ spent
    "max_frequency":     4.0,   # Pause if ad frequency > 4 (creative fatigue)
    "min_ctr":           0.5,   # Pause if CTR drops below 0.5%
    "evaluation_days":   3,     # Evaluate over 3-day window
}

class MetaAdsAgent:
    """
    Autonomous Media Buyer for OROVA's Meta Lead Gen service tier.
    """

    def __init__(self):
        self.db            = DatabaseManager()
        self.access_token  = os.getenv("META_ACCESS_TOKEN", "")
        self.ad_account_id = os.getenv("META_AD_ACCOUNT_ID", "")
        self.agency_name   = os.getenv("AGENCY_NAME", "OROVA")

        if not self.access_token:
            logger.warning("[META ADS] META_ACCESS_TOKEN not set")
        if not self.ad_account_id:
            logger.warning("[META ADS] META_AD_ACCOUNT_ID not set — format: act_XXXXXXXXXX")

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Execute a GET request to the Meta Graph API."""
        import requests
        params = params or {}
        params["access_token"] = self.access_token
        url = f"{META_GRAPH_BASE}/{endpoint}"
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            logger.error(
                f"[META ADS] API error {resp.status_code}: "
                + json.dumps(body.get("error", {}))
            )
            return None
        except Exception as e:
            logger.error(f"[META ADS] Request failed: {e}")
            return None

    def _post(self, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """Execute a POST request to the Meta Graph API."""
        import requests
        data = data or {}
        data["access_token"] = self.access_token
        url = f"{META_GRAPH_BASE}/{endpoint}"
        try:
            resp = requests.post(url, data=data, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[META ADS] POST failed to {endpoint}: {e}")
            return None

    # ── REPORTING ─────────────────────────────────────────────────────────
    def get_account_performance(
        self, date_preset: str = "last_7d"
    ) -> Optional[Dict[str, Any]]:
        """Pull top-level ad account performance from Meta API."""
        if not self.ad_account_id:
            return {"error": "META_AD_ACCOUNT_ID not configured"}

        account_id = self.ad_account_id.lstrip("act_")
        data = self._get(
            f"act_{account_id}/insights",
            params={
                "fields": (
                    "spend,impressions,clicks,ctr,cpc,cpm,"
                    "actions,action_values,frequency"
                ),
                "date_preset":  date_preset,
                "level":        "account",
                "action_attribution_windows": '["7d_click","1d_view"]',
            },
        )

        if not data or "data" not in data or not data["data"]:
            return {"error": "No data returned from Meta API", "date_preset": date_preset}

        raw = data["data"][0]

        leads = 0
        purchase_value = 0.0
        for action in raw.get("actions", []):
            if action.get("action_type") in ("lead", "leadgen_other"):
                leads += int(action.get("value", 0))
        for action_val in raw.get("action_values", []):
            if action_val.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
                purchase_value += float(action_val.get("value", 0))

        spend = float(raw.get("spend", 0))

        cpl  = round(spend / leads, 2) if leads > 0 else None
        roas = round(purchase_value / spend, 2) if spend > 0 else None

        return {
            "date_preset":   date_preset,
            "spend":         spend,
            "impressions":   int(raw.get("impressions", 0)),
            "clicks":        int(raw.get("clicks", 0)),
            "ctr":           round(float(raw.get("ctr", 0)), 2),
            "cpc":           round(float(raw.get("cpc", 0)), 2),
            "cpm":           round(float(raw.get("cpm", 0)), 2),
            "frequency":     round(float(raw.get("frequency", 0)), 2),
            "leads":         leads,
            "cpl":           cpl,
            "purchase_value":purchase_value,
            "roas":          roas,
            "data_source":   "meta_graph_api_v19",
            "pulled_at":     datetime.utcnow().isoformat(),
        }

    def get_ad_set_performance(
        self, date_preset: str = "last_7d"
    ) -> List[Dict[str, Any]]:
        """Pull per-ad-set performance."""
        if not self.ad_account_id:
            return []

        account_id = self.ad_account_id.lstrip("act_")
        data = self._get(
            f"act_{account_id}/insights",
            params={
                "fields": (
                    "adset_id,adset_name,spend,impressions,clicks,"
                    "ctr,frequency,actions,action_values"
                ),
                "date_preset":  date_preset,
                "level":        "adset",
                "action_attribution_windows": '["7d_click","1d_view"]',
            },
        )

        if not data or "data" not in data:
            return []

        ad_sets = []
        for row in data["data"]:
            spend = float(row.get("spend", 0))
            leads = sum(
                int(a.get("value", 0))
                for a in row.get("actions", [])
                if a.get("action_type") in ("lead", "leadgen_other")
            )
            purchase_value = sum(
                float(a.get("value", 0))
                for a in row.get("action_values", [])
                if a.get("action_type") in (
                    "purchase", "offsite_conversion.fb_pixel_purchase"
                )
            )

            cpl  = round(spend / leads, 2) if leads > 0 else None
            roas = round(purchase_value / spend, 2) if spend > 0 else None

            ad_sets.append({
                "adset_id":   row.get("adset_id"),
                "adset_name": row.get("adset_name"),
                "spend":      spend,
                "leads":      leads,
                "cpl":        cpl,
                "roas":       roas,
                "ctr":        round(float(row.get("ctr", 0)), 2),
                "frequency":  round(float(row.get("frequency", 0)), 2),
            })
        return ad_sets

    # ── BUDGET PROTECTION ─────────────────────────────────────────────────
    def evaluate_and_pause_underperformers(
        self,
        thresholds: Dict = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Evaluate ad sets against KPI thresholds and pause underperforming ones."""
        thresholds = thresholds or DEFAULT_KPI_THRESHOLDS
        ad_sets    = self.get_ad_set_performance(
            date_preset=f"last_{thresholds['evaluation_days']}d"
        )

        paused     = []
        skipped    = []
        evaluated  = []

        for ad_set in ad_sets:
            adset_id   = ad_set["adset_id"]
            adset_name = ad_set["adset_name"]
            spend      = ad_set["spend"]

            if spend < thresholds["min_spend_before_decision"]:
                skipped.append({
                    "adset_id":   adset_id,
                    "adset_name": adset_name,
                    "reason":     f"Insufficient spend (${spend:.2f})",
                })
                continue

            pause_reason = None
            if ad_set["cpl"] and ad_set["cpl"] > thresholds["max_cpl"]:
                pause_reason = f"CPL > {thresholds['max_cpl']}"
            elif ad_set["roas"] is not None and ad_set["roas"] < thresholds["min_roas"]:
                pause_reason = f"ROAS < {thresholds['min_roas']}"
            elif ad_set["frequency"] > thresholds["max_frequency"]:
                pause_reason = f"Freq > {thresholds['max_frequency']}"
            elif ad_set["ctr"] < thresholds["min_ctr"]:
                pause_reason = f"CTR < {thresholds['min_ctr']}"

            if pause_reason:
                evaluated.append({
                    "adset_id":    adset_id,
                    "adset_name":  adset_name,
                    "pause_reason":pause_reason,
                    "kpis":        ad_set,
                    "action":      "DRY_RUN_PAUSE" if dry_run else "PAUSED",
                })

                if not dry_run:
                    result = self._pause_ad_set(adset_id)
                    if result:
                        paused.append({
                            "adset_id":    adset_id,
                            "adset_name":  adset_name,
                            "pause_reason":pause_reason,
                            "paused_at":   datetime.utcnow().isoformat(),
                        })
                        logger.info(f"[META ADS] PAUSED: '{adset_name}' — {pause_reason}")

        summary = {
            "ad_sets_evaluated":     len(ad_sets),
            "skipped_low_spend":     len(skipped),
            "flagged_for_pause":     len(evaluated),
            "successfully_paused":   len(paused),
            "dry_run":               dry_run,
            "thresholds_applied":    thresholds,
            "evaluated_at":          datetime.utcnow().isoformat(),
            "paused_details":        paused,
            "evaluated_details":     evaluated,
        }
        return summary

    def _pause_ad_set(self, adset_id: str) -> bool:
        """Execute PAUSE via API."""
        result = self._post(f"{adset_id}", data={"status": "PAUSED"})
        return result and result.get("success", False)

    # ── AD COPY GENERATION ────────────────────────────────────────────────
    def generate_luxury_ad_copy(
        self,
        vertical: str,
        asset_description: str,
        objective: str = "Lead Generation",
        client_name: str = "",
    ) -> Dict[str, str]:
        """Generate luxury ad copy using AI client."""
        # Use our existing internal UnifiedAIClient so we adhere to our architecture
        from app.core.ai_client import UnifiedAIClient
        import asyncio
        import json

        prompt = f"""
You are writing Meta ad copy for a premium AI lead generation agency's client.

Client vertical: {vertical}
Campaign objective: {objective}
Visual asset: {asset_description}
Client: {client_name or 'Premium ' + vertical + ' business'}
Agency: {self.agency_name}

LUXURY FILTER RULES (mandatory):
  — No exclamation marks
  — No "affordable," "cheap," "discount," "easy"
  — No generic calls to action ("Click here," "Learn more")
  — Tone: Understated authority. Executive-to-executive.
  — Value prop: ROI, precision, efficiency, exclusivity

Write four distinct ad copy components:
1. PRIMARY TEXT (Facebook feed copy — 1-3 sentences, under 125 words)
2. HEADLINE (Facebook headline — under 40 characters, punchy)
3. DESCRIPTION (Below headline — under 30 characters)
4. CTA BUTTON TEXT (choose one: Get Quote, Learn More, Book Now, Contact Us, Apply Now)

Return ONLY valid JSON:
{{
  "primary_text": "...",
  "headline": "...",
  "description": "...",
  "cta": "...",
  "vertical": "{vertical}"
}}
"""
        
        # We need a sync wrapper around the async write function
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        try:
            ai = UnifiedAIClient()
            raw = loop.run_until_complete(ai.write(prompt, model="gemini-2.0-flash"))
            raw = raw.strip().replace("```json","").replace("```","").strip()
            copy = json.loads(raw)
            logger.info(f"[META ADS] Ad copy generated for {vertical}")
            return copy
        except Exception as e:
            logger.error(f"[META ADS] Ad copy generation failed: {e}")
            return {
                "primary_text": f"We engineer qualified leads for {vertical} businesses. Precision outreach. Measurable outcomes.",
                "headline": "Qualified Leads. Guaranteed.",
                "description": f"For {vertical} operators.",
                "cta": "Get Quote",
                "vertical": vertical,
            }

    # ── WEEKLY REPORT ─────────────────────────────────────────────────────
    def generate_weekly_report(self, client_name: str = "") -> Dict[str, Any]:
        """Generate a complete weekly Meta Ads performance report."""
        perf_7d  = self.get_account_performance("last_7d")
        perf_30d = self.get_account_performance("last_30d")
        ad_sets  = self.get_ad_set_performance("last_7d")

        return {
            "client":         client_name,
            "report_date":    datetime.utcnow().strftime("%B %d, %Y"),
            "period_7d":      perf_7d,
            "period_30d":     perf_30d,
            "ad_set_count":   len(ad_sets),
            "ad_set_details": ad_sets,
            "data_source":    "meta_graph_api_v19",
            "generated_at":   datetime.utcnow().isoformat(),
        }
