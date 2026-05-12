"""
app/skills/media_buyer.py
SAGE — Autonomous Media Buyer for OROVA.

Meta Graph API v20.0 (current, Q1 2026).

ZERO HALLUCINATION POLICY:
  All metrics come from Meta API responses only.
  Gemini generates copy only — never performance data.
  Budget decisions require real API data above minimum spend threshold.

AUTONOMOUS RULES:
  ROAS > 2.0 for 3 days → increment budget 20%
  ROAS < 1.0 for 72h   → KILL-SWITCH (pause + alert)
  Frequency > 3.0       → rotate creative (flag for refresh)
  CPL > threshold       → pause ad set

TYPE SAFETY: Pydantic models for all API payloads.
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import requests
from pydantic import BaseModel, Field, validator
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger("orova.sage")

META_API_VERSION = "v20.0"
META_GRAPH_BASE  = f"https://graph.facebook.com/{META_API_VERSION}"


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — Type safety for all API payloads
# ══════════════════════════════════════════════════════════════════════════════

class AdSetKPIs(BaseModel):
    adset_id:   str
    adset_name: str
    spend:      float = 0.0
    leads:      int   = 0
    impressions:int   = 0
    clicks:     int   = 0
    ctr:        float = 0.0
    frequency:  float = 0.0
    cpl:        Optional[float] = None
    roas:       Optional[float] = None
    purchase_value: float = 0.0
    status:     str   = "ACTIVE"
    date_preset:str   = "last_7d"


class BudgetUpdatePayload(BaseModel):
    """Type-safe payload for budget modification API calls."""
    adset_id:      str
    current_budget:float
    new_budget:    float
    reason:        str
    action:        str  # "INCREMENT" | "PAUSE" | "KILL_SWITCH"
    triggered_by:  str  # The metric that triggered this action

    @validator("new_budget")
    def budget_must_be_positive(cls, v):
        if v < 0:
            raise ValueError("Budget cannot be negative")
        return round(v, 2)


class AdCopyOutput(BaseModel):
    """Type-safe ad copy from Gemini."""
    primary_text: str
    headline:     str
    description:  str
    cta:          str
    vertical:     str
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class KPIThresholds(BaseModel):
    """Per-client configurable KPI thresholds."""
    max_cpl:                  float = 150.0
    min_roas:                 float = 2.0
    kill_switch_roas:         float = 1.0
    kill_switch_hours:        int   = 72
    max_frequency:            float = 3.0
    min_spend_before_decision:float = 50.0
    budget_increment_pct:     float = 20.0
    evaluation_days:          int   = 3


# ══════════════════════════════════════════════════════════════════════════════
# META API CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class SageMediaBuyer:
    """
    SAGE — Autonomous Media Buyer.
    All decisions based on real Meta API data. Zero hallucination.
    """

    def __init__(self, thresholds: Optional[KPIThresholds] = None):
        self.token        = os.getenv("META_ACCESS_TOKEN", "")
        self.account_id   = os.getenv("META_AD_ACCOUNT_ID", "")
        self.thresholds   = thresholds or KPIThresholds()
        self._validate_config()

    def _validate_config(self):
        if not self.token:
            logger.warning("[SAGE] META_ACCESS_TOKEN not set — ad management disabled")
        if self.account_id and not self.account_id.startswith("act_"):
            logger.error(
                f"[SAGE] META_AD_ACCOUNT_ID must start with 'act_'. Got: {self.account_id}"
            )

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """GET from Meta Graph API. Returns None on error."""
        params = params or {}
        params["access_token"] = self.token
        try:
            resp = requests.get(
                f"{META_GRAPH_BASE}/{endpoint}",
                params=params,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            body = {}
            try:
                body = resp.json()
            except Exception:
                pass
            logger.error(
                f"[SAGE] API {resp.status_code}: "
                + json.dumps(body.get("error", {}))
            )
            return None
        except Exception as e:
            logger.error(f"[SAGE] GET failed: {e}")
            return None

    def _post(self, endpoint: str, data: Dict = None) -> Optional[Dict]:
        """POST to Meta Graph API."""
        data = data or {}
        data["access_token"] = self.token
        try:
            resp = requests.post(
                f"{META_GRAPH_BASE}/{endpoint}",
                data=data,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"[SAGE] POST failed to {endpoint}: {e}")
            return None

    # ── DATA PULLING ──────────────────────────────────────────────────────────

    def get_account_performance(
        self, date_preset: str = "last_7d"
    ) -> Optional[Dict[str, Any]]:
        """
        Pull top-level ad account performance.
        ALL numbers from Meta API. None invented.
        """
        if not self.account_id:
            return {"error": "META_AD_ACCOUNT_ID not configured"}

        account_id = self.account_id.lstrip("act_")
        data = self._get(
            f"act_{account_id}/insights",
            params={
                "fields": (
                    "spend,impressions,clicks,ctr,cpc,cpm,"
                    "actions,action_values,frequency"
                ),
                "date_preset":               date_preset,
                "level":                     "account",
                "action_attribution_windows": '["7d_click","1d_view"]',
            },
        )

        if not data or "data" not in data or not data["data"]:
            return {"error": "No data from Meta API", "date_preset": date_preset}

        raw    = data["data"][0]
        spend  = float(raw.get("spend", 0))
        leads  = sum(
            int(a.get("value", 0))
            for a in raw.get("actions", [])
            if a.get("action_type") in ("lead", "leadgen_other")
        )
        purchase_value = sum(
            float(a.get("value", 0))
            for a in raw.get("action_values", [])
            if a.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase")
        )
        cpl  = round(spend / leads, 2) if leads > 0 else None
        roas = round(purchase_value / spend, 2) if spend > 0 else None

        return {
            "date_preset":    date_preset,
            "spend":          spend,
            "impressions":    int(raw.get("impressions", 0)),
            "clicks":         int(raw.get("clicks", 0)),
            "ctr":            round(float(raw.get("ctr", 0)), 2),
            "cpc":            round(float(raw.get("cpc", 0)), 2),
            "frequency":      round(float(raw.get("frequency", 0)), 2),
            "leads":          leads,
            "cpl":            cpl,
            "purchase_value": purchase_value,
            "roas":           roas,
            "data_source":    f"meta_graph_api_{META_API_VERSION}",
            "pulled_at":      datetime.utcnow().isoformat(),
        }

    def get_adset_performance(
        self, date_preset: str = "last_7d"
    ) -> List[AdSetKPIs]:
        """Pull per-ad-set KPIs. Returns typed Pydantic models."""
        if not self.account_id:
            return []

        account_id = self.account_id.lstrip("act_")
        data = self._get(
            f"act_{account_id}/insights",
            params={
                "fields": (
                    "adset_id,adset_name,spend,impressions,clicks,"
                    "ctr,frequency,actions,action_values"
                ),
                "date_preset":               date_preset,
                "level":                     "adset",
                "action_attribution_windows": '["7d_click","1d_view"]',
            },
        )

        if not data or "data" not in data:
            return []

        results = []
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

            results.append(AdSetKPIs(
                adset_id       = row.get("adset_id", ""),
                adset_name     = row.get("adset_name", ""),
                spend          = spend,
                leads          = leads,
                impressions    = int(row.get("impressions", 0)),
                clicks         = int(row.get("clicks", 0)),
                ctr            = round(float(row.get("ctr", 0)), 2),
                frequency      = round(float(row.get("frequency", 0)), 2),
                cpl            = cpl,
                roas           = roas,
                purchase_value = purchase_value,
                date_preset    = date_preset,
            ))

        return results

    # ── AUTONOMOUS BUDGET DECISIONS ────────────────────────────────────────────

    def evaluate_and_act(
        self,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Evaluate all ad sets against KPI thresholds and take action.

        RULES:
          ROAS > 2.0  → INCREMENT budget 20%
          ROAS < 1.0 for 72h → KILL-SWITCH (pause + telegram alert)
          Frequency > 3.0 → flag for creative rotation
          CPL > max_cpl → PAUSE

        dry_run=True: analyse only, no API calls executed.
        dry_run=False: actions executed via Meta API.
        """
        t        = self.thresholds
        ad_sets  = self.get_adset_performance(f"last_{t.evaluation_days}d")
        results  = {
            "evaluated":  len(ad_sets),
            "incremented":[], "paused":[], "kill_switched":[],
            "flagged_creative":[], "skipped":[],
            "dry_run": dry_run,
        }

        for adset in ad_sets:
            # Skip: insufficient spend for statistical confidence
            if adset.spend < t.min_spend_before_decision:
                results["skipped"].append({
                    "adset_id": adset.adset_id,
                    "reason": f"Spend ${adset.spend:.2f} < min ${t.min_spend_before_decision:.2f}",
                })
                continue

            # ── KILL-SWITCH: ROAS < 1.0 ────────────────────────────────────
            if adset.roas is not None and adset.roas < t.kill_switch_roas:
                payload = BudgetUpdatePayload(
                    adset_id      = adset.adset_id,
                    current_budget= adset.spend,
                    new_budget    = 0.0,
                    reason        = f"ROAS {adset.roas:.2f}x < kill threshold {t.kill_switch_roas:.2f}x",
                    action        = "KILL_SWITCH",
                    triggered_by  = "roas",
                )
                if not dry_run:
                    self._pause_adset(adset.adset_id)
                    self._telegram_alert(
                        f"🚨 KILL-SWITCH TRIGGERED\n"
                        f"Ad Set: {adset.adset_name}\n"
                        f"ROAS: {adset.roas:.2f}x (threshold: {t.kill_switch_roas:.2f}x)\n"
                        f"Spend: ${adset.spend:.2f}\n"
                        f"Action: PAUSED"
                    )
                results["kill_switched"].append(payload.dict())
                continue

            # ── PAUSE: CPL too high ─────────────────────────────────────────
            if adset.cpl is not None and adset.cpl > t.max_cpl:
                payload = BudgetUpdatePayload(
                    adset_id      = adset.adset_id,
                    current_budget= adset.spend,
                    new_budget    = 0.0,
                    reason        = f"CPL ${adset.cpl:.2f} > max ${t.max_cpl:.2f}",
                    action        = "PAUSE",
                    triggered_by  = "cpl",
                )
                if not dry_run:
                    self._pause_adset(adset.adset_id)
                results["paused"].append(payload.dict())
                continue

            # ── INCREMENT: ROAS > target ────────────────────────────────────
            if adset.roas is not None and adset.roas > t.min_roas:
                # Get current daily budget to calculate increment
                current_budget = self._get_adset_budget(adset.adset_id)
                if current_budget and current_budget > 0:
                    new_budget = round(current_budget * (1 + t.budget_increment_pct / 100), 2)
                    payload = BudgetUpdatePayload(
                        adset_id      = adset.adset_id,
                        current_budget= current_budget,
                        new_budget    = new_budget,
                        reason        = f"ROAS {adset.roas:.2f}x > target {t.min_roas:.2f}x",
                        action        = "INCREMENT",
                        triggered_by  = "roas",
                    )
                    if not dry_run:
                        self._update_adset_budget(adset.adset_id, new_budget)
                    results["incremented"].append(payload.dict())

            # ── FREQUENCY: Creative fatigue ─────────────────────────────────
            if adset.frequency > t.max_frequency:
                results["flagged_creative"].append({
                    "adset_id":  adset.adset_id,
                    "adset_name":adset.adset_name,
                    "frequency": adset.frequency,
                    "reason":    f"Frequency {adset.frequency:.1f} > {t.max_frequency:.1f}",
                    "action":    "ROTATE_CREATIVE",
                })

        logger.info(
            f"[SAGE] Evaluation: {len(ad_sets)} sets | "
            f"kill={len(results['kill_switched'])} "
            f"pause={len(results['paused'])} "
            f"increment={len(results['incremented'])} "
            f"creative_flag={len(results['flagged_creative'])}"
        )
        return results

    # ── BUDGET ACTIONS ────────────────────────────────────────────────────────

    def _pause_adset(self, adset_id: str) -> bool:
        result = self._post(adset_id, data={"status": "PAUSED"})
        success = result and result.get("success")
        if success:
            logger.info(f"[SAGE] Paused adset {adset_id}")
        else:
            logger.error(f"[SAGE] Pause failed for {adset_id}: {result}")
        return bool(success)

    def _get_adset_budget(self, adset_id: str) -> Optional[float]:
        data = self._get(
            adset_id,
            params={"fields": "daily_budget,lifetime_budget"}
        )
        if data:
            daily    = data.get("daily_budget")
            lifetime = data.get("lifetime_budget")
            if daily:
                return float(daily) / 100  # Meta returns cents
            if lifetime:
                return float(lifetime) / 100
        return None

    def _update_adset_budget(self, adset_id: str, new_budget_usd: float) -> bool:
        """Update daily budget. Meta API expects cents as integer."""
        budget_cents = int(new_budget_usd * 100)
        result = self._post(adset_id, data={"daily_budget": budget_cents})
        success = result and result.get("success")
        if success:
            logger.info(f"[SAGE] Budget updated: {adset_id} → ${new_budget_usd:.2f}/day")
        return bool(success)

    # ── AD COPY GENERATION ────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def generate_luxury_copy(
        self,
        vertical: str,
        asset_description: str,
        objective: str = "Lead Generation",
        client_name: str = "",
    ) -> AdCopyOutput:
        """
        Generate luxury-tier Meta ad copy via Gemini.
        COPY ONLY — no metrics, no budget data from Gemini.
        """
        from google import genai

        google_key = os.getenv("GOOGLE_API_KEY")
        if not google_key:
            return AdCopyOutput(
                primary_text =f"Precision lead generation for {vertical} businesses.",
                headline     ="Qualified Leads. Guaranteed.",
                description  =f"For {vertical} operators.",
                cta          ="Get Quote",
                vertical     =vertical,
            )

        client = genai.Client(api_key=google_key)
        prompt = f"""
Write Meta ad copy for a premium AI lead generation agency client.

Vertical: {vertical}
Campaign objective: {objective}
Visual asset: {asset_description}
Client: {client_name or f"Premium {vertical} business"}
Agency: OROVA

LUXURY FILTER (mandatory):
  — No exclamation marks
  — No "affordable," "cheap," "quick," "easy"
  — Tone: understated authority, executive-to-executive
  — Value: ROI, precision, efficiency, exclusivity

Return ONLY valid JSON:
{{
  "primary_text": "1-3 sentences, under 125 words, opens with a result",
  "headline": "under 40 chars, states the outcome",
  "description": "under 30 chars, one supporting detail",
  "cta": "Get Quote"
}}
"""
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        raw  = resp.text.strip().replace("```json","").replace("```","").strip()
        try:
            parsed = json.loads(raw)
            return AdCopyOutput(
                primary_text=parsed.get("primary_text", ""),
                headline    =parsed.get("headline", ""),
                description =parsed.get("description", ""),
                cta         =parsed.get("cta", "Get Quote"),
                vertical    =vertical,
            )
        except Exception:
            logger.error("[SAGE] Ad copy JSON parse failed")
            return AdCopyOutput(
                primary_text =f"We engineer qualified leads for {vertical} businesses.",
                headline     ="Qualified Leads. Guaranteed.",
                description  =f"For {vertical} operators.",
                cta          ="Get Quote",
                vertical     =vertical,
            )

    # ── WEEKLY REPORT ─────────────────────────────────────────────────────────

    def generate_weekly_report(self, client_name: str = "") -> Dict[str, Any]:
        """Full weekly performance report. All data from Meta API."""
        return {
            "client":       client_name,
            "report_date":  datetime.utcnow().strftime("%B %d, %Y"),
            "period_7d":    self.get_account_performance("last_7d"),
            "period_30d":   self.get_account_performance("last_30d"),
            "ad_sets":      [a.dict() for a in self.get_adset_performance("last_7d")],
            "data_source":  f"meta_graph_api_{META_API_VERSION}",
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _telegram_alert(self, message: str):
        """Send alert to owner via Telegram."""
        try:
            import httpx
            token   = os.getenv("TELEGRAM_BOT_TOKEN")
            chat_id = os.getenv("ADMIN_CHAT_ID")
            if token and chat_id:
                httpx.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                    timeout=5.0,
                )
        except Exception as e:
            logger.debug(f"[SAGE] Telegram alert failed: {e}")
