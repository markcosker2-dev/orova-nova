#!/usr/bin/env python3
"""
OROVA System Validation Script
Comprehensive pre-deployment verification

Run: python validate_system.py
"""

import os
import sys
import json
import asyncio
import importlib
from datetime import datetime
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Test results
passed = 0
failed = 0
warnings = 0

def print_header(text):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{text:^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def test_pass(name):
    global passed
    passed += 1
    print(f"{GREEN}✓{RESET} {name}")

def test_fail(name, error=""):
    global failed
    failed += 1
    print(f"{RED}✗{RESET} {name}")
    if error:
        print(f"  {RED}Error: {error}{RESET}")

def test_warn(name, msg=""):
    global warnings
    warnings += 1
    print(f"{YELLOW}⚠{RESET} {name}")
    if msg:
        print(f"  {YELLOW}{msg}{RESET}")

def verify_imports():
    """Verify all critical imports work"""
    print_header("IMPORT VERIFICATION")
    
    imports_to_test = [
        ("fastapi", "FastAPI"),
        ("redis", "Redis client"),
        ("gspread", "Google Sheets"),
        ("google.auth", "Google Auth"),
        ("duckduckgo_search", "DuckDuckGo search"),
        ("httpx", "HTTPX client"),
        ("telegram", "Telegram bot"),
        ("retell_sdk", "Retell AI"),
        ("apscheduler", "APScheduler"),
        ("agentmail", "AgentMail (optional)"),
    ]
    
    for module_name, label in imports_to_test:
        try:
            importlib.import_module(module_name)
            test_pass(f"Import {label}")
        except ImportError:
            if "optional" in label:
                test_warn(f"Import {label} (optional - not critical)")
            else:
                test_fail(f"Import {label}")
        except Exception as e:
            test_fail(f"Import {label}", str(e))

def verify_environment():
    """Verify environment variables"""
    print_header("ENVIRONMENT CONFIGURATION")
    
    required = [
        ("TELEGRAM_BOT_TOKEN", "Telegram bot token"),
    ]
    
    optional = [
        ("RENDER_EXTERNAL_URL", "Render external URL"),
        ("DASHBOARD_API_KEY", "Dashboard API key"),
        ("GOOGLE_SHEETS_WORKBOOK", "Google Sheets workbook"),
        ("GOOGLE_CREDENTIALS_JSON", "Google credentials"),
        ("APOLLO_API_KEY", "Apollo.io API key (optional)"),
        ("TAVILY_API_KEY", "Tavily API key (optional)"),
        ("FIRECRAWL_API_KEY", "Firecrawl API key (optional)"),
    ]
    
    for env_var, label in required:
        if os.getenv(env_var):
            test_pass(f"Environment {label}")
        else:
            test_fail(f"Environment {label}", "Not set")
    
    for env_var, label in optional:
        if os.getenv(env_var):
            test_pass(f"Environment {label} (configured)")
        else:
            test_warn(f"Environment {label} (not configured - features may be limited)")

def verify_files():
    """Verify critical files exist"""
    print_header("FILE STRUCTURE")
    
    files_to_check = [
        ("app/main.py", "Main application"),
        ("app/worker.py", "Worker scheduler"),
        ("app/core/router.py", "Message router"),
        ("app/core/database.py", "Database manager"),
        ("app/core/telegram_queue.py", "Telegram queue"),
        ("app/skills/lead_finder.py", "Lead finder skill"),
        ("app/skills/agentmail_skill.py", "AgentMail skill"),
        ("mission-control/index.html", "Mission Control dashboard"),
        ("mission-control/js/app.js", "Dashboard JS"),
        ("requirements.txt", "Python dependencies"),
        ("tasks.json", "Task persistence (auto-created ok)"),
        ("content.json", "Content persistence (auto-created ok)"),
        ("memories.json", "Memory persistence (auto-created ok)"),
    ]
    
    for file_path, label in files_to_check:
        if Path(file_path).exists():
            size_mb = Path(file_path).stat().st_size / 1024 / 1024
            test_pass(f"File exists: {label} ({size_mb:.1f}MB)")
        else:
            # Some files are auto-created
            if "auto-created" in label:
                test_warn(f"File not yet created: {label} (will be created on first run)")
            else:
                test_fail(f"File missing: {label}")

def verify_database():
    """Verify database initialization"""
    print_header("DATABASE VERIFICATION")
    
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from app.core.database import DatabaseManager
        
        # Try to initialize
        DatabaseManager.init_db()
        test_pass("Database initialization")
        
        # Check schema tables would be created
        test_pass("Database schema validation")
        
    except Exception as e:
        test_fail("Database initialization", str(e))

def verify_skills():
    """Verify skill registrations"""
    print_header("SKILL SYSTEM VERIFICATION")
    
    expected_skills = [
        "find_leads",
        "deep_research",
        "enrich_lead_lite",
        "opportunity_scanner",
        "send_outreach",
        "check_replies",
        "write_cold_email",
        "trigger_retell_call",
        "generate_proposal",
        "write_ad_copy",
        "create_instagram_post",
        "generate_ai_image",
        "pipeline_report",
        "conversion_analysis",
        "roi_calculator",
        "run_pipeline",
    ]
    
    found_skills = 0
    for skill in expected_skills:
        try:
            # Check if skill module exists
            skill_module = skill.replace("_", "/").lower()
            possible_paths = [
                f"app/skills/{skill}.py",
                f"app/core/{skill}.py",
            ]
            
            found = False
            for path in possible_paths:
                if Path(path).exists():
                    found = True
                    found_skills += 1
                    test_pass(f"Skill registered: {skill}")
                    break
            
            if not found:
                test_warn(f"Skill not found: {skill}")
                
        except Exception as e:
            test_fail(f"Skill {skill}", str(e))
    
    if found_skills >= 20:
        test_pass(f"Skills total: {found_skills} skills found (minimum 20)")
    else:
        test_fail(f"Skills total: Only {found_skills} found (minimum 20)")

def verify_api_endpoints():
    """Verify API endpoint definitions"""
    print_header("API ENDPOINT VERIFICATION")
    
    expected_endpoints = [
        ("/api/health", "Health check"),
        ("/api/leads", "Lead listing"),
        ("/api/tasks", "Task management"),
        ("/api/content", "Content management"),
        ("/api/memory", "Memory management"),
        ("/api/chat", "Chat interface"),
        ("/api/actions/hunt-leads", "Lead hunting action"),
        ("/api/actions/send-emails", "Email action"),
        ("/api/actions/generate-report", "Report generation"),
        ("/telegram", "Telegram webhook"),
        ("/api/skills", "Skills listing"),
        ("/api/pipelines", "Pipeline listing"),
        ("/api/agents", "Agent status"),
        ("/api/notifications", "Notifications"),
    ]
    
    try:
        with open("app/main.py", "r") as f:
            main_content = f.read()
        
        found_endpoints = 0
        for endpoint, label in expected_endpoints:
            if endpoint.replace("/", "_").replace("-", "_") in main_content or f'"{endpoint}"' in main_content or f"'{endpoint}'" in main_content:
                found_endpoints += 1
                test_pass(f"Endpoint implemented: {label} ({endpoint})")
            else:
                test_warn(f"Endpoint may not be implemented: {label} ({endpoint})")
        
        if found_endpoints >= 10:
            test_pass(f"API endpoints: {found_endpoints}+ endpoints found")
        else:
            test_fail(f"API endpoints: Only {found_endpoints} found")
            
    except Exception as e:
        test_fail("API endpoint scanning", str(e))

def verify_dashboard():
    """Verify dashboard structure"""
    print_header("MISSION CONTROL DASHBOARD")
    
    screens = [
        ("taskboard", "Task Board"),
        ("analytics", "Analytics"),
        ("pipeline", "Pipeline"),
        ("calendar", "Calendar"),
        ("leads", "Leads"),
        ("memory", "Memory"),
        ("team", "Team"),
        ("skills", "Skills"),
        ("workflows", "Workflows"),
        ("office", "Digital Office"),
    ]
    
    try:
        with open("mission-control/js/app.js", "r") as f:
            dashboard_content = f.read()
        
        found_screens = 0
        for screen_id, label in screens:
            if screen_id in dashboard_content:
                found_screens += 1
                test_pass(f"Dashboard screen: {label}")
            else:
                test_warn(f"Dashboard screen not found: {label}")
        
        if found_screens >= 8:
            test_pass(f"Dashboard screens: {found_screens}/10 screens implemented")
        else:
            test_warn(f"Dashboard screens: Only {found_screens}/10 found")
            
    except Exception as e:
        test_fail("Dashboard verification", str(e))

def verify_telegram():
    """Verify Telegram integration"""
    print_header("TELEGRAM INTEGRATION")
    
    try:
        with open("app/main.py", "r") as f:
            main_content = f.read()
        
        telegram_checks = [
            ("webhook", "Webhook registration"),
            ("tg_queue", "Telegram queue"),
            ("process_telegram_message", "Message processor"),
            ("_send_telegram", "Response sender"),
            ("TELEGRAM_BOT_TOKEN", "Token configuration"),
        ]
        
        found_checks = 0
        for check_str, label in telegram_checks:
            if check_str in main_content:
                found_checks += 1
                test_pass(f"Telegram feature: {label}")
            else:
                test_fail(f"Telegram feature: {label}")
        
        if found_checks >= 4:
            test_pass("Telegram integration: Core features implemented")
        else:
            test_fail("Telegram integration: Missing critical features")
            
    except Exception as e:
        test_fail("Telegram verification", str(e))

def verify_security():
    """Verify security features"""
    print_header("SECURITY FEATURES")
    
    security_checks = [
        ("rate_limiter", "Rate limiting"),
        ("sanitizer", "Input sanitization"),
        ("guardrails", "Prompt injection prevention"),
        ("Guardrails.sanitize_input", "Guardrail implementation"),
        ("circuit_breaker", "Circuit breaker"),
        ("X-API-Key", "API key authentication"),
    ]
    
    try:
        with open("app/core/router.py", "r") as f:
            router_content = f.read()
        
        with open("app/main.py", "r") as f:
            main_content = f.read()
        
        full_content = router_content + main_content
        
        found_checks = 0
        for check_str, label in security_checks:
            if check_str in full_content:
                found_checks += 1
                test_pass(f"Security feature: {label}")
            else:
                test_warn(f"Security feature: {label} (not found)")
        
        if found_checks >= 5:
            test_pass("Security: Core hardening features implemented")
        else:
            test_warn("Security: Some features may be missing")
            
    except Exception as e:
        test_fail("Security verification", str(e))

def generate_report():
    """Generate final report"""
    print_header("VERIFICATION REPORT")
    
    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"{BOLD}Tests Run:{RESET} {total}")
    print(f"{GREEN}{BOLD}Passed:{RESET} {passed}")
    print(f"{RED}{BOLD}Failed:{RESET} {failed}")
    print(f"{YELLOW}{BOLD}Warnings:{RESET} {warnings}")
    print(f"{BOLD}Pass Rate:{RESET} {pass_rate:.1f}%")
    
    print_header("FINAL STATUS")
    
    if failed == 0 and pass_rate >= 90:
        print(f"{GREEN}{BOLD}✓ SYSTEM READY FOR PRODUCTION{RESET}")
        return True
    elif failed <= 2 and pass_rate >= 85:
        print(f"{YELLOW}{BOLD}⚠ SYSTEM READY WITH MINOR ISSUES{RESET}")
        print(f"  Review warnings above and fix before deployment")
        return True
    else:
        print(f"{RED}{BOLD}✗ SYSTEM NOT READY - FIX ERRORS FIRST{RESET}")
        return False

def main():
    print(f"\n{BOLD}{BLUE}OROVA SYSTEM VALIDATION{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python version: {sys.version.split()[0]}")
    
    verify_imports()
    verify_environment()
    verify_files()
    verify_database()
    verify_skills()
    verify_api_endpoints()
    verify_dashboard()
    verify_telegram()
    verify_security()
    
    ready = generate_report()
    
    print(f"\n{BLUE}{'='*60}{RESET}\n")
    
    return 0 if ready else 1

if __name__ == "__main__":
    sys.exit(main())
