from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import requests
import json
import os
from datetime import datetime, timedelta

class AdInsight(BaseModel):
    ad_id: str
    ad_name: str
    spend: float
    impressions: int
    clicks: int
    conversions: float
    cost_per_result: float
    roas: Optional[float] = None

    @validator('spend', 'cost_per_result', pre=True)
    def parse_float(cls, v):
        return float(v) if v else 0.0

    @validator('impressions', 'clicks', pre=True)
    def parse_int(cls, v):
        return int(v) if v else 0

class CampaignData(BaseModel):
    campaign_id: str
    campaign_name: str
    ads: List[AdInsight]

class AdAccountData(BaseModel):
    account_id: str
    campaigns: List[CampaignData]

class MediaBuyerConfig(BaseModel):
    access_token: str
    ad_account_ids: List[str]
    max_cpl: float = 15.0
    kill_switch_roas: float = 1.0
    scale_roas_threshold: float = 2.0
    scale_percentage: float = 20.0
    min_spend_for_action: float = 50.0
    api_version: str = "v20.0"

class MediaBuyerAgent:
    def __init__(self, config: MediaBuyerConfig):
        self.config = config
        self.base_url = f"https://graph.facebook.com/{self.config.api_version}"

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        params['access_token'] = self.config.access_token
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_ad_insights(self, ad_account_id: str, days_back: int = 7) -> AdAccountData:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        params = {
            "level": "ad",
            "fields": "ad_id,ad_name,spend,impressions,clicks,actions,cost_per_action_type",
            "time_range": json.dumps({
                "since": start_date.strftime("%Y-%m-%d"),
                "until": end_date.strftime("%Y-%m-%d")
            }),
            "filtering": json.dumps([{
                "field": "ad.effective_status",
                "operator": "IN",
                "value": ["ACTIVE"]
            }])
        }
        
        data = self._make_request(f"/{ad_account_id}/insights", params)
        
        ads = []
        for item in data.get("data", []):
            actions = item.get("actions", [])
            conversions = sum(float(action.get("value", 0)) for action in actions if action.get("action_type") == "purchase")
            
            # Calculate ROAS (assuming revenue from conversions, need to adjust based on actual value)
            spend = float(item.get("spend", 0))
            roas = conversions / spend if spend > 0 else 0
            
            ad = AdInsight(
                ad_id=item["ad_id"],
                ad_name=item.get("ad_name", ""),
                spend=spend,
                impressions=int(item.get("impressions", 0)),
                clicks=int(item.get("clicks", 0)),
                conversions=conversions,
                cost_per_result=float(item.get("cost_per_action_type", [{}])[0].get("value", 0)),
                roas=roas
            )
            ads.append(ad)
        
        # For simplicity, assuming all ads in one campaign or create dummy campaign
        campaign = CampaignData(
            campaign_id="default",
            campaign_name="Default Campaign",
            ads=ads
        )
        
        return AdAccountData(
            account_id=ad_account_id,
            campaigns=[campaign]
        )

    def evaluate(self) -> Dict[str, Any]:
        evaluation_results = {}
        
        for account_id in self.config.ad_account_ids:
            try:
                account_data = self.fetch_ad_insights(account_id)
                evaluation_results[account_id] = {
                    "total_spend": sum(ad.spend for campaign in account_data.campaigns for ad in campaign.ads),
                    "total_conversions": sum(ad.conversions for campaign in account_data.campaigns for ad in campaign.ads),
                    "avg_roas": sum(ad.roas or 0 for campaign in account_data.campaigns for ad in campaign.ads) / len([ad for campaign in account_data.campaigns for ad in campaign.ads]) if any(account_data.campaigns) else 0,
                    "ads_to_kill": [ad.ad_id for campaign in account_data.campaigns for ad in campaign.ads if (ad.roas or 0) < self.config.kill_switch_roas and ad.spend > self.config.min_spend_for_action],
                    "ads_to_scale": [ad.ad_id for campaign in account_data.campaigns for ad in campaign.ads if (ad.roas or 0) > self.config.scale_roas_threshold and ad.spend > self.config.min_spend_for_action],
                    "ads_over_cpl": [ad.ad_id for campaign in account_data.campaigns for ad in campaign.ads if ad.cost_per_result > self.config.max_cpl]
                }
            except Exception as e:
                evaluation_results[account_id] = {"error": str(e)}
        
        return evaluation_results

    def act(self, evaluation_results: Dict[str, Any]) -> Dict[str, Any]:
        actions_taken = {}
        
        for account_id, results in evaluation_results.items():
            if "error" in results:
                continue
            
            actions_taken[account_id] = {
                "paused": [],
                "scaled": []
            }
            
            # Kill ads with low ROAS
            for ad_id in results.get("ads_to_kill", []):
                try:
                    self._pause_ad(ad_id)
                    actions_taken[account_id]["paused"].append(ad_id)
                except Exception as e:
                    print(f"Error pausing ad {ad_id}: {e}")
            
            # Scale ads with high ROAS
            for ad_id in results.get("ads_to_scale", []):
                try:
                    self._scale_ad_budget(ad_id, self.config.scale_percentage)
                    actions_taken[account_id]["scaled"].append(ad_id)
                except Exception as e:
                    print(f"Error scaling ad {ad_id}: {e}")
        
        return actions_taken

    def _pause_ad(self, ad_id: str):
        params = {"status": "PAUSED"}
        self._make_request(f"/{ad_id}", params)

    def _scale_ad_budget(self, ad_id: str, percentage: float):
        # First, get current budget
        current_data = self._make_request(f"/{ad_id}", {"fields": "daily_budget"})
        current_budget = int(current_data.get("daily_budget", 0))
        new_budget = int(current_budget * (1 + percentage / 100))
        
        params = {"daily_budget": new_budget}
        self._make_request(f"/{ad_id}", params)

# Module-level wrappers for planner tool registry
def create_media_buyer_agent(access_token: str, ad_account_ids: List[str], **kwargs) -> MediaBuyerAgent:
    config = MediaBuyerConfig(access_token=access_token, ad_account_ids=ad_account_ids, **kwargs)
    return MediaBuyerAgent(config)

def run_evaluation_cycle(agent: MediaBuyerAgent) -> Dict[str, Any]:
    evaluation = agent.evaluate()
    actions = agent.act(evaluation)
    return {"evaluation": evaluation, "actions": actions}

# Example usage
if __name__ == "__main__":
    # This would be configured with actual tokens and IDs
    config = MediaBuyerConfig(
        access_token=os.getenv("META_ACCESS_TOKEN", "your_token_here"),
        ad_account_ids=["act_123456789"]
    )
    agent = MediaBuyerAgent(config)
    results = run_evaluation_cycle(agent)
    print(json.dumps(results, indent=2))