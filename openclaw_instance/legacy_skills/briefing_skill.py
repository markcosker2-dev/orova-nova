# -*- coding: utf-8 -*-
"""
Briefing Skill for MarkBot
Daily morning briefing with calendar, emails, and reminders
"""

import os
from pathlib import Path
from datetime import datetime

# Import other skills
from skills.gmail_skill import get_inbox
from skills.calendar_skill import get_today_events
from skills.orova_skills import list_schedule, read_leads, web_search_ddg
from skills.memory_skill import load_memory
from skills.lead_finder import LeadFinder


def deep_research(topic: str):
    """
    Perform deep research on a topic using multi-source coordination.
    (Web Search + News Search + Synthesis)
    """
    report = f"# Deep Research Report: {topic}\n\n"

    # 1. General Context (Web)
    report += "## 🌍 General Context\n\n"
    web_res = web_search_ddg(topic, max_results=5)
    if web_res.get("success"):
        for r in web_res.get("results", []):
            report += f"- **{r['title']}**: {r['snippet']} ([Link]({r['url']}))\n"
    else:
        report += f"Web search failed: {web_res.get('error')}\n"

    # 2. Latest News (News)
    report += "\n## 📰 Latest News\n\n"
    news_res = LeadFinder.news_search(topic, limit=5)
    if news_res:
        for n in news_res:
            report += f"- **{n['title']}** ({n['source']}, {n['date']}): {n['snippet']} ([Link]({n['url']}))\n"
    else:
        report += "No recent news found.\n"

    return {
        "success": True,
        "topic": topic,
        "report": report
    }


def generate_briefing():
    """Generate a daily briefing"""
    briefing = f"# Daily Briefing - {datetime.now().strftime('%A, %B %d, %Y')}\n\n"
    
    # Calendar
    briefing += "## 📅 Today's Calendar\n\n"
    calendar = get_today_events()
    if calendar.get("success"):
        if calendar.get("count", 0) > 0:
            for event in calendar.get("events", []):
                briefing += f"- {event['start']}: {event['summary']}\n"
        else:
            briefing += "No events scheduled today.\n"
    else:
        briefing += f"Could not load calendar: {calendar.get('error', 'Unknown error')}\n"
    
    briefing += "\n"
    
    # Emails
    briefing += "## 📧 Unread Emails\n\n"
    inbox = get_inbox(max_results=5, unread_only=True)
    if inbox.get("success"):
        if inbox.get("count", 0) > 0:
            for email in inbox.get("emails", []):
                briefing += f"- **{email['from'][:30]}**: {email['subject'][:50]}\n"
        else:
            briefing += "No unread emails!\n"
    else:
        briefing += f"Could not load inbox: {inbox.get('error', 'Unknown error')}\n"
    
    briefing += "\n"
    
    # Reminders
    briefing += "## ⏰ Pending Reminders\n\n"
    schedule = list_schedule()
    if schedule.get("success"):
        reminders = schedule.get("reminders", [])
        if reminders:
            for r in reminders[:5]:
                briefing += f"- {r['message'][:50]}\n"
        else:
            briefing += "No pending reminders.\n"
    
    briefing += "\n"
    
    # Hot Leads (for business)
    briefing += "## 🔥 Hot Leads\n\n"
    leads = read_leads(limit=5)
    if leads.get("success") and leads.get("total", 0) > 0:
        briefing += f"{leads.get('total', 0)} leads in pipeline.\n"
    else:
        briefing += "No leads data available.\n"
    
    # Memory/Notes
    memory = load_memory()
    if memory and memory.strip():
        briefing += "\n## 📝 Notes\n\n"
        facts = [line.strip() for line in memory.split("\n") if line.strip().startswith("- ")]
        for fact in facts[:3]:
            briefing += f"{fact}\n"
    
    return {
        "success": True,
        "briefing": briefing,
        "date": datetime.now().isoformat()
    }


def register_briefing_skills(TOOLS, tool_decorator):
    """Register Briefing tools"""
    
    @tool_decorator("daily_briefing", "Generate a daily briefing with calendar, emails, and reminders")
    def _briefing():
        return generate_briefing()

    @tool_decorator("deep_research", "Perform deep multi-source research on a topic")
    def _deep_research(topic: str):
        return deep_research(topic)
    
    TOOLS["daily_briefing"] = {"func": _briefing, "description": "Generate daily briefing"}
    TOOLS["deep_research"] = {"func": _deep_research, "description": "Deep multi-source research"}
    
    return TOOLS
