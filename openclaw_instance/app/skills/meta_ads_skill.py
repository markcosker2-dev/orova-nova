import os
import requests
import logging

logger = logging.getLogger(__name__)

def get_meta_insights(ad_account_id, access_token, days=7):
    """Fetch spend and lead conversion insights from Meta Graph API."""
    if not access_token:
        return {"error": "No access token provided"}
    
    # Strip 'act_' if present in account ID
    account_id = ad_account_id.replace("act_", "")
    
    url = f"https://graph.facebook.com/v20.0/act_{account_id}/insights"
    params = {
        "fields": "spend,conversions,impressions,clicks,cpc,ctr",
        "date_preset": f"last_{days}d" if days in [1, 7, 30] else "maximum",
        "access_token": access_token
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        insights = data.get("data", [])
        if not insights:
            return {"spend": 0, "leads": 0, "cpl": 0}
        
        main_stats = insights[0]
        spend = float(main_stats.get("spend", 0))
        
        # conversions is a list of dicts in Meta API
        conversions = main_stats.get("conversions", [])
        leads = 0
        for conv in conversions:
            if conv.get("action_type") in ["lead", "offsite_conversion.fb_pixel_lead"]:
                leads += int(conv.get("value", 0))
        
        cpl = spend / leads if leads > 0 else spend
        
        return {
            "spend": spend,
            "leads": leads,
            "cpl": round(cpl, 2),
            "impressions": main_stats.get("impressions"),
            "clicks": main_stats.get("clicks")
        }
    except Exception as e:
        logger.error(f"Meta Stats Error: {e}")
        return {"error": str(e)}

def pause_meta_campaign(campaign_id, access_token):
    """Autonomously pause a failing Meta Ad Campaign."""
    if not access_token:
        return {"success": False, "error": "No access token"}
        
    url = f"https://graph.facebook.com/v20.0/{campaign_id}"
    params = {
        "status": "PAUSED",
        "access_token": access_token
    }
    
    try:
        response = requests.post(url, data=params, timeout=15)
        response.raise_for_status()
        return {"success": True, "message": f"Campaign {campaign_id} PAUSED successfully."}
    except Exception as e:
        logger.error(f"Meta Pause Error: {e}")
        return {"success": False, "error": str(e)}

def monitor_client_ads(client_id, ad_account_id, access_token, cpl_threshold=50.0):
    """ORACLE SKILL: Monitor ads and pause if budget drain is detected."""
    stats = get_meta_insights(ad_account_id, access_token)
    
    if "error" in stats:
        return stats
    
    current_cpl = stats.get("cpl", 0)
    total_spend = stats.get("spend", 0)
    
    # Logic: If we've spent over $100 and CPL is double the threshold, kill it.
    if total_spend > 100 and current_cpl > (cpl_threshold * 2):
        logger.warning(f"⚠️ [ORACLE] Client {client_id} Ad Account act_{ad_account_id} is draining budget. CPL is ${current_cpl}!")
        # Pause logic would go here if we had specific campaign IDs
        # For now, we return the warning for the CEO to approve a mass pause
        return {
            "status": "DANGER",
            "message": f"CPL (${current_cpl}) exceeds safety threshold (${cpl_threshold}). Budget drain detected.",
            "stats": stats
        }
    
    return {
        "status": "HEALTHY",
        "stats": stats
    }
