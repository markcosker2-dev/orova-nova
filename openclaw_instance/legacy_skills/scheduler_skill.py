# -*- coding: utf-8 -*-
"""
Scheduler Skill for MarkBot
Auto-running scheduled tasks and reminders
"""

import os
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta

SCHEDULE_FILE = Path(__file__).parent.parent / "schedule.json"


def load_schedule():
    """Load schedule from file"""
    if SCHEDULE_FILE.exists():
        try:
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure required keys exist
                if "tasks" not in data:
                    data["tasks"] = []
                if "reminders" not in data:
                    data["reminders"] = []
                return data
        except:
            pass
    return {"tasks": [], "reminders": []}


def save_schedule(schedule):
    """Save schedule to file"""
    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, indent=2, ensure_ascii=False)


def add_scheduled_task(task_name: str, time_str: str, command: str, repeat: str = "daily", chat_id: int = None):
    """
    Schedule a task to run at a specific time
    
    Args:
        task_name: Name of the task
        time_str: "HH:MM" format (24-hour)
        command: What to run - can be:
            - "shell: <command>" for shell commands
            - "python: <script.py>" for Python scripts
            - "tool: <tool_name>" to call a bot tool
            - Just a description for AI to interpret
        repeat: "once", "daily", "weekdays", "weekly"
        chat_id: Telegram chat ID to send results to
    """
    schedule = load_schedule()
    
    # Validate time format
    try:
        hour, minute = map(int, time_str.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return {"success": False, "error": "Invalid time. Use HH:MM format (00:00 to 23:59)"}
    except:
        return {"success": False, "error": "Invalid time format. Use HH:MM (e.g., 09:00, 14:30)"}
    
    # Calculate next run time
    now = datetime.now()
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    
    task = {
        "id": len(schedule["tasks"]) + 1,
        "name": task_name,
        "time": time_str,
        "command": command,
        "repeat": repeat,
        "enabled": True,
        "chat_id": chat_id,
        "created": now.isoformat(),
        "next_run": next_run.isoformat(),
        "last_run": None,
        "run_count": 0
    }
    
    schedule["tasks"].append(task)
    save_schedule(schedule)
    
    return {
        "success": True,
        "message": f"Scheduled '{task_name}' at {time_str} ({repeat})",
        "next_run": next_run.strftime("%Y-%m-%d %H:%M"),
        "task": task
    }


def get_due_tasks():
    """Get tasks that are due to run now"""
    schedule = load_schedule()
    now = datetime.now()
    due_tasks = []
    
    for task in schedule.get("tasks", []):
        if not task.get("enabled", True):
            continue
        
        next_run_str = task.get("next_run")
        if not next_run_str:
            continue
        
        try:
            next_run = datetime.fromisoformat(next_run_str)
            if next_run <= now:
                due_tasks.append(task)
        except:
            continue
    
    return due_tasks


def execute_task(task: dict):
    """Execute a scheduled task and return the result"""
    command = task.get("command", "")
    result = {"success": False, "output": "", "error": ""}
    
    try:
        # Determine command type
        if command.startswith("shell:"):
            # Run shell command
            shell_cmd = command[6:].strip()
            proc = subprocess.run(
                shell_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(Path(__file__).parent.parent)
            )
            result["success"] = proc.returncode == 0
            result["output"] = proc.stdout[:2000] if proc.stdout else ""
            if proc.returncode != 0:
                result["error"] = proc.stderr[:500] if proc.stderr else ""
        
        elif command.startswith("python:"):
            # Run Python script
            script = command[7:].strip()
            script_path = Path(__file__).parent.parent.parent / script
            if not script_path.exists():
                script_path = Path(__file__).parent.parent / script
            
            if script_path.exists():
                proc = subprocess.run(
                    ["python", str(script_path)],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(script_path.parent)
                )
                result["success"] = proc.returncode == 0
                result["output"] = proc.stdout[:2000] if proc.stdout else ""
                if proc.returncode != 0:
                    result["error"] = proc.stderr[:500] if proc.stderr else ""
            else:
                result["error"] = f"Script not found: {script}"
        
        elif command.startswith("tool:"):
            # This will be handled by the bot itself
            result["success"] = True
            result["output"] = f"Tool call: {command[5:].strip()}"
            result["is_tool_call"] = True
        
        else:
            # Just a description - mark as needing AI interpretation
            result["success"] = True
            result["output"] = f"Task: {command}"
            result["needs_ai"] = True
    
    except subprocess.TimeoutExpired:
        result["error"] = "Task timed out"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def mark_task_completed(task_id: int):
    """Mark a task as run and update next run time"""
    schedule = load_schedule()
    now = datetime.now()
    
    for task in schedule.get("tasks", []):
        if task.get("id") != task_id:
            continue
        
        task["last_run"] = now.isoformat()
        task["run_count"] = task.get("run_count", 0) + 1
        
        repeat = task.get("repeat", "once")
        
        if repeat == "once":
            task["enabled"] = False
            task["next_run"] = None
        elif repeat == "daily":
            # Next day at same time
            next_run = datetime.fromisoformat(task["next_run"]) + timedelta(days=1)
            task["next_run"] = next_run.isoformat()
        elif repeat == "weekdays":
            # Next weekday at same time
            next_run = datetime.fromisoformat(task["next_run"]) + timedelta(days=1)
            while next_run.weekday() >= 5:  # 5=Saturday, 6=Sunday
                next_run += timedelta(days=1)
            task["next_run"] = next_run.isoformat()
        elif repeat == "weekly":
            next_run = datetime.fromisoformat(task["next_run"]) + timedelta(weeks=1)
            task["next_run"] = next_run.isoformat()
        
        break
    
    save_schedule(schedule)


def enable_task(task_id: int, enabled: bool = True):
    """Enable or disable a task"""
    schedule = load_schedule()
    
    for task in schedule.get("tasks", []):
        if task.get("id") == task_id:
            task["enabled"] = enabled
            if enabled and not task.get("next_run"):
                # Recalculate next run
                time_str = task.get("time", "00:00")
                try:
                    hour, minute = map(int, time_str.split(":"))
                    now = datetime.now()
                    next_run = now.replace(hour=hour, minute=minute, second=0)
                    if next_run <= now:
                        next_run += timedelta(days=1)
                    task["next_run"] = next_run.isoformat()
                except:
                    pass
            save_schedule(schedule)
            return {"success": True, "message": f"Task #{task_id} {'enabled' if enabled else 'disabled'}"}
    
    return {"success": False, "error": f"Task #{task_id} not found"}


def delete_task(task_id: int):
    """Delete a scheduled task"""
    schedule = load_schedule()
    original_count = len(schedule.get("tasks", []))
    schedule["tasks"] = [t for t in schedule.get("tasks", []) if t.get("id") != task_id]
    
    if len(schedule["tasks"]) == original_count:
        return {"success": False, "error": f"Task #{task_id} not found"}
    
    save_schedule(schedule)
    return {"success": True, "message": f"Task #{task_id} deleted"}


def list_scheduled_tasks():
    """List all scheduled tasks"""
    schedule = load_schedule()
    tasks = schedule.get("tasks", [])
    
    formatted = []
    for t in tasks:
        formatted.append({
            "id": t.get("id"),
            "name": t.get("name"),
            "time": t.get("time"),
            "command": t.get("command", "")[:50],
            "repeat": t.get("repeat"),
            "enabled": t.get("enabled", True),
            "next_run": t.get("next_run", "")[:16] if t.get("next_run") else "N/A",
            "last_run": t.get("last_run", "")[:16] if t.get("last_run") else "Never"
        })
    
    return {
        "success": True,
        "count": len(formatted),
        "tasks": formatted
    }


def register_scheduler_skills(TOOLS, tool_decorator):
    """Register Scheduler tools"""
    
    @tool_decorator("schedule_task", "Schedule a task to run at a specific time")
    def _schedule_task(**kwargs):
        name = kwargs.get('name') or kwargs.get('task_name') or kwargs.get('task')
        time_str = kwargs.get('time') or kwargs.get('at') or kwargs.get('time_str')
        command = kwargs.get('command') or kwargs.get('cmd') or kwargs.get('run')
        repeat = kwargs.get('repeat') or kwargs.get('frequency') or "daily"
        
        if not name:
            return {"success": False, "error": "Missing 'name' parameter"}
        if not time_str:
            return {"success": False, "error": "Missing 'time' parameter (HH:MM format)"}
        if not command:
            return {"success": False, "error": "Missing 'command' parameter"}
        
        if repeat not in ["once", "daily", "weekdays", "weekly"]:
            repeat = "daily"
        
        return add_scheduled_task(name, time_str, command, repeat)
    
    @tool_decorator("list_scheduled", "List all scheduled tasks")
    def _list_scheduled(**kwargs):
        return list_scheduled_tasks()
    
    @tool_decorator("enable_task", "Enable or disable a scheduled task")
    def _enable_task(**kwargs):
        task_id = kwargs.get('task_id') or kwargs.get('id')
        enabled = kwargs.get('enabled', True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ['true', 'yes', '1', 'on']
        
        if not task_id:
            return {"success": False, "error": "Missing 'task_id' parameter"}
        
        try:
            task_id = int(task_id)
        except:
            return {"success": False, "error": "task_id must be a number"}
        
        return enable_task(task_id, enabled)
    
    @tool_decorator("delete_scheduled", "Delete a scheduled task")
    def _delete_scheduled(**kwargs):
        task_id = kwargs.get('task_id') or kwargs.get('id')
        
        if not task_id:
            return {"success": False, "error": "Missing 'task_id' parameter"}
        
        try:
            task_id = int(task_id)
        except:
            return {"success": False, "error": "task_id must be a number"}
        
        return delete_task(task_id)
    
    TOOLS["schedule_task"] = {"func": _schedule_task, "description": "Schedule a task to run at a time"}
    TOOLS["list_scheduled"] = {"func": _list_scheduled, "description": "List scheduled tasks"}
    TOOLS["enable_task"] = {"func": _enable_task, "description": "Enable/disable a scheduled task"}
    TOOLS["delete_scheduled"] = {"func": _delete_scheduled, "description": "Delete a scheduled task"}
    
    return TOOLS
