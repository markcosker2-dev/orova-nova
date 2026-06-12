# -*- coding: utf-8 -*-
"""
Notes & Tasks Skill for MarkBot
Quick capture of notes and TODO management
"""

import os
import json
from pathlib import Path
from datetime import datetime

# Data files
NOTES_FILE = Path(__file__).parent.parent / "notes.json"
TASKS_FILE = Path(__file__).parent.parent / "tasks.json"


def _load_json(file_path: Path) -> list:
    """Load JSON list from file"""
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []


def _save_json(file_path: Path, data: list):
    """Save list to JSON file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# NOTES
# ═══════════════════════════════════════════════════════════════════════════════

def add_note(content: str, category: str = "general"):
    """Add a quick note
    
    Args:
        content: The note content
        category: Optional category (general, idea, meeting, etc.)
    """
    notes = _load_json(NOTES_FILE)
    
    note = {
        "id": len(notes) + 1,
        "content": content,
        "category": category,
        "created": datetime.now().isoformat(),
    }
    
    notes.append(note)
    _save_json(NOTES_FILE, notes)
    
    return {
        "success": True,
        "message": f"Note #{note['id']} added",
        "note": note
    }


def log_skill_note(skill_name: str, message: str, category: str = "self-improvement"):
    """Log a short skill improvement / feedback note."""
    if not message:
        return {"success": False, "error": "Missing message"}
    content = f"[{skill_name}] {message}"
    return add_note(content, category)


def list_notes(category: str = None, limit: int = 10):
    """List notes
    
    Args:
        category: Filter by category (optional)
        limit: Maximum notes to return
    """
    notes = _load_json(NOTES_FILE)
    
    if category:
        notes = [n for n in notes if n.get("category", "").lower() == category.lower()]
    
    # Sort by newest first
    notes = sorted(notes, key=lambda x: x.get("created", ""), reverse=True)
    
    return {
        "success": True,
        "total": len(notes),
        "showing": min(limit, len(notes)),
        "notes": notes[:limit]
    }


def delete_note(note_id: int):
    """Delete a note by ID"""
    notes = _load_json(NOTES_FILE)
    
    original_count = len(notes)
    notes = [n for n in notes if n.get("id") != note_id]
    
    if len(notes) == original_count:
        return {"success": False, "error": f"Note #{note_id} not found"}
    
    _save_json(NOTES_FILE, notes)
    
    return {
        "success": True,
        "message": f"Note #{note_id} deleted"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TASKS / TODO
# ═══════════════════════════════════════════════════════════════════════════════

def add_task(task: str, priority: str = "normal"):
    """Add a TODO task
    
    Args:
        task: The task description
        priority: low, normal, or high
    """
    tasks = _load_json(TASKS_FILE)
    
    new_task = {
        "id": len(tasks) + 1,
        "task": task,
        "priority": priority,
        "done": False,
        "created": datetime.now().isoformat(),
    }
    
    tasks.append(new_task)
    _save_json(TASKS_FILE, tasks)
    
    return {
        "success": True,
        "message": f"Task #{new_task['id']} added",
        "task": new_task
    }


def list_tasks(show_done: bool = False):
    """List TODO tasks
    
    Args:
        show_done: If True, also show completed tasks
    """
    tasks = _load_json(TASKS_FILE)
    
    if not show_done:
        tasks = [t for t in tasks if not t.get("done", False)]
    
    # Sort by priority (high first) then by ID
    priority_order = {"high": 0, "normal": 1, "low": 2}
    tasks = sorted(tasks, key=lambda x: (priority_order.get(x.get("priority", "normal"), 1), x.get("id", 0)))
    
    return {
        "success": True,
        "total": len(tasks),
        "pending": len([t for t in tasks if not t.get("done", False)]),
        "tasks": tasks
    }


def complete_task(task_id: int):
    """Mark a task as completed"""
    tasks = _load_json(TASKS_FILE)
    
    found = False
    for task in tasks:
        if task.get("id") == task_id:
            task["done"] = True
            task["completed"] = datetime.now().isoformat()
            found = True
            break
    
    if not found:
        return {"success": False, "error": f"Task #{task_id} not found"}
    
    _save_json(TASKS_FILE, tasks)
    
    return {
        "success": True,
        "message": f"Task #{task_id} marked as done ✓"
    }


def delete_task(task_id: int):
    """Delete a task"""
    tasks = _load_json(TASKS_FILE)
    
    original_count = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    
    if len(tasks) == original_count:
        return {"success": False, "error": f"Task #{task_id} not found"}
    
    _save_json(TASKS_FILE, tasks)
    
    return {
        "success": True,
        "message": f"Task #{task_id} deleted"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_notes_skills(TOOLS, tool_decorator):
    """Register Notes & Tasks tools"""
    
    # Notes
    @tool_decorator("add_note", "Add a quick note")
    def _add_note(**kwargs):
        content = kwargs.get('content') or kwargs.get('note') or kwargs.get('text')
        category = kwargs.get('category') or "general"
        
        if not content:
            return {"success": False, "error": "Missing 'content' parameter"}
        
        return add_note(content, category)
    
    @tool_decorator("list_notes", "List all notes")
    def _list_notes(**kwargs):
        category = kwargs.get('category')
        limit = kwargs.get('limit') or 10
        try:
            limit = int(limit)
        except:
            limit = 10
        return list_notes(category, limit)
    
    @tool_decorator("delete_note", "Delete a note")
    def _delete_note(**kwargs):
        note_id = kwargs.get('note_id') or kwargs.get('id')
        if not note_id:
            return {"success": False, "error": "Missing 'note_id' parameter"}
        try:
            note_id = int(note_id)
        except:
            return {"success": False, "error": "note_id must be a number"}
        return delete_note(note_id)
    
    # Tasks
    @tool_decorator("add_task", "Add a TODO task")
    def _add_task(**kwargs):
        task = kwargs.get('task') or kwargs.get('todo') or kwargs.get('content')
        priority = kwargs.get('priority') or "normal"
        
        if not task:
            return {"success": False, "error": "Missing 'task' parameter"}
        
        return add_task(task, priority)
    
    @tool_decorator("list_tasks", "List TODO tasks")
    def _list_tasks(**kwargs):
        show_done = kwargs.get('show_done') or kwargs.get('all') or False
        return list_tasks(show_done)
    
    @tool_decorator("complete_task", "Mark a task as done")
    def _complete_task(**kwargs):
        task_id = kwargs.get('task_id') or kwargs.get('id')
        if not task_id:
            return {"success": False, "error": "Missing 'task_id' parameter"}
        try:
            task_id = int(task_id)
        except:
            return {"success": False, "error": "task_id must be a number"}
        return complete_task(task_id)
    
    @tool_decorator("delete_task", "Delete a task")
    def _delete_task(**kwargs):
        task_id = kwargs.get('task_id') or kwargs.get('id')
        if not task_id:
            return {"success": False, "error": "Missing 'task_id' parameter"}
        try:
            task_id = int(task_id)
        except:
            return {"success": False, "error": "task_id must be a number"}
        return delete_task(task_id)
    
    TOOLS["add_note"] = {"func": _add_note, "description": "Add a quick note"}
    TOOLS["list_notes"] = {"func": _list_notes, "description": "List notes"}
    TOOLS["delete_note"] = {"func": _delete_note, "description": "Delete a note"}
    TOOLS["add_task"] = {"func": _add_task, "description": "Add a TODO task"}
    TOOLS["list_tasks"] = {"func": _list_tasks, "description": "List TODO tasks"}
    TOOLS["complete_task"] = {"func": _complete_task, "description": "Complete a task"}
    TOOLS["delete_task"] = {"func": _delete_task, "description": "Delete a task"}
    
    return TOOLS
