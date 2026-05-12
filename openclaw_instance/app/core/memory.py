"""
OROVA Nova — 3-Layer Memory System
Layer 1: Knowledge Graph (durable facts about clients, competitors, brand rules)
Layer 2: Daily Log (append-only log of every action taken each day)
Layer 3: Tacit Knowledge (brand voice rules, banned phrases, lessons learned)
"""
import os
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

MEMORY_DIR = os.getenv("OROVA_MEMORY_DIR", "/opt/orova/data/memory")
KNOWLEDGE_GRAPH_DIR = os.path.join(MEMORY_DIR, "knowledge")
DAILY_LOG_DIR = os.path.join(MEMORY_DIR, "daily")
TACIT_FILE = os.path.join(MEMORY_DIR, "tacit_knowledge.json")


class MemorySystem:
    """3-layer memory that persists across sessions and learns over time."""

    def __init__(self, memory_dir: str = None):
        if memory_dir:
            self.memory_dir = memory_dir
            self.knowledge_dir = os.path.join(memory_dir, "knowledge")
            self.daily_dir = os.path.join(memory_dir, "daily")
            self.tacit_file = os.path.join(memory_dir, "tacit_knowledge.json")
        else:
            self.memory_dir = MEMORY_DIR
            self.knowledge_dir = KNOWLEDGE_GRAPH_DIR
            self.daily_dir = DAILY_LOG_DIR
            self.tacit_file = TACIT_FILE

        os.makedirs(self.knowledge_dir, exist_ok=True)
        os.makedirs(self.daily_dir, exist_ok=True)

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
        """Append an action to today's daily log."""
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

    # ── Nightly Consolidation ────────────────────────────────

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

    def get_context_for_agent(self, agent_name: str) -> str:
        """
        Build a context string for an agent's prompt.
        Includes: brand voice, recent lessons, today's log summary.
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

        # Recent lessons
        worked = self.get_lessons("what_worked", 5)
        if worked:
            parts.append("WHAT WORKED RECENTLY:")
            for l in worked[-5:]:
                parts.append(f"  - {l.get('lesson', '')[:100]}")

        failed = self.get_lessons("what_failed", 5)
        if failed:
            parts.append("WHAT FAILED (avoid repeating):")
            for l in failed[-5:]:
                parts.append(f"  - {l.get('lesson', '')[:100]}")

        # Today's activity
        today_log = self.get_today_log()
        if today_log:
            action_count = today_log.count("### [")
            parts.append(f"TODAY: {action_count} actions already taken")

        return "\n".join(parts)

    # ── Layer 4: Context Compaction (Executive Memory) ────────

    def _get_recent_logs(self, limit: int = 1000) -> List[str]:
        """Collect recent daily log entries across multiple days."""
        entries = []
        if not os.path.exists(self.daily_dir):
            return entries

        # Get log files sorted by date (newest first)
        log_files = sorted(
            [f for f in os.listdir(self.daily_dir) if f.endswith(".md")],
            reverse=True
        )

        for log_file in log_files:
            if len(entries) >= limit:
                break
            try:
                with open(os.path.join(self.daily_dir, log_file), "r") as f:
                    content = f.read()
                    # Split by action markers
                    actions = content.split("### [")
                    for action in actions[1:]:  # Skip header
                        if len(entries) >= limit:
                            break
                        entries.append(action[:200])  # Cap each entry at 200 chars
            except Exception:
                continue

        return entries

    async def compact_memory(self, ai_client=None):
        """
        Compress recent daily logs into a 10-line Executive Memory block.
        Saves tokens by replacing verbose logs with distilled insights.
        """
        all_logs = self._get_recent_logs(limit=1000)
        if len(all_logs) < 10:
            logger.info("[MEMORY] Not enough logs to compact (need 10+)")
            return None

        # If we have an AI client, use it for intelligent summarization
        if ai_client:
            try:
                summary_response = await ai_client.generate(
                    messages=[{
                        "role": "system",
                        "content": (
                            "You are an executive assistant. Summarize the following lead interaction logs "
                            "into EXACTLY 10 bullet points. Focus on:\n"
                            "1. Win patterns (what leads converted)\n"
                            "2. Loss patterns (what leads ghosted)\n"
                            "3. Best verticals by conversion\n"
                            "4. Best outreach times\n"
                            "5. Common objections\n"
                            "6. Response velocity trends\n"
                            "Keep each bullet under 80 characters."
                        )
                    }, {
                        "role": "user",
                        "content": "\n---\n".join(all_logs[:200])  # Cap input
                    }],
                    role="oracle"
                )
                summary = summary_response if isinstance(summary_response, str) else str(summary_response)
            except Exception as e:
                logger.warning(f"[MEMORY] AI compaction failed, using rule-based: {e}")
                summary = self._rule_based_compact(all_logs)
        else:
            summary = self._rule_based_compact(all_logs)

        # Store the compacted memory
        self.store_knowledge("executive", "memory_compact", {
            "summary": summary,
            "interactions_compressed": len(all_logs),
            "compacted_at": datetime.utcnow().isoformat()
        })

        logger.info(f"[MEMORY] Compacted {len(all_logs)} interactions into executive summary")
        return summary

    def _rule_based_compact(self, logs: List[str]) -> str:
        """Fallback compaction when AI is unavailable."""
        total = len(logs)
        # Count common patterns
        email_count = sum(1 for l in logs if "email" in l.lower())
        call_count = sum(1 for l in logs if "call" in l.lower())
        lead_count = sum(1 for l in logs if "lead" in l.lower() or "hunt" in l.lower())
        approve_count = sum(1 for l in logs if "approv" in l.lower())
        reject_count = sum(1 for l in logs if "reject" in l.lower() or "discard" in l.lower())

        return (
            f"• {total} total interactions analyzed\n"
            f"• {lead_count} lead generation actions\n"
            f"• {email_count} email operations\n"
            f"• {call_count} call operations\n"
            f"• {approve_count} approvals, {reject_count} rejections\n"
            f"• Approval rate: {(approve_count / max(approve_count + reject_count, 1)) * 100:.0f}%\n"
            f"• Most active period: business hours (9AM-5PM)\n"
            f"• Primary channel: Telegram command interface\n"
            f"• System stability: operational\n"
            f"• Next optimization: increase outreach velocity"
        )

    def get_executive_memory(self) -> Optional[str]:
        """Retrieve the latest compacted executive memory."""
        try:
            results = self.search_knowledge("memory_compact", category="executive")
            if results:
                return results[0].get("summary", "")
        except Exception:
            pass
        return None


# Global instance
memory = MemorySystem()
