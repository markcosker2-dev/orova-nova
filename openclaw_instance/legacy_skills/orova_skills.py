# -*- coding: utf-8 -*-
"""
OROVA Skills for MikeBot
- Web Search (DuckDuckGo)
- Email (The Scribe)
- Cold Caller (Retell)
- Lead Management
- Scheduler
"""

import os
import sys
import json
import csv
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

OROVA_ROOT = Path(__file__).parent.parent.parent

# ═══════════════════════════════════════════════════════════════════════════════
# WEB SEARCH (DuckDuckGo - FREE, No API Key)
# ═══════════════════════════════════════════════════════════════════════════════

def web_search_ddg(query: str, max_results: int = 5):
    """Search the web using DuckDuckGo (free, no API key needed)"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        try:
            # Try alternate import (older versions)
            from ddgs import DDGS
        except ImportError:
            return {
                "success": False, 
                "error": "DuckDuckGo search not installed. Run: pip install duckduckgo-search"
            }
    
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", r.get("link", "")),
                "snippet": r.get("body", r.get("snippet", ""))[:200]
            })
        
        return {
            "success": True,
            "query": query,
            "results": formatted,
            "count": len(formatted)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL AGENT (The Scribe)
# ═══════════════════════════════════════════════════════════════════════════════

def send_email(to_email: str, subject: str, body: str):
    """Send an email using the configured Gmail account"""
    try:
        import yagmail
    except ImportError:
        return {"success": False, "error": "yagmail not installed. Run: pip install yagmail"}
    
    # Load email config from email_agent.py or environment
    email_user = os.environ.get("EMAIL_USER")
    email_pass = os.environ.get("EMAIL_PASS")
    
    if not email_user or not email_pass:
        return {"success": False, "error": "Email credentials not configured. Set EMAIL_USER and EMAIL_PASS in .env"}
    
    try:
        yag = yagmail.SMTP(email_user, email_pass)
        yag.send(to=to_email, subject=subject, contents=body)
        
        return {
            "success": True,
            "message": f"Email sent to {to_email}",
            "subject": subject
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def generate_cold_email(business_name: str, owner_name: str = "there", icebreaker: str = ""):
    """Generate a cold email using AI (requires API)"""
    # This uses the pattern from email_agent.py
    subject = f"quick question about {business_name}".lower()
    
    owner_first = owner_name.split()[0] if owner_name and owner_name != "N/A" else "there"
    
    body = f"""Hi {owner_first},

{icebreaker if icebreaker else f"I came across {business_name} and was impressed by your work."}

We help shops like yours fill the calendar with high-ticket ceramic and PPF jobs automatically - no chasing leads, no wasted ad spend.

Worth a quick chat to see if it's a fit?

