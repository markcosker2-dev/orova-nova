"""
OROVA Nova — 4-Layer Memory System
Layer 1: Knowledge Graph (durable facts about clients, competitors, brand rules)
Layer 2: Daily Log (append-only log of every action taken each day)
Layer 3: Tacit Knowledge (brand voice rules, banned phrases, lessons learned)
Layer 4: Episodic Vector Memory (semantic search over all past experiences)
"""
import os
import json
import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

MEMORY_DIR = os.getenv("OROVA_MEMORY_DIR", "/opt/orova/data/memory")
KNOWLEDGE_GRAPH_DIR = os.path.join(MEMORY_DIR, "knowledge")
DAILY_LOG_DIR = os.path.join(MEMORY_DIR, "daily")
VECTOR_DB_DIR = os.path.join(MEMORY_DIR, "chroma")
TACIT_FILE = os.path.join(MEMORY_DIR, "tacit_knowledge.json")

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("[MEMORY] ChromaDB not installed, vector memory disabled")


class MemorySystem:
    """3-layer memory that persists across sessions and learns over time."""

    def __init__(self, memory_dir: str = None):
        if memory_dir:
            self.memory_dir = memory_dir
            self.knowledge_dir = os.path.join(memory_dir, "knowledge")
            self.daily_dir = os.path.join(memory_dir, "daily")
            self.vector_dir = os.path.join(memory_dir, "chroma")
            self.tacit_file = os.path.join(memory_dir, "tacit_knowledge.json")
        else:
            self.memory_dir = MEMORY_DIR
            self.knowledge_dir = KNOWLEDGE_GRAPH_DIR
            self.daily_dir = DAILY_LOG_DIR
            self.vector_dir = VECTOR_DB_DIR
            self.tacit_file = TACIT_FILE

        os.makedirs(self.knowledge_dir, exist_ok=True)
        os.makedirs(self.daily_dir, exist_ok=True)
        os.makedirs(self.vector_dir, exist_ok=True)

        # Initialize ChromaDB with local persistence
        self.chroma_client = None
        self.episodic_collection = None
        
        if CHROMA_AVAILABLE:
            try:
                self.chroma_client = chromadb.PersistentClient(path=self.vector_dir)
                self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
                self.episodic_collection = self.chroma_client.get_or_create_collection(
                    name="episodic_memory",
                    embedding_function=self.embedding_fn,
                    metadata={"description": "All logged actions and experiences"}
                )
                logger.info("[MEMORY] Episodic vector memory initialized")
            except Exception as e:
                logger.warning(f"[MEMORY] Failed to initialize ChromaDB: {str(e)}")
                self.chroma_client = None
                self.episodic_collection = None

        if not os.path.exists(self.tacit_file):
            self._save_tacit({
                "brand_voice": {
                    "tone": "professional, confident, never desperate",
                    "banned_words": ["cheap", "affordable", "budget", "discount", "deal", "free trial"],
                    "preferred_words": ["investment", "premium", "tailored", "bespoke", "exclusive"],
                    "cta_style": "soft close — offer value, don't pressure"
                },
                "what_worked": [],
                "what_failed": [],
                "competitor_notes": {},
                "client_preferences": {}
            })

    # ── Layer 1: Knowledge Graph ─────────────────────────────

    def store_knowledge(self, category: str, key: str, data: Dict[str, Any]):
        """Store a durable fact in the knowledge graph.
        Categories: clients, competitors, verticals, contacts, campaigns
        """
        cat_dir = os.path.join(self.knowledge_dir, category)
        os.makedirs(cat_dir, exist_ok=True)

        file_path = os.path.join(cat_dir, f"{key}.json")

        existing = {}
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                existing = json.load(f)

        existing.update(data)
        existing["_updated_at"] = datetime.utcnow().isoformat()
        existing["_category"] = category
        existing["_key"] = key

        with open(file_path, "w") as f:
            json.dump(existing, f, indent=2)

        logger.info(f"[MEMORY] Stored knowledge: {category}/{key}")

    def search_knowledge(self, query: str, category: str = None) -> List[Dict]:
        """Search the knowledge graph by keyword."""
        results = []
        search_dirs = []

        if category:
            cat_dir = os.path.join(self.knowledge_dir, category)
            if os.path.exists(cat_dir):
                search_dirs.append(cat_dir)
        else:
            if os.path.exists(self.knowledge_dir):
                search_dirs = [
                    os.path.join(self.knowledge_dir, d)
                    for d in os.listdir(self.knowledge_dir)
                    if os.path.isdir(os.path.join(self.knowledge_dir, d))
                ]

        query_lower = query.lower()
        for d in search_dirs:
            for fname in os.listdir(d):
                if fname.endswith(".json"):
                    with open(os.path.join(d, fname), "r") as f:
                        data = json.load(f)
                    text = json.dumps(data).lower()
                    if query_lower in text:
                        results.append(data)

        return results

    def get_knowledge(self, category: str, key: str) -> Optional[Dict]:
        """Retrieve a specific knowledge entry."""
        file_path = os.path.join(self.knowledge_dir, category, f"{key}.json")
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
        return None

    # ── Layer 2: Daily Log ───────────────────────────────────

    def log_action(self, agent: str, action: str, details: str = "", result: str = ""):
        """Append an action to today's daily log and vector memory."""
        today = date.today().isoformat()
        log_file = os.path.join(self.daily_dir, f"{today}.md")

        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"\n### [{timestamp}] {agent} | {action}\n"
        if details:
            entry += f"- Details: {details}\n"
        if result:
            entry += f"- Result: {result}\n"
        entry += "---\n"

        with open(log_file, "a") as f:
            f.write(entry)
        
        # Store in vector memory (idempotent)
        if self.episodic_collection:
            try:
                # Generate deterministic unique ID for entry
                entry_hash = hashlib.sha256(f"{today}{timestamp}{agent}{action}{details}{result}".encode()).hexdigest()
                
                # Build full text document for embedding
                document = f"[{today} {timestamp}] Agent: {agent}, Action: {action}"
                if details:
                    document += f"\nDetails: {details}"
                if result:
                    document += f"\nResult: {result}"
                
                # Idempotent upsert
                self.episodic_collection.upsert(
                    ids=[entry_hash],
                    documents=[document],
                    metadatas=[{
                        "date": today,
                        "timestamp": timestamp,
                        "agent": agent,
                        "action": action,
                        "type": "log_entry"
                    }]
                )
            except Exception as e:
                logger.debug(f"[MEMORY] Vector store failed: {str(e)}")

    def get_today_log(self) -> str:
        """Read today's daily log."""
        today = date.today().isoformat()
        log_file = os.path.join(self.daily_dir, f"{today}.md")
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                return f.read()
        return ""

    def get_log_for_date(self, target_date: str) -> str:
        """Read a specific date's log (YYYY-MM-DD)."""
        log_file = os.path.join(self.daily_dir, f"{target_date}.md")
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                return f.read()
        return ""

    # ── Layer 3: Tacit Knowledge ─────────────────────────────

    def _load_tacit(self) -> Dict:
        with open(self.tacit_file, "r") as f:
            return json.load(f)

    def _save_tacit(self, data: Dict):
        with open(self.tacit_file, "w") as f:
            json.dump(data, f, indent=2)

    def get_brand_voice(self) -> Dict:
        """Get brand voice rules."""
        tacit = self._load_tacit()
        return tacit.get("brand_voice", {})

    def add_lesson_learned(self, lesson: str, category: str = "what_worked"):
        """Add a lesson to tacit knowledge. Category: what_worked or what_failed."""
        tacit = self._load_tacit()
        if category not in tacit:
            tacit[category] = []
        tacit[category].append({
            "lesson": lesson,
            "learned_at": datetime.utcnow().isoformat()
        })
        self._save_tacit(tacit)
        logger.info(f"[MEMORY] Lesson learned [{category}]: {lesson[:60]}")

    def get_lessons(self, category: str = "what_worked", limit: int = 20) -> List[Dict]:
        """Get recent lessons."""
        tacit = self._load_tacit()
        return tacit.get(category, [])[-limit:]

    def update_competitor_notes(self, competitor: str, notes: str):
        """Update notes about a competitor."""
        tacit = self._load_tacit()
        if "competitor_notes" not in tacit:
            tacit["competitor_notes"] = {}
        tacit["competitor_notes"][competitor] = {
            "notes": notes,
            "updated_at": datetime.utcnow().isoformat()
        }
        self._save_tacit(tacit)

    def update_client_preference(self, client_id: str, preferences: Dict):
        """Store client preferences."""
        tacit = self._load_tacit()
        if "client_preferences" not in tacit:
            tacit["client_preferences"] = {}
        tacit["client_preferences"][client_id] = {
            **preferences,
            "updated_at": datetime.utcnow().isoformat()
        }
        self._save_tacit(tacit)

    # ── Layer 4: Episodic Vector Memory ───────────────────────

    def semantic_search(self, query: str, limit: int = 10, threshold: float = 0.7) -> List[Dict]:
        """
        Perform semantic search over all past experiences.
        Returns matching entries sorted by relevance.
        """
        if not self.episodic_collection:
            return []
        
        try:
            results = self.episodic_collection.query(
                query_texts=[query],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
            
            formatted = []
            for doc, meta, distance in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
                # Chroma distance is L2; higher = less relevant
                relevance = 1.0 - min(distance / 2.0, 1.0)
                if relevance >= threshold:
                    formatted.append({
                        "content": doc,
                        "date": meta.get("date"),
                        "agent": meta.get("agent"),
                        "action": meta.get("action"),
                        "relevance": round(relevance, 3)
                    })
            
            return formatted
        except Exception as e:
            logger.debug(f"[MEMORY] Semantic search failed: {str(e)}")
            return []

    # ── Nightly Consolidation ────────────────────────────────
    
    def compact_memory(self, interaction_limit: int = 1000, bullet_count: int = 10) -> List[str]:
        """
        Summarize last 1000 lead interactions into 10 bullet point executive summary.
        Uses Gemini 1.5 Flash for high quality summarization.
        """
        from app.core.ai_client import ai
        
        logger.info(f"[MEMORY] Running compact_memory: summarizing last {interaction_limit} interactions")
        
        # Get last N interactions from vector memory
        if not self.episodic_collection:
            logger.warning("[MEMORY] No vector collection available for compaction")
            return []
        
        try:
            # Fetch most recent interactions
            results = self.episodic_collection.get(
                limit=interaction_limit,
                include=["documents", "metadatas"]
            )
            
            if not results or not results["documents"]:
                logger.info("[MEMORY] No interactions found for compaction")
                return []
            
            # Format interactions for summarization
            interactions_text = "\n---\n".join(
                f"[{meta['date']} {meta['timestamp']}] {meta['agent']} | {doc[:500]}"
                for doc, meta in zip(results["documents"], results["metadatas"])
            )
            
            # Call Gemini 1.5 Flash for executive summarization
            prompt = f"""
            You are an executive analyst. Summarize these {len(results['documents'])} recent lead interactions
            into EXACTLY {bullet_count} high impact bullet points.
            
            Rules:
            - Each bullet must be 1 sentence maximum
            - Focus on trends, outcomes, patterns, and actionable insights
            - Ignore trivial log entries
            - Highlight what's working, what's failing, and important observations
            - Do not use formatting, only plain text bullets starting with "- "
            
            INTERACTIONS:
            {interactions_text}
            """
            
            summary = ai.chat([{"role": "user", "content": prompt}], role="oracle")
            
            # Parse and clean bullet points
            bullets = []
            for line in summary.strip().split("\n"):
                line = line.strip()
                if line.startswith("- ") and len(bullets) < bullet_count:
                    bullets.append(line[2:].strip())
            
            # Store summary in knowledge graph
            today = date.today().isoformat()
            self.store_knowledge("executive_summaries", today, {
                "date": today,
                "interactions_analyzed": len(results["documents"]),
                "summary_bullets": bullets,
                "generated_at": datetime.utcnow().isoformat()
            })
            
            logger.info(f"[MEMORY] Compact memory complete: {len(bullets)} bullet summary generated")
            return bullets
            
        except Exception as e:
            logger.error(f"[MEMORY] Compact memory failed: {str(e)}")
            return []

    def consolidate(self):
        """
        Run nightly consolidation:
        1. Read today's daily log
        2. Extract durable learnings
        3. Store in knowledge graph or tacit knowledge
        4. Archive the daily log
        """
        today = date.today().isoformat()
        log_content = self.get_today_log()

        if not log_content:
            logger.info("[MEMORY] No actions today, skipping consolidation")
            return

        # Count actions by agent
        action_counts = {}
        for line in log_content.split("\n"):
            if line.startswith("### ["):
                parts = line.split("|")
                if len(parts) >= 2:
                    agent = parts[0].split("]")[-1].strip()
                    action_counts[agent] = action_counts.get(agent, 0) + 1

        # Store daily summary in knowledge graph
        self.store_knowledge("daily_summaries", today, {
            "date": today,
            "total_actions": sum(action_counts.values()),
            "actions_by_agent": action_counts,
            "log_length": len(log_content)
        })

        # Extract and store what happened per vertical
        for vertical in ["HVAC", "Roofing", "LuxuryRemodeling", "Automotive"]:
            if vertical.lower() in log_content.lower():
                self.store_knowledge("verticals", vertical.lower(), {
                    "last_active": today,
                    "notes": f"Activity detected on {today}"
                })

        logger.info(f"[MEMORY] Consolidated {today}: {sum(action_counts.values())} actions across {len(action_counts)} agents")

        return {
            "date": today,
            "actions_consolidated": sum(action_counts.values()),
            "agents_active": list(action_counts.keys())
        }

    # ── Context for Agent Prompts ────────────────────────────

    def get_context_for_agent(self, agent_name: str, goal: str = None) -> str:
        """
        Build a context string for an agent's prompt.
        Includes: brand voice, recent lessons, today's log summary, semantic matches for current goal.
        """
        parts = []

        # Brand voice
        voice = self.get_brand_voice()
        if voice:
            parts.append(f"BRAND VOICE: Tone={voice.get('tone', 'N/A')}")
            if voice.get("banned_words"):
                parts.append(f"NEVER use these words: {', '.join(voice['banned_words'])}")
            if voice.get("preferred_words"):
                parts.append(f"Preferred language: {', '.join(voice['preferred_words'])}")

        # Semantic relevant past experiences for current goal
        if goal and self.episodic_collection:
            relevant = self.semantic_search(goal, limit=5)
            if relevant:
                parts.append("\nRELEVANT PAST EXPERIENCES:")
                for exp in relevant:
                    parts.append(f"  [{exp['date']}] {exp['content'][:180]}")

        # Recent lessons
        worked = self.get_lessons("what_worked", 5)
        if worked:
            parts.append("\nWHAT WORKED RECENTLY:")
            for l in worked[-5:]:
                parts.append(f"  - {l.get('lesson', '')[:100]}")

        failed = self.get_lessons("what_failed", 5)
        if failed:
            parts.append("\nWHAT FAILED (avoid repeating):")
            for l in failed[-5:]:
                parts.append(f"  - {l.get('lesson', '')[:100]}")

        # Today's activity
        today_log = self.get_today_log()
        if today_log:
            action_count = today_log.count("### [")
            parts.append(f"\nTODAY: {action_count} actions already taken")

        return "\n".join(parts)


# Global instance
memory = MemorySystem()
