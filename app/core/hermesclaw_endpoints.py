"""
HermesClaw API Endpoints — Render-compatible HTTP API for all new autonomous features.
These endpoints allow the mission-control dashboard, Telegram bot, and HermesClaw
desktop UI to trigger the new self-improvement infrastructure.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

async def _require_api_key(request: Request):
    """Auth dependency for HermesClaw endpoints. Uses DASHBOARD_API_KEY env var.

    The Request type annotation is load-bearing: without it FastAPI treats
    `request` as a required query parameter and every endpoint 422s.
    Accepts the same credentials as main.require_dashboard_api_key,
    including session tokens issued by /api/keys/new.
    """
    import os
    import secrets
    expected = os.getenv("DASHBOARD_API_KEY") or os.getenv("NOVA_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="API key not configured")
    api_key = request.headers.get("X-Dashboard-Secret") or request.headers.get("X-API-Key") or ""
    if api_key and secrets.compare_digest(api_key.strip(), expected):
        return True
    from app.main import _is_valid_session_token
    if await _is_valid_session_token(request.headers.get("X-Session-Token", "")):
        return True
    raise HTTPException(status_code=403, detail="Unauthorized")


router = APIRouter(prefix="/api", tags=["hermesclaw"], dependencies=[Depends(_require_api_key)])


@router.post("/proofread")
async def api_proofread(request: dict):
    """Proofread an email draft. Accepts {to, subject, body, recipient_context}."""
    from app.skills.email_proofreader import proofread_email
    to = request.get("to", "")
    subject = request.get("subject", "")
    body = request.get("body", "")
    recipient_context = request.get("recipient_context", "")
    if not to or not subject or not body:
        raise HTTPException(status_code=400, detail="to, subject, and body are required")
    result = await proofread_email(to, subject, body, recipient_context)
    return {"status": "ok", **result}


@router.post("/morning_brief")
async def api_morning_brief(request: dict = None):
    """Generate and send the morning CEO briefing."""
    from app.core.ceo_brain import CEOBrain
    client_id = (request or {}).get("client_id", 0)
    brain = CEOBrain()
    brief = await brain.morning_brief(client_id=client_id)
    return {"status": "ok", "brief": brief}


@router.get("/health_check")
async def api_health_check(client_id: int = 0):
    """Run a pipeline health check and return score + alerts."""
    from app.core.ceo_brain import CEOBrain
    brain = CEOBrain()
    result = await brain.pipeline_health_check(client_id=client_id)
    return {"status": "ok", **result}


@router.post("/improvement_loop")
async def api_improvement_loop(request: dict = None):
    """Trigger the self-improvement loop manually."""
    from app.core.self_improvement import ImprovementLoop
    client_id = (request or {}).get("client_id", 0)
    loop = ImprovementLoop()
    await loop.run(client_id=client_id)
    return {"status": "ok", "message": "Improvement loop completed"}


@router.post("/approve_pruning")
async def api_approve_pruning():
    """Approve pending stale lead pruning."""
    from app.core.router import Router
    from app.core.planner import TaskPlanner
    from app.core.ai_client import UnifiedAIClient
    planner = TaskPlanner(UnifiedAIClient())
    from app.skills.lead_gen_v3 import find_leads
    router_obj = Router(planner, find_leads)
    result = await router_obj._approve_pruning_handler()
    return {"status": "ok", "message": result}


@router.get("/outreach_outcomes")
async def api_outreach_outcomes(limit: int = 100, client_id: int = 0):
    """Get outreach outcome records."""
    rows = await DatabaseManager.fetchall(
        """SELECT * FROM outreach_outcomes WHERE client_id = ? ORDER BY created_at DESC LIMIT ?""",
        (client_id, limit)
    )
    return {"status": "ok", "outcomes": [dict(r) for r in rows] if rows else []}


@router.get("/learned_strategies")
async def api_learned_strategies(client_id: int = 0):
    """Get learned strategies from the self-improvement loop."""
    rows = await DatabaseManager.fetchall(
        """SELECT * FROM learned_strategies WHERE client_id = ? AND active = 1 ORDER BY win_rate DESC""",
        (client_id,)
    )
    return {"status": "ok", "strategies": [dict(r) for r in rows] if rows else []}


@router.post("/worker/trigger/lane/{lane}")
async def api_trigger_lane(lane: int, client_id: int = 0):
    """Manually trigger a specific worker lane for testing."""
    from app.worker import (
        run_ceo_fast_lane, run_lead_hunt_slow_lane, run_reply_monitor,
        run_cold_lead_escalation, cloud_backup_job, ceo_brain_job,
        health_check_job, self_improvement_job, sequence_drip_job
    )
    lane_map = {
        1: lambda: run_ceo_fast_lane(client_id),
        2: lambda: run_lead_hunt_slow_lane(client_id),
        3: lambda: run_reply_monitor(client_id),
        4: lambda: run_cold_lead_escalation(client_id),
        5: cloud_backup_job,
        6: ceo_brain_job,
        7: health_check_job,
        8: self_improvement_job,
        9: sequence_drip_job,
    }
    fn = lane_map.get(lane)
    if not fn:
        raise HTTPException(status_code=400, detail=f"Unknown lane {lane}. Valid: 1-9")
    from app.worker import _run_async
    _run_async(fn())
    return {"status": "ok", "message": f"Lane {lane} triggered"}


@router.get("/revenue_metrics")
async def api_revenue_metrics(client_id: int = 0):
    """Get comprehensive revenue metrics: pipeline stats, conversion funnel, ROI."""
    try:
        # Get base metrics from DB
        metrics = await DatabaseManager.aget_metrics(client_id=client_id)
        
        # Calculate conversion rates
        leads = metrics.get("leads_found", 0)
        emails_sent = metrics.get("emails_sent", 0)
        replies = metrics.get("replies_received", 0)
        meetings = metrics.get("meetings_booked", 0)
        calls_made = metrics.get("calls_made", 0)
        cost = metrics.get("cost", 0.0)
        
        # Conversion rates
        contact_rate = (emails_sent / leads * 100) if leads > 0 else 0.0
        reply_rate = (replies / emails_sent * 100) if emails_sent > 0 else 0.0
        meeting_rate = (meetings / replies * 100) if replies > 0 else 0.0
        call_rate = (calls_made / leads * 100) if leads > 0 else 0.0
        
        # ROI Calculation (assume $500 per meeting value)
        meeting_value = 500.0
        total_value = meetings * meeting_value
        roi = ((total_value - cost) / cost * 100) if cost > 0 else 0.0
        
        # Get A/B subject performance from outreach_outcomes
        ab_rows = await DatabaseManager.fetchall(
            """SELECT strategy, COUNT(*) as count, 
                SUM(CASE WHEN result = 'replied' THEN 1 ELSE 0 END) as replies
               FROM outreach_outcomes 
               WHERE client_id = ? AND action = 'email_sent'
               GROUP BY strategy""",
            (client_id,)
        )
        ab_performance = [dict(r) for r in ab_rows] if ab_rows else []
        
        # Get niche performance
        niche_rows = await DatabaseManager.fetchall(
            """SELECT niche, COUNT(*) as count,
                SUM(CASE WHEN result = 'replied' THEN 1 ELSE 0 END) as replies,
                SUM(CASE WHEN result = 'sent' THEN 1 ELSE 0 END) as sent
               FROM outreach_outcomes 
               WHERE client_id = ?
               GROUP BY niche""",
            (client_id,)
        )
        niche_performance = [dict(r) for r in niche_rows] if niche_rows else []
        
        # Get daily trend (last 7 days)
        daily_rows = await DatabaseManager.fetchall(
            """SELECT DATE(created_at) as day, 
                COUNT(*) as total,
                SUM(CASE WHEN result = 'sent' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN result = 'replied' THEN 1 ELSE 0 END) as replied
               FROM outreach_outcomes 
               WHERE client_id = ? AND created_at > datetime('now', '-7 days')
               GROUP BY DATE(created_at)
               ORDER BY day""",
            (client_id,)
        )
        daily_trend = [dict(r) for r in daily_rows] if daily_rows else []
        
        return {
            "status": "ok",
            "totals": {
                "leads": leads,
                "emails_sent": emails_sent,
                "replies": replies,
                "meetings_booked": meetings,
                "calls_made": calls_made,
                "cost": cost,
            },
            "conversion_rates": {
                "contact_rate": round(contact_rate, 1),
                "reply_rate": round(reply_rate, 1),
                "meeting_rate": round(meeting_rate, 1),
                "call_rate": round(call_rate, 1),
            },
            "roi": {
                "total_value": round(total_value, 2),
                "roi_percent": round(roi, 1),
                "cost": cost,
                "meeting_value": meeting_value,
            },
            "ab_performance": ab_performance,
            "niche_performance": niche_performance,
            "daily_trend": daily_trend,
        }
    except Exception as e:
        logger.error(f"[RevenueMetrics] Error: {e}")
        logger.error(f"[HERMESCLAW] Revenue metrics error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/linkedin_enrich")
async def api_linkedin_enrich(business_name: str, owner_name: str = "", domain: str = ""):
    """Free LinkedIn enrichment for a lead."""
    from app.skills.lead_enrichment import enrich_with_linkedin
    result = await enrich_with_linkedin(business_name=business_name, owner_name=owner_name, domain=domain)
    return {"status": "ok", **result}


@router.get("/booking_link")
async def api_booking_link(lead_name: str = "", business_name: str = ""):
    """Generate a meeting booking link for outbound emails."""
    from app.skills.cal_booking import get_booking_link
    link = get_booking_link(lead_name=lead_name, business_name=business_name)
    return {"status": "ok", "booking_link": link}


def register_hermesclaw_routes(app):
    """Register all HermesClaw endpoints onto a FastAPI app instance."""
    app.include_router(router)
    logger.info("[HERMESCLAW] Registered all autonomous endpoints on /api/*")
