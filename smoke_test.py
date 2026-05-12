#!/usr/bin/env python3
"""
OROVA Nova — Pre-Deployment Smoke Test
Verifies all imports resolve before starting the service.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0

def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  [PASS] {name}")
        PASS += 1
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        FAIL += 1

print("=" * 60)
print("  OROVA Nova — Smoke Test")
print("=" * 60)

# 1. Core imports
print("\n[1/8] Core Modules")
def t():
    from app.core.config import cfg
    from app.core.database import DatabaseManager
    from app.core.ai_client import UnifiedAIClient
    from app.core.planner import TaskPlanner
    from app.core.router import Router
    from app.core.guardrails import Guardrails
    from app.core.phone_utils import to_e164
    from app.core.signal_protocol import send_revenue_alert, send_mission_pulse, set_chat_id
    from app.core.luxury_filter import LuxuryFilter, critique_and_rewrite
check("Core imports", t)

# 2. Production modules (new)
print("\n[2/8] Production Modules")
def t():
    from app.core.memory import memory
    from app.core.audit_trail import audit
    from app.core.budget import budget
    from app.core.agent_bus import agent_bus
    from app.core.kill_switch import kill_switch
    from app.core.ai_provider import ai
    from app.core.smart_calling import calling_hours
    from app.skills.revenue_tracker import revenue
    from app.skills.night_shift import night_shift
check("Production modules", t)

# 3. Skill imports
print("\n[3/8] Skill Modules")
def t():
    from app.skills.lead_finder import find_leads, read_webpage
    from app.skills.browser_ops import browse_and_extract, google_search_scrape, research_lead
    from app.skills.outbound_dialer import trigger_retell_call
    from app.skills.media_buyer import SageMediaBuyer
    from app.skills.definitions import TOOLS
    from app.skills.competitive_intel import analyze_competitor, compare_competitors
    from app.skills.content_writer import write_content, optimize_post
    from app.skills.seo_audit import run_seo_audit
    from app.skills.deep_research import deep_research
    from app.skills.approval_workflow import request_approval, list_pending
    from app.skills.agentmail_skill import send_outreach, check_replies
    from app.skills.gmail_skill import get_inbox, search_emails, send_email
    from app.skills.calendar_skill import get_today, get_week, create_event
    from app.skills.orova_sales_core import get_orova_prompt
    from app.skills.sheets_skill import append_to_sheet, create_new_sheet
    from app.skills.image_gen import generate_ai_image
    from app.skills.follow_up_sequences import generate_sequence
    from app.skills.proposal_gen import generate_proposal
    from app.skills.perf_dashboard import generate_weekly_report, track_metric
    from app.skills.scrapling_scraper import stealth_search, stealth_extract, bulk_scrape
    from app.skills.email_sequence_skill import create_drip_campaign
    from app.skills.copywriting_skill import write_cold_email, write_ad_copy
    from app.skills.analytics_skill import pipeline_report, conversion_analysis, roi_calculator
    from app.skills.meta_ads_skill import monitor_client_ads, pause_meta_campaign
    from app.skills.cipher_agent import CipherAgent
    from app.skills.appointment_setter import detect_close_signal
check("Skill imports", t)

# 3. Dashboard
print("\n[4/8] Dashboard")
def t():
    from app.dashboard.mission_control import app as dashboard_app
check("Dashboard import", t)

# 4. Phone normalization
print("\n[5/8] Phone Utils")
def t():
    from app.core.phone_utils import to_e164
    assert to_e164("+1 (213) 555-1234") == "+12135551234"
    assert to_e164("2135551234") == "+12135551234"
    assert to_e164("INVALID") is None
check("E.164 normalization", t)

# 5. Database
print("\n[6/8] Database")
def t():
    from app.core.database import DatabaseManager, DB_PATH
    DatabaseManager.init_db()
    assert os.path.exists(DB_PATH)
check("Database init", t)

# 7. Tool registry consistency
print("\n[7/8] Tool Registry")
def t():
    from app.skills.definitions import TOOLS
    from app.core.planner import TaskPlanner
    from app.core.ai_client import UnifiedAIClient

    ai = UnifiedAIClient()
    planner = TaskPlanner(ai)

    tool_names = {t["function"]["name"] for t in TOOLS}
    registered = set(planner.available_functions.keys())

    missing = tool_names - registered
    extra = registered - tool_names
    if missing:
        print(f"    WARNING: {len(missing)} tools defined but not registered: {missing}")
    if extra:
        print(f"    INFO: {len(extra)} tools registered but not in definitions: {extra}")
check("Tool registry", t)

# 8. Production systems (memory, budget, kill switch, retell)
print("\n[8/8] Production Systems")
def t():
    from app.core.memory import memory
    from app.core.audit_trail import audit
    from app.core.budget import budget
    from app.core.agent_bus import agent_bus
    from app.core.kill_switch import kill_switch
    from app.core.ai_provider import ai
    from app.core.smart_calling import calling_hours
    from app.skills.revenue_tracker import revenue
    from app.skills.night_shift import night_shift
    from app.skills.retell_script_gen import retell

    # Test memory store/retrieve
    memory.store_knowledge("test", "smoke", {"status": "ok"})
    result = memory.get_knowledge("test", "smoke")
    assert result["status"] == "ok", "Memory store/retrieve failed"

    # Test audit log
    audit.log("smoke_test", "test_action", input_data="test")

    # Test budget check
    status = budget.check_budget("HAWK")
    assert "can_proceed" in status

    # Test kill switch
    assert kill_switch.check_before_action("test", "action") == True

    # Test AI provider status
    provider_status = ai.get_status()
    assert isinstance(provider_status, dict)

    # Test retell script generation (fallback mode)
    script = retell.generate_script({"business": "TestCo", "vertical": "HVAC"})
    assert len(script) > 50, "Script too short"

    # Test smart calling (timezone detection)
    tz = calling_hours.get_prospect_timezone("+13055551234")
    assert "America/" in tz, f"Timezone detection failed: {tz}"

    # Test revenue tracker
    revenue.add_deal(999, "TestCo", "HVAC")
    summary = revenue.get_pipeline_summary()
    assert "total_pipeline_value" in summary

    # Test night shift
    ns = night_shift.get_shift_summary()
    assert "is_night_shift" in ns
check("Production systems", t)

print("\n" + "=" * 60)
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 60)

if FAIL > 0:
    print("\n  DEPLOY BLOCKED: Fix failures first.")
    sys.exit(1)
else:
    print("\n  ALL CLEAR. Safe to deploy.")
    sys.exit(0)
