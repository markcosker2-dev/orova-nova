import os
import logging
from mem0 import Memory
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

class MegaMemory:
    """
    Hermes Evolution: Integrated Mem0 for personalized, entity-based long-term memory.
    Replaces the basic fact-distiller with a multi-layered knowledge graph.
    """
    def __init__(self):
        # Configure Mem0 to use SQLite for Render Free Tier (RAM optimization)
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app", "data", "mem0_db"),
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": os.getenv("OPENAI_API_KEY"),
                    "model": "google/gemini-2.0-flash-lite-001"
                }
            }
        }
        try:
            self.memory = Memory.from_config(config)
            logger.info("🧠 Mem0 Mega-Memory Online (Hermes Evolution Active)")
        except Exception as e:
            logger.error(f"💥 Mem0 Initialization failed: {e}")
            self.memory = None

    async def add(self, data: str, user_id: str = "mark", metadata: dict = None):
        """Add information to the long-term memory."""
        if not self.memory: return
        try:
            self.memory.add(data, user_id=user_id, metadata=metadata)
        except Exception as e:
            logger.error(f"💥 Mem0 Add failed: {e}")

    async def retrieve(self, query: str, user_id: str = "mark") -> str:
        """Retrieve relevant context for a query."""
        if not self.memory: return ""
        try:
            results = self.memory.search(query, user_id=user_id, limit=3)
            if not results: return ""
            
            context = "\n[RECALLED MEMORIES]:\n"
            for res in results:
                context += f"- {res['memory']}\n"
            return context
        except Exception as e:
            logger.error(f"💥 Mem0 Search failed: {e}")
            return ""

# Singleton instance
mega_memory = MegaMemory()
