# -*- coding: utf-8 -*-
"""
CEO Memory Skill for OROVA MikeBot
Persistent memory layer using SQLite + JSON (100% Free, No External APIs)

Features:
- Conversation history with semantic search (basic keyword matching)
- Agency knowledge base (pricing, clients, protocols)
- Context injection into system prompts
"""

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Storage paths
MEMORY_DIR = Path(__file__).parent.parent / "mem0_storage"
MEMORY_DIR.mkdir(exist_ok=True)

CEO_MEMORY_DB = MEMORY_DIR / "ceo_memory.db"
AGENCY_KNOWLEDGE_FILE = MEMORY_DIR / "agency_knowledge.json"

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════

def get_db_connection():
    """Get SQLite connection with row factory"""
    conn = sqlite3.connect(CEO_MEMORY_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Initialize the CEO memory database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Conversation memories table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'mark',
            memory TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            importance INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Conversation history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'mark',
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create indexes for faster search
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON conversation_history(user_id)")
    
    conn.commit()
    conn.close()

# Initialize on import
init_database()

# ═══════════════════════════════════════════════════════════════════════════════
# AGENCY KNOWLEDGE BASE
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_AGENCY_KNOWLEDGE = {
    "agency_name": "OROVA",
    "ceo": "Mark",
    "services": {
        "lead_generation": {
            "price": "$4,000/month",
            "description": "AI-powered lead generation for automotive businesses"
        },
        "lead_generation_plus_qualification": {
            "price": "$5,000/month", 
            "description": "Lead generation + AI qualification and scoring"
        }
    },
    "tech_stack": {
        "automation": "Python",
        "crm": "Google Sheets",
        "primary_lead_source": "Instagram",
        "enrichment": ["Tavily", "Playwright"]
    },
    "protocols": {
        "mandatory_opal_scoring": "Every lead must be scored by Opal before processing",
        "lead_sources": ["Instagram", "Quora", "LinkedIn"]
    },
    "target_market": {
        "industry": "Automotive",
        "location": "California, USA",
        "business_types": ["Dealerships", "Performance Shops", "Collision Centers"]
    },
    "clients": []
}

def load_agency_knowledge() -> Dict[str, Any]:
    """Load agency knowledge from JSON file"""
    if AGENCY_KNOWLEDGE_FILE.exists():
        try:
            with open(AGENCY_KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_AGENCY_KNOWLEDGE.copy()

def save_agency_knowledge(knowledge: Dict[str, Any]):
    """Save agency knowledge to JSON file"""
    with open(AGENCY_KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(knowledge, f, indent=2)

# Initialize agency knowledge if not exists
if not AGENCY_KNOWLEDGE_FILE.exists():
    save_agency_knowledge(DEFAULT_AGENCY_KNOWLEDGE)

# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def add_memory(memory: str, category: str = "general", importance: int = 5, user_id: str = "mark") -> Dict:
    """Add a new memory to the CEO brain"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO memories (user_id, memory, category, importance) VALUES (?, ?, ?, ?)",
        (user_id, memory, category, importance)
    )
    
    memory_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "memory_id": memory_id,
        "message": f"Stored: {memory[:50]}..."
    }

def search_memories(query: str, user_id: str = "mark", limit: int = 5) -> List[Dict]:
    """Search memories using keyword matching"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Simple keyword search (can be enhanced with FTS5 later)
    keywords = query.lower().split()
    conditions = " OR ".join(["LOWER(memory) LIKE ?" for _ in keywords])
    params = [f"%{kw}%" for kw in keywords]
    params.append(user_id)
    
    cursor.execute(f"""
        SELECT id, memory, category, importance, created_at
        FROM memories 
        WHERE ({conditions}) AND user_id = ?
        ORDER BY importance DESC, created_at DESC
        LIMIT {limit}
    """, params)
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return results

def get_all_memories(user_id: str = "mark", category: Optional[str] = None) -> List[Dict]:
    """Get all memories, optionally filtered by category"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if category:
        cursor.execute(
            "SELECT * FROM memories WHERE user_id = ? AND category = ? ORDER BY importance DESC",
            (user_id, category)
        )
    else:
        cursor.execute(
            "SELECT * FROM memories WHERE user_id = ? ORDER BY importance DESC",
            (user_id,)
        )
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return results

def delete_memory(memory_id: int) -> Dict:
    """Delete a specific memory"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    deleted = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    return {"success": deleted > 0, "deleted": deleted}

# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION HISTORY
# ═══════════════════════════════════════════════════════════════════════════════

def add_to_history(role: str, content: str, user_id: str = "mark"):
    """Add a message to conversation history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO conversation_history (user_id, role, content) VALUES (?, ?, ?)",
        (user_id, role, content)
    )
    
    conn.commit()
    conn.close()

def get_recent_history(user_id: str = "mark", limit: int = 10) -> List[Dict]:
    """Get recent conversation history"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT role, content, created_at 
        FROM conversation_history 
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (user_id, limit))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    # Reverse to get chronological order
    return list(reversed(results))

# ═══════════════════════════════════════════════════════════════════════════════
# CONTEXT GENERATION FOR SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

def get_ceo_context(query: str = "", user_id: str = "mark") -> str:
    """Generate context string to inject into system prompt"""
    context_parts = []
    
    # Agency knowledge
    knowledge = load_agency_knowledge()
    context_parts.append("## OROVA Agency Knowledge")
    context_parts.append(f"- Agency: {knowledge.get('agency_name', 'OROVA')}")
    context_parts.append(f"- CEO: {knowledge.get('ceo', 'Mark')}")
    
    services = knowledge.get('services', {})
    if services:
        context_parts.append("- Services:")
        for name, details in services.items():
            context_parts.append(f"  - {name}: {details.get('price', 'N/A')}")
    
    protocols = knowledge.get('protocols', {})
    if protocols:
        context_parts.append("- Protocols:")
        for name, desc in protocols.items():
            context_parts.append(f"  - {name}: {desc}")
    
    # Relevant memories (if query provided)
    if query:
        memories = search_memories(query, user_id, limit=3)
        if memories:
            context_parts.append("\n## Relevant Memories")
            for mem in memories:
                context_parts.append(f"- [{mem['category']}] {mem['memory']}")
    
    # Important memories (high importance)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT memory, category FROM memories 
        WHERE user_id = ? AND importance >= 8
        ORDER BY importance DESC LIMIT 5
    """, (user_id,))
    important = cursor.fetchall()
    conn.close()
    
    if important:
        context_parts.append("\n## Important Facts")
        for row in important:
            context_parts.append(f"- [{row['category']}] {row['memory']}")
    
    return "\n".join(context_parts)

# ═══════════════════════════════════════════════════════════════════════════════
# AGENCY KNOWLEDGE TOOLS
# ═══════════════════════════════════════════════════════════════════════════════

def update_agency_info(key: str, value: Any) -> Dict:
    """Update agency knowledge base"""
    knowledge = load_agency_knowledge()
    
    # Handle nested keys (e.g., "services.lead_generation.price")
    keys = key.split(".")
    target = knowledge
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    
    target[keys[-1]] = value
    save_agency_knowledge(knowledge)
    
    return {"success": True, "updated": key, "value": value}

def get_agency_info(key: Optional[str] = None) -> Dict:
    """Get agency knowledge"""
    knowledge = load_agency_knowledge()
    
    if key:
        keys = key.split(".")
        target = knowledge
        for k in keys:
            if isinstance(target, dict) and k in target:
                target = target[k]
            else:
                return {"success": False, "error": f"Key not found: {key}"}
        return {"success": True, "key": key, "value": target}
    
    return {"success": True, "knowledge": knowledge}

def add_client(name: str, industry: str, status: str = "prospect") -> Dict:
    """Add a client to the agency knowledge"""
    knowledge = load_agency_knowledge()
    
    if "clients" not in knowledge:
        knowledge["clients"] = []
    
    client = {
        "name": name,
        "industry": industry,
        "status": status,
        "added_at": datetime.now().isoformat()
    }
    
    knowledge["clients"].append(client)
    save_agency_knowledge(knowledge)
    
    return {"success": True, "client": client}

# ═══════════════════════════════════════════════════════════════════════════════
# SKILL REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_ceo_memory_skills(TOOLS, tool_decorator):
    """Register CEO Memory tools"""
    
    @tool_decorator("ceo_remember", "Store important information in CEO brain")
    def _ceo_remember(fact: str, category: str = "general", importance: int = 5):
        return add_memory(fact, category, importance)
    
    @tool_decorator("ceo_recall", "Search CEO memories for relevant information")
    def _ceo_recall(query: str):
        results = search_memories(query)
        return {"success": True, "count": len(results), "memories": results}
    
    @tool_decorator("agency_info", "Get OROVA agency information (pricing, services, protocols)")
    def _agency_info(key: str = ""):
        return get_agency_info(key if key else None)
    
    @tool_decorator("update_agency", "Update OROVA agency information")
    def _update_agency(key: str, value: str):
        return update_agency_info(key, value)
    
    @tool_decorator("add_client", "Add a new client/prospect to OROVA")
    def _add_client(name: str, industry: str, status: str = "prospect"):
        return add_client(name, industry, status)
    
    TOOLS["ceo_remember"] = {"func": _ceo_remember, "description": "Store important information in CEO brain"}
    TOOLS["ceo_recall"] = {"func": _ceo_recall, "description": "Search CEO memories"}
    TOOLS["agency_info"] = {"func": _agency_info, "description": "Get OROVA agency information"}
    TOOLS["update_agency"] = {"func": _update_agency, "description": "Update OROVA agency information"}
    TOOLS["add_client"] = {"func": _add_client, "description": "Add a new client/prospect"}
    
    return TOOLS
