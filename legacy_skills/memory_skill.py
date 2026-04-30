# -*- coding: utf-8 -*-
"""
Memory Skill for MarkBot
Persistent memory - remembers facts about the user
"""

import os
from pathlib import Path
from datetime import datetime

MEMORY_FILE = Path(__file__).parent.parent / "memory.md"


def load_memory():
    """Load memory from file"""
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return ""


def save_memory(content: str):
    """Save memory to file"""
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        f.write(content)


def remember(fact: str):
    """Add a fact to memory"""
    memory = load_memory()
    
    # Initialize if empty
    if not memory.strip():
        memory = "# MarkBot Memory\n\n## Facts about Mark\n\n"
    
    # Add new fact
    timestamp = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"- {fact} (added {timestamp})\n"
    memory += new_entry
    
    save_memory(memory)
    
    return {
        "success": True,
        "message": f"Remembered: {fact}",
        "total_facts": memory.count("- ")
    }


def forget(fact_keyword: str):
    """Remove a fact from memory containing the keyword"""
    memory = load_memory()
    
    lines = memory.split("\n")
    new_lines = []
    removed = 0
    
    for line in lines:
        if fact_keyword.lower() in line.lower() and line.strip().startswith("- "):
            removed += 1
        else:
            new_lines.append(line)
    
    save_memory("\n".join(new_lines))
    
    return {
        "success": True,
        "removed": removed,
        "message": f"Forgot {removed} fact(s) containing '{fact_keyword}'"
    }


def recall(keyword: str = ""):
    """Recall facts from memory"""
    memory = load_memory()
    
    if not memory.strip():
        return {"success": True, "facts": [], "message": "Memory is empty"}
    
    lines = memory.split("\n")
    facts = [line.strip() for line in lines if line.strip().startswith("- ")]
    
    if keyword:
        facts = [f for f in facts if keyword.lower() in f.lower()]
    
    return {
        "success": True,
        "count": len(facts),
        "facts": facts[:20],  # Limit to 20
        "query": keyword if keyword else "(all)"
    }


def get_context_for_prompt():
    """Get memory context to add to system prompt"""
    memory = load_memory()
    if not memory.strip():
        return ""
    
    lines = memory.split("\n")
    facts = [line.strip() for line in lines if line.strip().startswith("- ")]
    
    if not facts:
        return ""
    
    return "\n\nThings I remember about Mark:\n" + "\n".join(facts[:10])


def register_memory_skills(TOOLS, tool_decorator):
    """Register Memory tools"""
    
    @tool_decorator("remember", "Remember a fact about Mark")
    def _remember(fact: str):
        return remember(fact)
    
    @tool_decorator("forget", "Forget facts containing a keyword")
    def _forget(keyword: str):
        return forget(keyword)
    
    @tool_decorator("recall", "Recall facts from memory")
    def _recall(keyword: str = ""):
        return recall(keyword)
    
    TOOLS["remember"] = {"func": _remember, "description": "Remember a fact about Mark"}
    TOOLS["forget"] = {"func": _forget, "description": "Forget facts containing keyword"}
    TOOLS["recall"] = {"func": _recall, "description": "Recall facts from memory"}
    
    return TOOLS