Best,
Mark"""
    
    return {
        "success": True,
        "subject": subject,
        "body": body,
        "to_name": owner_first,
        "business": business_name
    }

def email_lead(lead_name: str, custom_message: str = None):
    """Generate and optionally send email to a lead from qualified_leads.csv"""
    csv_path = OROVA_ROOT / "qualified_leads.csv"
    
    if not csv_path.exists():
        return {"success": False, "error": "qualified_leads.csv not found"}
    
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        # Find the lead
        mask = df['Business Name'].str.lower().str.contains(lead_name.lower(), na=False)
        matches = df[mask]
        
        if matches.empty:
            return {"success": False, "error": f"Lead not found: {lead_name}"}
        
        lead = matches.iloc[0]
        email = lead.get('Contact Email', 'N/A')
        
        if email == 'N/A' or pd.isna(email):
            return {
                "success": False, 
                "error": f"No email found for {lead['Business Name']}",
                "lead": lead.to_dict()
            }
        
        # Generate email content
        email_content = generate_cold_email(
            business_name=lead.get('Business Name', 'your business'),
            owner_name=lead.get('Decision Maker', 'there'),
            icebreaker=lead.get('Icebreaker', '')
        )
        
        return {
            "success": True,
            "lead": lead['Business Name'],
            "to_email": email,
            "draft": email_content,
            "note": "Use send_email tool to actually send, or approve in CLI"
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# COLD CALLER (Retell AI)
# ═══════════════════════════════════════════════════════════════════════════════

def list_leads_for_calling(min_score: int = 7):
    """List leads available for cold calling"""
    csv_path = OROVA_ROOT / "qualified_leads.csv"
    
    if not csv_path.exists():
        return {"success": False, "error": "qualified_leads.csv not found"}
    
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        # Filter by score and phone availability
        if 'AI_Score' in df.columns:
            hot_leads = df[df['AI_Score'] >= min_score]
        else:
            hot_leads = df
        
        # Filter to those with phone numbers
        hot_leads = hot_leads[hot_leads['Phone'].notna() & (hot_leads['Phone'] != 'N/A')]
        
        leads_list = []
        for _, row in hot_leads.iterrows():
            leads_list.append({
                "name": row.get('Business Name', 'Unknown'),
                "phone": row.get('Phone', 'N/A'),
                "score": row.get('AI_Score', 'N/A'),
                "tier": row.get('Market_Tier', 'Unknown')
            })
        
        return {
            "success": True,
            "count": len(leads_list),
            "min_score": min_score,
            "leads": leads_list[:20]  # Limit to 20
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def call_lead(business_name: str):
    """Initiate a Retell AI cold call to a lead"""
    import requests
    
    RETELL_API_KEY = os.environ.get("RETELL_API_KEY")
    if not RETELL_API_KEY:
        return {"success": False, "error": "Retell API key not configured. Set RETELL_API_KEY in .env"}
    RETELL_AGENT_ID = "agent_54910fe615575e38f35cfbd028"
    
    csv_path = OROVA_ROOT / "qualified_leads.csv"
    
    if not csv_path.exists():
        return {"success": False, "error": "qualified_leads.csv not found"}
    
    try:
        import pandas as pd
        df = pd.read_csv(csv_path)
        
        # Find lead
        mask = df['Business Name'].str.lower().str.contains(business_name.lower(), na=False)
        matches = df[mask]
        
        if matches.empty:
            return {"success": False, "error": f"Lead not found: {business_name}"}
        
        lead = matches.iloc[0]
        phone = lead.get('Phone', 'N/A')
        
        if phone == 'N/A' or pd.isna(phone):
            return {"success": False, "error": f"No phone number for {lead['Business Name']}"}
        
        # Clean phone for E.164
        import re
        phone_clean = re.sub(r'\D', '', str(phone))
        if len(phone_clean) == 10:
            phone_clean = "+1" + phone_clean
        elif not phone_clean.startswith("+"):
            phone_clean = "+" + phone_clean
        
        # Build personalization
        retell_vars = {
            "business_name": lead.get('Business Name', 'there'),
            "icebreaker": str(lead.get('Icebreaker', ''))[:100],
            "service_type": lead.get('Primary_Service', 'automotive services'),
            "market_tier": lead.get('Market_Tier', 'premium')
        }
        
        # Make Retell API call
        headers = {
            "Authorization": f"Bearer {RETELL_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "agent_id": RETELL_AGENT_ID,
            "customer_number": phone_clean,
            "retell_llm_dynamic_variables": retell_vars
        }
        
        response = requests.post(
            "https://api.retellai.com/v2/create-phone-call",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 201:
            result = response.json()
            return {
                "success": True,
                "message": f"Call initiated to {lead['Business Name']}",
                "phone": phone_clean,
                "call_id": result.get('call_id', 'N/A')
            }
        else:
            return {
                "success": False,
                "error": f"Retell API error: {response.status_code}",
                "details": response.text[:200]
            }
            
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# LEAD MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def read_leads(limit: int = 20):
    """Read leads from qualified_leads.csv"""
    csv_path = OROVA_ROOT / "qualified_leads.csv"
    if not csv_path.exists():
        return {"success": False, "error": "qualified_leads.csv not found"}
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            leads = list(reader)
        
        return {
            "success": True,
            "total": len(leads),
            "leads": leads[:limit],
            "showing": min(limit, len(leads))
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def add_lead(name: str, phone: str = "", email: str = "", business: str = "", notes: str = ""):
    """Add a new lead to qualified_leads.csv"""
    csv_path = OROVA_ROOT / "qualified_leads.csv"
    
    try:
        fieldnames = ["timestamp", "Business Name", "Phone", "Contact Email", "Website", "notes", "AI_Score"]
        rows = []
        
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or fieldnames
                rows = list(reader)
        
        new_lead = {
            "timestamp": datetime.now().isoformat(),
            "Business Name": name,
            "Phone": phone,
            "Contact Email": email,
            "Website": business,
            "notes": notes,
            "AI_Score": ""
        }
        rows.append(new_lead)
        
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return {
            "success": True,
            "message": f"Added lead: {name}",
            "reminder": "⚠️ Lead must be scored by Opal app before processing (per MEMORANDUM.md)"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_memorandum():
    """Read the OROVA MEMORANDUM for operational protocols"""
    memo_path = OROVA_ROOT / "MEMORANDUM.md"
    if not memo_path.exists():
        return {"success": False, "error": "MEMORANDUM.md not found"}
    
    try:
        with open(memo_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"success": True, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

SCHEDULE_FILE = Path(__file__).parent.parent / "schedule.json"

def load_schedule():
    if SCHEDULE_FILE.exists():
        with open(SCHEDULE_FILE, 'r') as f:
            return json.load(f)
    return {"tasks": [], "reminders": []}

def save_schedule(schedule):
    with open(SCHEDULE_FILE, 'w') as f:
        json.dump(schedule, f, indent=2)

def add_scheduled_task(task_name: str, time_str: str, command: str, repeat: str = "once"):
    """
    Schedule a task to run at a specific time
    time_str: "HH:MM" format (24-hour)
    repeat: "once", "daily", "weekdays"
    command: what to run (e.g., "run_scraper", "run_scribe", "send_report")
    """
    schedule = load_schedule()
    
    task = {
        "id": len(schedule["tasks"]) + 1,
        "name": task_name,
        "time": time_str,
        "command": command,
        "repeat": repeat,
        "enabled": True,
        "created": datetime.now().isoformat(),
        "last_run": None
    }
    
    schedule["tasks"].append(task)
    save_schedule(schedule)
    
    return {
        "success": True,
        "message": f"Scheduled '{task_name}' at {time_str} ({repeat})",
        "task": task
    }

def add_reminder(message: str, when: str):
    """
    Add a reminder
    when: "in 30 minutes", "at 14:00", "tomorrow 9:00"
    """
    schedule = load_schedule()
    
    # Parse the 'when' parameter
    now = datetime.now()
    remind_at = None
    
    if when.startswith("in "):
        # Parse "in X minutes/hours/seconds"
        import re
        match = re.match(r'in (\d+) (second|seconds|sec|secs|minute|minutes|hour|hours|min|mins|hr|hrs)', when)
        if match:
            amount = int(match.group(1))
            unit = match.group(2)
            if 'hour' in unit or 'hr' in unit:
                remind_at = now + timedelta(hours=amount)
            elif 'second' in unit or 'sec' in unit:
                remind_at = now + timedelta(seconds=amount)
            else:
                remind_at = now + timedelta(minutes=amount)
    elif when.startswith("at "):
        # Parse "at HH:MM"
        time_str = when[3:].strip()
        try:
            hour, minute = map(int, time_str.split(":"))
            remind_at = now.replace(hour=hour, minute=minute, second=0)
            if remind_at < now:
                remind_at += timedelta(days=1)
        except:
            pass
    elif "tomorrow" in when.lower():
        # Parse "tomorrow HH:MM"
        import re
        match = re.search(r'(\d{1,2}):(\d{2})', when)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            remind_at = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0)
    
    if not remind_at:
        return {"success": False, "error": f"Could not parse time: {when}"}
    
    reminder = {
        "id": len(schedule["reminders"]) + 1,
        "message": message,
        "remind_at": remind_at.isoformat(),
        "created": now.isoformat(),
        "sent": False
    }
    
    schedule["reminders"].append(reminder)
    save_schedule(schedule)
    
    return {
        "success": True,
        "message": f"Reminder set for {remind_at.strftime('%Y-%m-%d %H:%M')}",
        "reminder": reminder
    }

def list_schedule():
    """List all scheduled tasks and reminders"""
    schedule = load_schedule()
    
    return {
        "success": True,
        "tasks": schedule.get("tasks", []),
        "reminders": [r for r in schedule.get("reminders", []) if not r.get("sent", False)],
        "task_count": len(schedule.get("tasks", [])),
        "pending_reminders": len([r for r in schedule.get("reminders", []) if not r.get("sent", False)])
    }

def check_due_reminders():
    """Check for any reminders that are due"""
    schedule = load_schedule()
    now = datetime.now()
    due = []
    
    for reminder in schedule.get("reminders", []):
        if reminder.get("sent", False):
            continue
        
        remind_at = datetime.fromisoformat(reminder["remind_at"])
        if remind_at <= now:
            due.append(reminder)
            reminder["sent"] = True
    
    if due:
        save_schedule(schedule)
    
    return {
        "success": True,
        "due_reminders": due,
        "count": len(due)
    }

def run_scheduled_command(command: str):
    """Execute a scheduled command"""
    command_map = {
        # Chain Scraper -> Batch Processor (Hunter) to update CRM automatically
        "run_scraper": f"python {OROVA_ROOT / 'scraper.py'} && python {OROVA_ROOT / 'batch_processor.py'}",
        "run_scribe": f"python {OROVA_ROOT / 'email_agent.py'}",
        "run_hunter": f"python {OROVA_ROOT / 'batch_processor.py'}",
        "list_leads": "read_leads"
    }
    
    if command in command_map:
        if command_map[command].startswith("python"):
            # Run as subprocess
            try:
                result = subprocess.run(
                    command_map[command],
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(OROVA_ROOT)
                )
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout[:2000] + result.stderr[:500]
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # Internal command
            return {"success": True, "note": f"Would run: {command_map[command]}"}
    
    return {"success": False, "error": f"Unknown command: {command}"}

# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_orova_skills(TOOLS, tool_decorator):
    """Register all OROVA skills"""
    
    # Web Search
    @tool_decorator("web_search", "Search the web using DuckDuckGo (free, no API key)")
    def _web_search(query: str, max_results: int = 5):
        return web_search_ddg(query, max_results)
    TOOLS["web_search"] = {"func": _web_search, "description": "Search the web using DuckDuckGo (free)"}
    
    # Lead Management
    TOOLS["read_leads"] = {"func": read_leads, "description": "Read leads from qualified_leads.csv"}
    TOOLS["add_lead"] = {"func": add_lead, "description": "Add a new lead to qualified_leads.csv"}
    TOOLS["check_memorandum"] = {"func": check_memorandum, "description": "Read OROVA operational protocols"}
    
    # Email
    TOOLS["send_email"] = {"func": send_email, "description": "Send an email via Gmail"}
    TOOLS["draft_email"] = {"func": generate_cold_email, "description": "Generate a cold email draft"}
    TOOLS["email_lead"] = {"func": email_lead, "description": "Draft/send email to a lead from CSV"}
    
    # Caller
    TOOLS["list_hot_leads"] = {"func": list_leads_for_calling, "description": "List leads ready for cold calling"}
    TOOLS["call_lead"] = {"func": call_lead, "description": "Initiate Retell AI call to a lead"}
    
    # Scheduler
    TOOLS["schedule_task"] = {"func": add_scheduled_task, "description": "Schedule a task (e.g., run scraper daily at 9 AM)"}
    TOOLS["add_reminder"] = {"func": add_reminder, "description": "Set a reminder (e.g., 'in 30 seconds', 'in 5 minutes', 'at 14:00')"}
    TOOLS["list_schedule"] = {"func": list_schedule, "description": "List scheduled tasks and reminders"}
    TOOLS["check_reminders"] = {"func": check_due_reminders, "description": "Check for due reminders"}
    
    return TOOLS
